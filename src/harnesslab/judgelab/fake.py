from __future__ import annotations

import json
import re

from harnesslab.model_lane.models import (
    ProviderFailureCategory,
    ProviderInvocationError,
    ProviderRequest,
    ProviderResult,
    ProviderUsage,
)


class FakeJudgeProvider:
    """Deterministic keyless adapter that interprets only the public Judge request."""

    def __init__(
        self,
        behavior: str = "GOOD",
        *,
        scenario: str | None = None,
    ) -> None:
        self.behavior = behavior
        self.scenario = scenario
        self.requests: list[ProviderRequest] = []

    async def invoke(self, request: ProviderRequest) -> ProviderResult:
        self.requests.append(request)
        if self.scenario == "provider_timeout":
            raise ProviderInvocationError(
                ProviderFailureCategory.TIMEOUT, "fake Judge provider timed out"
            )
        payload = json.loads(request.input)
        case = payload["public_case"]
        if self.scenario == "refusal":
            output, refused = "", True
        elif self.scenario == "malformed":
            output, refused = "{not-json", False
        elif self.scenario == "duplicate":
            output, refused = (
                '{"schema_version":1,"label":"PASS","label":"FAIL","reason":"x"}',
                False,
            )
        elif self.scenario == "extra_field":
            output, refused = (
                json.dumps(
                    {"schema_version": 1, "label": "PASS", "reason": "x", "extra": True},
                    separators=(",", ":"),
                ),
                False,
            )
        elif self.scenario == "private_reasoning":
            output, refused = (
                json.dumps(
                    {
                        "schema_version": 1,
                        "label": "PASS",
                        "reason": "public",
                        "thinking": "PRIVATE_REASONING_SENTINEL",
                    },
                    separators=(",", ":"),
                ),
                False,
            )
        elif self.scenario == "out_of_range":
            output, refused = (
                json.dumps(
                    {"schema_version": 1, "score": 999, "abstain": False, "reason": "invalid"},
                    separators=(",", ":"),
                ),
                False,
            )
        else:
            output, refused = self._judge(case), False
        return ProviderResult(
            requested_model=request.profile.requested_model,
            observed_model=request.profile.requested_model,
            provider=request.profile.provider,
            endpoint=f"{request.profile.base_url}{request.profile.route}",
            protocol=request.profile.protocol,
            request_id=f"fake-judge-{len(self.requests)}",
            public_output_text=output,
            refused=refused,
            usage=ProviderUsage(input_tokens=80, output_tokens=18, total_tokens=98),
            stop_reason="stop",
            response_status="completed",
            latency_ms=0,
            attempt_count=1,
        )

    def _judge(self, case: dict[str, object]) -> str:
        mode = str(case["mode"])
        repeat_raw = case["repeat_index"]
        if not isinstance(repeat_raw, int) or isinstance(repeat_raw, bool):
            raise ValueError("fake Judge request has invalid repeat index")
        repeat = repeat_raw
        biased = self.behavior == "BIASED"
        if mode == "LABEL":
            candidate = str(case["candidate"])
            if "INSUFFICIENT_INFORMATION" in candidate:
                label = "UNKNOWN"
            else:
                label = "PASS" if "QUALITY=PASS" in candidate else "FAIL"
            if biased and repeat % 2:
                label = "FAIL" if label == "PASS" else "PASS"
            return json.dumps(
                {"schema_version": 1, "label": label, "reason": "Public rubric applied."},
                separators=(",", ":"),
            )
        if mode == "SCORE":
            candidate = str(case["candidate"])
            match = re.search(r"QUALITY_SCORE=([0-9]+(?:\.[0-9]+)?)", candidate)
            score = float(match.group(1)) if match else None
            if biased and score is not None:
                score = max(1.0, min(5.0, score + (1.5 if repeat % 2 else -1.0)))
            return json.dumps(
                {
                    "schema_version": 1,
                    "score": score,
                    "abstain": score is None,
                    "reason": "Public rubric applied.",
                },
                separators=(",", ":"),
            )
        left = str(case["candidate_left"])
        right = str(case["candidate_right"])
        if "INSUFFICIENT_INFORMATION" in left + right:
            preference = "UNKNOWN"
        elif biased:
            preference = "LEFT" if repeat % 2 == 0 else "RIGHT"
            if "VERBOSITY_PROBE" in left + right:
                preference = "LEFT" if len(left) > len(right) else "RIGHT"
        else:
            left_match = re.search(r"QUALITY_SCORE=([0-9]+)", left)
            right_match = re.search(r"QUALITY_SCORE=([0-9]+)", right)
            left_score = int(left_match.group(1)) if left_match else 0
            right_score = int(right_match.group(1)) if right_match else 0
            preference = (
                "LEFT"
                if left_score > right_score
                else "RIGHT"
                if right_score > left_score
                else "TIE"
            )
        return json.dumps(
            {
                "schema_version": 1,
                "preference": preference,
                "reason": "Candidates compared under the public rubric.",
            },
            separators=(",", ":"),
        )
