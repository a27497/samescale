from __future__ import annotations

import json
from enum import StrEnum

from harnesslab.harness_lane.adapter import CodexExecutionPlan
from harnesslab.harness_lane.models import CodexProcessCapture

PRIVATE_REASONING_SENTINEL = "PRIVATE_CODEX_REASONING_MUST_NEVER_PERSIST"


class FakeCodexScenario(StrEnum):
    SOLVE = "solve"
    SELF_REPORTED_SUCCESS_WRONG_WORKSPACE = "self_reported_success_wrong_workspace"
    MALFORMED_JSONL = "malformed_jsonl"
    TURN_FAILED = "turn_failed"
    PROCESS_ERROR = "process_error"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    INTERMEDIATE_COMMAND_FAILURE = "intermediate_command_failure"
    PROFILE_VIOLATION_WEB = "profile_violation_web"
    PROFILE_VIOLATION_MCP = "profile_violation_mcp"
    REASONING_PRIVATE = "reasoning_private"
    FILE_CHANGE_LIE = "file_change_lie"
    OBSERVED_MODEL_EXPOSED = "observed_model_exposed"


def _line(payload: dict[str, object]) -> str:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def _solution(task_id: str) -> tuple[str, str]:
    if task_id == "micro-python-clamp":
        return (
            "calculator.py",
            "def clamp(value: int, lower: int, upper: int) -> int:\n"
            "    return max(lower, min(value, upper))\n",
        )
    if task_id == "micro-java-clamp":
        return (
            "Range.java",
            "public final class Range {\n"
            "    private Range() {}\n\n"
            "    public static int clamp(int value, int lower, int upper) {\n"
            "        return Math.max(lower, Math.min(value, upper));\n"
            "    }\n"
            "}\n",
        )
    if task_id == "micro-typescript-clamp":
        return (
            "range.ts",
            "export function clamp(value: number, lower: number, upper: number): number {\n"
            "  return Math.max(lower, Math.min(value, upper));\n"
            "}\n",
        )
    raise ValueError(f"unsupported Fake Codex task: {task_id}")


class FakeCodexBackend:
    """Trusted deterministic fixture that still uses the production adapter and evidence path."""

    def __init__(self, scenario: FakeCodexScenario = FakeCodexScenario.SOLVE) -> None:
        self.scenario = scenario
        self.plans: list[CodexExecutionPlan] = []

    @property
    def artifact_secret_values(self) -> tuple[str, ...]:
        return ()

    async def run(self, plan: CodexExecutionPlan) -> CodexProcessCapture:
        self.plans.append(plan)
        thread: dict[str, object] = {"type": "thread.started", "thread_id": "fake-thread-1"}
        if self.scenario is FakeCodexScenario.OBSERVED_MODEL_EXPOSED:
            thread["observed_model"] = "fake-observed-codex-model"
        lines = [
            _line(thread),
            _line({"type": "turn.started"}),
        ]
        if self.scenario is FakeCodexScenario.MALFORMED_JSONL:
            lines.append("{this is not valid JSON")
            return CodexProcessCapture(tuple(lines), 0, 4)
        if self.scenario is FakeCodexScenario.TURN_FAILED:
            lines.append(
                _line(
                    {
                        "type": "turn.failed",
                        "error": {"code": "model_turn_failed", "message": "safe failure"},
                    }
                )
            )
            return CodexProcessCapture(tuple(lines), 1, 5)
        if self.scenario is FakeCodexScenario.PROCESS_ERROR:
            return CodexProcessCapture(tuple(lines), 7, 5)
        if self.scenario is FakeCodexScenario.TIMEOUT:
            return CodexProcessCapture(tuple(lines), None, 50, timed_out=True)
        if self.scenario is FakeCodexScenario.CANCELLED:
            return CodexProcessCapture(tuple(lines), None, 7, cancelled=True)
        if self.scenario in {FakeCodexScenario.SOLVE, FakeCodexScenario.OBSERVED_MODEL_EXPOSED}:
            path, content = _solution(plan.task_id)
            (plan.workspace / path).write_text(content, encoding="utf-8")
            lines.extend(
                (
                    _line(
                        {
                            "type": "item.completed",
                            "item": {
                                "id": "reasoning-1",
                                "type": "reasoning",
                                "text": PRIVATE_REASONING_SENTINEL,
                                "summary": [PRIVATE_REASONING_SENTINEL],
                                "status": "completed",
                            },
                        }
                    ),
                    _line(
                        {
                            "type": "item.completed",
                            "item": {
                                "id": "file-1",
                                "type": "file_change",
                                "status": "completed",
                                "changes": [{"path": f"/workspace/{path}", "kind": "update"}],
                            },
                        }
                    ),
                )
            )
        elif self.scenario is FakeCodexScenario.INTERMEDIATE_COMMAND_FAILURE:
            lines.append(
                _line(
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "command-1",
                            "type": "command_execution",
                            "command": "false",
                            "aggregated_output": "synthetic command failure",
                            "exit_code": 1,
                            "status": "failed",
                        },
                    }
                )
            )
        elif self.scenario is FakeCodexScenario.PROFILE_VIOLATION_WEB:
            lines.append(
                _line(
                    {
                        "type": "item.completed",
                        "item": {"id": "web-1", "type": "web_search", "status": "completed"},
                    }
                )
            )
        elif self.scenario is FakeCodexScenario.PROFILE_VIOLATION_MCP:
            lines.append(
                _line(
                    {
                        "type": "item.completed",
                        "item": {"id": "mcp-1", "type": "mcp_tool_call", "status": "completed"},
                    }
                )
            )
        elif self.scenario is FakeCodexScenario.REASONING_PRIVATE:
            lines.append(
                _line(
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "reasoning-1",
                            "type": "reasoning",
                            "text": PRIVATE_REASONING_SENTINEL,
                            "summary": [PRIVATE_REASONING_SENTINEL],
                            "status": "completed",
                        },
                    }
                )
            )
        elif self.scenario is FakeCodexScenario.FILE_CHANGE_LIE:
            lines.append(
                _line(
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "file-lie",
                            "type": "file_change",
                            "status": "completed",
                            "changes": [{"path": "/workspace/claimed.txt", "kind": "add"}],
                        },
                    }
                )
            )
        lines.extend(
            (
                _line(
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "message-1",
                            "type": "agent_message",
                            "text": "Implemented successfully; tests pass.",
                        },
                    }
                ),
                _line(
                    {
                        "type": "turn.completed",
                        "usage": {
                            "input_tokens": 100,
                            "cached_input_tokens": 20,
                            "cache_write_input_tokens": 0,
                            "output_tokens": 30,
                            "reasoning_output_tokens": 10,
                        },
                    }
                ),
            )
        )
        return CodexProcessCapture(tuple(lines), 0, 12)
