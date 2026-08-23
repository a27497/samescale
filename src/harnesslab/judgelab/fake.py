from __future__ import annotations

import json

from harnesslab.model_lane.models import (
    ProviderFailureCategory,
    ProviderInvocationError,
    ProviderRequest,
    ProviderResult,
    ProviderUsage,
)


class FakeJudgeProvider:
    """Deterministic keyless test adapter over public fixture identity and content."""

    def __init__(
        self,
        behavior: str = "GOOD",
        *,
        scenario: str | None = None,
        provider_timeout_slots: frozenset[tuple[str, int, str]] = frozenset(),
    ) -> None:
        self.behavior = behavior
        self.scenario = scenario
        self.provider_timeout_slots = provider_timeout_slots
        self.requests: list[ProviderRequest] = []

    async def invoke(self, request: ProviderRequest) -> ProviderResult:
        self.requests.append(request)
        payload = json.loads(request.input)
        case = payload["public_case"]
        slot_identity = (
            str(case["case_id"]),
            int(case["repeat_index"]),
            str(case["order_variant"]),
        )
        if self.scenario == "provider_timeout" or slot_identity in self.provider_timeout_slots:
            raise ProviderInvocationError(
                ProviderFailureCategory.TIMEOUT, "fake Judge provider timed out"
            )
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
        case_id = str(case["case_id"])
        repeat_raw = case["repeat_index"]
        if not isinstance(repeat_raw, int) or isinstance(repeat_raw, bool):
            raise ValueError("fake Judge request has invalid repeat index")
        repeat = repeat_raw
        biased = self.behavior == "BIASED"
        if mode == "LABEL":
            label = {
                "label-l0-pass": "PASS",
                "label-l0-fail": "FAIL",
                "label-l1-clear": "PASS",
                "label-l1-irrelevant": "FAIL",
                "label-unknown": "UNKNOWN",
            }[case_id]
            if biased and repeat % 2:
                label = "FAIL" if label == "PASS" else "PASS"
            return json.dumps(
                {"schema_version": 1, "label": label, "reason": "Public rubric applied."},
                separators=(",", ":"),
            )
        if mode == "SCORE":
            score = {
                "score-arithmetic-fragment": 1.0,
                "score-security-caveat": 2.0,
                "score-deployment-guide": 4.0,
                "score-citation-answer": 5.0,
            }[case_id]
            if biased:
                score = max(1.0, min(5.0, score + (1.5 if repeat % 2 else -1.0)))
            return json.dumps(
                {
                    "schema_version": 1,
                    "score": score,
                    "abstain": False,
                    "reason": "Public rubric applied.",
                },
                separators=(",", ":"),
            )
        left = str(case["candidate_left"])
        right = str(case["candidate_right"])
        variant = str(case["order_variant"])
        canonical_gold = {
            "pair-arithmetic": "A",
            "pair-adversarial": "B",
            "pair-concurrency": "TIE",
            "pair-unpublished": "UNKNOWN",
            "pair-restatement": "TIE",
            "pair-transport": "TIE",
        }[case_id]
        if biased and canonical_gold != "UNKNOWN":
            preference = "LEFT" if repeat % 2 == 0 else "RIGHT"
            if case_id in {"pair-restatement", "pair-transport"}:
                preference = "LEFT" if len(left) > len(right) else "RIGHT"
        else:
            preference = canonical_gold
            if canonical_gold in {"A", "B"}:
                canonical_left = "A" if variant == "ORIGINAL" else "B"
                preference = "LEFT" if canonical_gold == canonical_left else "RIGHT"
        return json.dumps(
            {
                "schema_version": 1,
                "preference": preference,
                "reason": "Candidates compared under the public rubric.",
            },
            separators=(",", ":"),
        )
