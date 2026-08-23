from __future__ import annotations

import json
from enum import StrEnum

from harnesslab.multi_harness.adapter import HarnessExecutionPlan
from harnesslab.multi_harness.models import HarnessKind, HarnessProcessCapture

PRIVATE_CLAUDE_REASONING_SENTINEL = "PRIVATE_CLAUDE_REASONING_MUST_NEVER_PERSIST"


class FakeHarnessScenario(StrEnum):
    SOLVE = "solve"
    SELF_REPORTED_SUCCESS_WRONG_WORKSPACE = "self_reported_success_wrong_workspace"
    PROFILE_VIOLATION = "profile_violation"
    PRIVATE_REASONING = "private_reasoning"
    API_RETRY = "api_retry"
    MALFORMED = "malformed"
    PROCESS_ERROR = "process_error"
    TIMEOUT = "timeout"


def _solution(task_id: str) -> tuple[str, str]:
    solutions = {
        "micro-python-clamp": (
            "calculator.py",
            "def clamp(value: int, lower: int, upper: int) -> int:\n"
            "    return max(lower, min(value, upper))\n",
        ),
        "micro-java-clamp": (
            "Range.java",
            "public final class Range {\n"
            "    private Range() {}\n\n"
            "    public static int clamp(int value, int lower, int upper) {\n"
            "        return Math.max(lower, Math.min(value, upper));\n"
            "    }\n"
            "}\n",
        ),
        "micro-typescript-clamp": (
            "range.ts",
            "export function clamp(value: number, lower: number, upper: number): number {\n"
            "  return Math.max(lower, Math.min(value, upper));\n"
            "}\n",
        ),
    }
    try:
        return solutions[task_id]
    except KeyError as exc:
        raise ValueError(f"unsupported fake Phase F task: {task_id}") from exc


def _line(payload: dict[str, object]) -> str:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


class FakeMultiHarnessBackend:
    """Deterministic fixture that traverses the production Phase F evidence path."""

    def __init__(
        self,
        scenario: FakeHarnessScenario = FakeHarnessScenario.SOLVE,
        *,
        secret_values: tuple[str, ...] = (),
    ) -> None:
        self.scenario = scenario
        self._secret_values = secret_values
        self.plans: list[HarnessExecutionPlan] = []

    @property
    def artifact_secret_values(self) -> tuple[str, ...]:
        return self._secret_values

    async def run(self, plan: HarnessExecutionPlan) -> HarnessProcessCapture:
        self.plans.append(plan)
        if self.scenario is FakeHarnessScenario.TIMEOUT:
            return HarnessProcessCapture((), "", None, 30_000, timed_out=True)
        if self.scenario is FakeHarnessScenario.PROCESS_ERROR:
            return HarnessProcessCapture(("safe failure",), "", 7, 8)
        if self.scenario is FakeHarnessScenario.MALFORMED:
            return HarnessProcessCapture(("{malformed",), "", 0, 3)
        if self.scenario is FakeHarnessScenario.SOLVE:
            path, content = _solution(plan.task_id)
            (plan.workspace / path).write_text(content, encoding="utf-8")
        if plan.harness is HarnessKind.DEEPSEEK:
            public_output = "Implemented successfully; the hidden verifier remains authoritative."
            if self._secret_values:
                public_output += f" leaked={self._secret_values[0]}"
            return HarnessProcessCapture(
                (public_output,),
                "",
                0,
                12,
            )
        tools = ["Read", "Edit", "Write", "Bash"]
        if self.scenario is FakeHarnessScenario.PROFILE_VIOLATION:
            tools.append("WebSearch")
        lines = [
            _line(
                {
                    "type": "system",
                    "subtype": "init",
                    "model": "fake-observed-claude-model",
                    "tools": tools,
                    "mcp_servers": [],
                    "plugins": [],
                }
            )
        ]
        if self.scenario in {
            FakeHarnessScenario.SOLVE,
            FakeHarnessScenario.PRIVATE_REASONING,
        }:
            blocks: list[dict[str, object]] = [
                {
                    "type": "thinking",
                    "thinking": PRIVATE_CLAUDE_REASONING_SENTINEL,
                }
            ]
            if self.scenario is FakeHarnessScenario.SOLVE:
                path, _ = _solution(plan.task_id)
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": "tool-1",
                        "name": "Edit",
                        "input": {
                            "file_path": f"/workspace/{path}",
                            "old_string": "private-input-not-evidence",
                            "new_string": "private-input-not-evidence",
                        },
                    }
                )
            lines.append(_line({"type": "assistant", "message": {"content": blocks}}))
        if self.scenario is FakeHarnessScenario.API_RETRY:
            lines.append(
                _line(
                    {
                        "type": "system",
                        "subtype": "api_retry",
                        "attempt": "2",
                        "error": "overloaded_error",
                    }
                )
            )
        lines.extend(
            (
                _line(
                    {
                        "type": "assistant",
                        "message": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Implemented successfully; tests pass.",
                                }
                            ]
                        },
                    }
                ),
                _line(
                    {
                        "type": "result",
                        "subtype": "success",
                        "is_error": False,
                        "result": "Implemented successfully; tests pass.",
                        "usage": {"input_tokens": 100, "output_tokens": 30},
                    }
                ),
            )
        )
        return HarnessProcessCapture(tuple(lines), "", 0, 12)
