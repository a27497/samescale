from __future__ import annotations

from harnesslab.comparability.models import (
    ComparabilityIntent,
    ComparabilityReason,
    ComparabilityReport,
    ComparabilityStatus,
    ComparisonFacts,
    FieldComparison,
    FieldState,
    ReasonCode,
    ReasonSeverity,
)

FIELDS = (
    "task_id",
    "task_version",
    "task_digest",
    "workspace_input_digest",
    "context_identity",
    "verifier_identity",
    "requested_model",
    "observed_model",
    "provider_route",
    "budget_identity",
    "network_policy",
    "harness",
    "harness_version",
    "harness_profile_identity",
    "prompt_identity",
    "trace_coverage",
)

CORE_CONTROLS = {
    "task_id",
    "task_version",
    "task_digest",
    "workspace_input_digest",
    "context_identity",
    "verifier_identity",
}
UPLIFT_CONTROLS = CORE_CONTROLS | {
    "requested_model",
    "provider_route",
    "budget_identity",
    "network_policy",
}
UPLIFT_TREATMENTS = {"harness", "harness_version", "harness_profile_identity", "prompt_identity"}
MODEL_CONTROLS = CORE_CONTROLS | {
    "provider_route",
    "budget_identity",
    "network_policy",
    "harness",
    "harness_version",
    "harness_profile_identity",
    "prompt_identity",
}
MODEL_TREATMENTS = {"requested_model", "observed_model"}


class ComparabilityEngine:
    """Pure, deterministic assessment. It never infers absent identities."""

    def assess(
        self,
        left: ComparisonFacts,
        right: ComparisonFacts,
        *,
        intent: ComparabilityIntent,
    ) -> ComparabilityReport:
        if intent is ComparabilityIntent.HARNESS_UPLIFT:
            controls, treatments = UPLIFT_CONTROLS, UPLIFT_TREATMENTS
        elif intent is ComparabilityIntent.MODEL_COMPARISON:
            controls, treatments = MODEL_CONTROLS, MODEL_TREATMENTS
        else:
            controls, treatments = CORE_CONTROLS, set()
        fields: list[FieldComparison] = []
        reasons: list[ComparabilityReason] = []
        for name in FIELDS:
            left_value = getattr(left, name)
            right_value = getattr(right, name)
            if left_value is None or right_value is None:
                state = FieldState.MISSING
            elif left_value == right_value:
                state = FieldState.MATCH
            elif name in treatments:
                state = FieldState.INTENDED_DIFFERENCE
            else:
                state = FieldState.DIFFER
            fields.append(
                FieldComparison(field=name, left=left_value, right=right_value, state=state)
            )
            if state is FieldState.MISSING:
                if name == "observed_model":
                    reasons.append(
                        ComparabilityReason(
                            code=ReasonCode.OBSERVED_MODEL_MISSING,
                            severity=ReasonSeverity.PARTIAL,
                            field=name,
                            detail=(
                                "At least one harness did not expose the observed model identity."
                            ),
                        )
                    )
                elif name in controls:
                    reasons.append(
                        ComparabilityReason(
                            code=ReasonCode.HARD_CONTROL_MISSING,
                            severity=ReasonSeverity.BLOCKING,
                            field=name,
                            detail=(
                                "A required control identity is absent; a strong claim is blocked."
                            ),
                        )
                    )
                elif name == "trace_coverage":
                    reasons.append(
                        ComparabilityReason(
                            code=ReasonCode.TRACE_COVERAGE_LIMITED,
                            severity=ReasonSeverity.PARTIAL,
                            field=name,
                            detail=(
                                "Trace-dependent attribution is limited by missing "
                                "coverage evidence."
                            ),
                        )
                    )
                elif intent is ComparabilityIntent.GENERAL:
                    reasons.append(
                        ComparabilityReason(
                            code=ReasonCode.GENERAL_EVIDENCE_GAP,
                            severity=ReasonSeverity.PARTIAL,
                            field=name,
                            detail="The evidence omits this identity.",
                        )
                    )
            elif state is FieldState.DIFFER:
                if name == "observed_model":
                    reasons.append(
                        ComparabilityReason(
                            code=ReasonCode.OBSERVED_MODEL_MISMATCH,
                            severity=ReasonSeverity.BLOCKING,
                            field=name,
                            detail="Observed model identities differ.",
                        )
                    )
                elif name in controls:
                    reasons.append(
                        ComparabilityReason(
                            code=ReasonCode.HARD_CONTROL_MISMATCH,
                            severity=ReasonSeverity.BLOCKING,
                            field=name,
                            detail="Required control identities differ.",
                        )
                    )
                elif name == "trace_coverage":
                    reasons.append(
                        ComparabilityReason(
                            code=ReasonCode.TRACE_COVERAGE_LIMITED,
                            severity=ReasonSeverity.PARTIAL,
                            field=name,
                            detail=(
                                "Final correctness remains usable, but trace attribution "
                                "is partial."
                            ),
                        )
                    )
                else:
                    reasons.append(
                        ComparabilityReason(
                            code=ReasonCode.GENERAL_EVIDENCE_GAP,
                            severity=ReasonSeverity.PARTIAL,
                            field=name,
                            detail="This non-control identity differs.",
                        )
                    )
            elif state is FieldState.INTENDED_DIFFERENCE:
                reasons.append(
                    ComparabilityReason(
                        code=ReasonCode.INTENDED_TREATMENT_DIFFERENCE,
                        severity=ReasonSeverity.INFORMATIONAL,
                        field=name,
                        detail="The difference is the declared treatment for this intent.",
                    )
                )
        if intent is ComparabilityIntent.HARNESS_UPLIFT:
            for side, facts in (("left", left), ("right", right)):
                if (
                    facts.requested_model is not None
                    and facts.observed_model is not None
                    and facts.requested_model != facts.observed_model
                ):
                    reasons.append(
                        ComparabilityReason(
                            code=ReasonCode.REQUESTED_OBSERVED_MISMATCH,
                            severity=ReasonSeverity.BLOCKING,
                            field="observed_model",
                            detail=(f"The {side} observed model differs from its requested model."),
                        )
                    )
        severities = {reason.severity for reason in reasons}
        if ReasonSeverity.BLOCKING in severities:
            status = ComparabilityStatus.NOT_COMPARABLE
        elif ReasonSeverity.PARTIAL in severities:
            status = ComparabilityStatus.PARTIALLY_COMPARABLE
        else:
            status = ComparabilityStatus.COMPARABLE
        return ComparabilityReport(
            intent=intent,
            status=status,
            left_evidence_identity=left.evidence_identity,
            right_evidence_identity=right.evidence_identity,
            fields=tuple(fields),
            reasons=tuple(reasons),
        )
