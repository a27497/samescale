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
    "verifier_control_identity",
    "verifier_execution_identity",
    "verifier_execution_status",
    "verifier_control_execution_status",
    "requested_model",
    "observed_model",
    "provider_route",
    "budget_identity",
    "resource_envelope_identity",
    "network_policy",
    "harness",
    "harness_version",
    "harness_profile_identity",
    "provider_config_identity",
    "harness_image_identity",
    "runner_contract",
    "credential_reference_identity",
    "tool_policy_identity",
    "mcp_policy_identity",
    "reasoning_effort",
    "prompt_identity",
    "trace_coverage",
)

CORE_CONTROLS = {
    "task_id",
    "task_version",
    "task_digest",
    "workspace_input_digest",
    "context_identity",
    "verifier_control_identity",
}
UPLIFT_CONTROLS = CORE_CONTROLS | {
    "requested_model",
    "provider_route",
    "budget_identity",
    "resource_envelope_identity",
    "network_policy",
}
UPLIFT_TREATMENTS = {"harness", "harness_version", "harness_profile_identity", "prompt_identity"}
MODEL_CONTROLS = CORE_CONTROLS | {
    "provider_route",
    "budget_identity",
    "resource_envelope_identity",
    "network_policy",
    "harness",
    "harness_version",
    "harness_profile_identity",
    "prompt_identity",
}
MODEL_TREATMENTS = {"requested_model", "observed_model"}
NATIVE_SYSTEM_CONTROLS = CORE_CONTROLS | {
    "requested_model",
    "provider_route",
    "network_policy",
}
NATIVE_SYSTEM_TREATMENTS = UPLIFT_TREATMENTS | {
    "budget_identity",
    "resource_envelope_identity",
}
CONTROLLED_ABLATION_CONTROLS = {
    "task_id",
    "task_version",
    "task_digest",
    "workspace_input_digest",
    "context_identity",
    "verifier_control_identity",
    "verifier_execution_identity",
    "verifier_execution_status",
    "verifier_control_execution_status",
    "requested_model",
    "provider_route",
    "provider_config_identity",
    "budget_identity",
    "resource_envelope_identity",
    "network_policy",
    "harness",
    "harness_version",
    "harness_profile_identity",
    "harness_image_identity",
    "runner_contract",
    "prompt_identity",
    "credential_reference_identity",
    "tool_policy_identity",
    "mcp_policy_identity",
    "trace_coverage",
}
CONTROLLED_ABLATION_TREATMENTS = {"reasoning_effort"}


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
        elif intent is ComparabilityIntent.NATIVE_HARNESS_SYSTEM_COMPARISON:
            controls, treatments = NATIVE_SYSTEM_CONTROLS, NATIVE_SYSTEM_TREATMENTS
        elif intent is ComparabilityIntent.MODEL_COMPARISON:
            controls, treatments = MODEL_CONTROLS, MODEL_TREATMENTS
        elif intent is ComparabilityIntent.CONTROLLED_ABLATION:
            controls, treatments = (
                CONTROLLED_ABLATION_CONTROLS,
                CONTROLLED_ABLATION_TREATMENTS,
            )
        else:
            controls, treatments = CORE_CONTROLS, set()
        fields: list[FieldComparison] = []
        reasons: list[ComparabilityReason] = []
        verifier_diagnostics = {
            "verifier_identity",
            "verifier_execution_identity",
            "verifier_execution_status",
            "verifier_control_execution_status",
        }
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
                if name == "resource_envelope_identity" and name in controls:
                    reasons.append(
                        ComparabilityReason(
                            code=ReasonCode.RESOURCE_ENVELOPE_MISSING,
                            severity=ReasonSeverity.BLOCKING,
                            field=name,
                            detail=(
                                "An explicitly scoped resource envelope is required for "
                                "a resource-normalized claim."
                            ),
                        )
                    )
                elif name == "requested_model" and intent is ComparabilityIntent.MODEL_COMPARISON:
                    reasons.append(
                        ComparabilityReason(
                            code=ReasonCode.REQUESTED_MODEL_MISSING,
                            severity=ReasonSeverity.BLOCKING,
                            field=name,
                            detail=("A requested model identity is required for model comparison."),
                        )
                    )
                elif (
                    name == "observed_model"
                    and intent is not ComparabilityIntent.CONTROLLED_ABLATION
                ):
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
                elif name == "verifier_identity" or (
                    name in verifier_diagnostics
                    and intent is not ComparabilityIntent.CONTROLLED_ABLATION
                ):
                    pass
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
                if name == "resource_envelope_identity" and name in controls:
                    reasons.append(
                        ComparabilityReason(
                            code=ReasonCode.RESOURCE_ENVELOPE_MISMATCH,
                            severity=ReasonSeverity.BLOCKING,
                            field=name,
                            detail="Scoped resource envelopes differ.",
                        )
                    )
                elif name == "observed_model":
                    reasons.append(
                        ComparabilityReason(
                            code=ReasonCode.OBSERVED_MODEL_MISMATCH,
                            severity=ReasonSeverity.BLOCKING,
                            field=name,
                            detail="Observed model identities differ.",
                        )
                    )
                elif name == "verifier_identity" or (
                    name in verifier_diagnostics
                    and intent is not ComparabilityIntent.CONTROLLED_ABLATION
                ):
                    pass
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
        for side, facts in (("left", left), ("right", right)):
            if facts.verifier_control_execution_status == "MISMATCH":
                reasons.append(
                    ComparabilityReason(
                        code=ReasonCode.VERIFIER_CONTROL_EXECUTION_MISMATCH,
                        severity=ReasonSeverity.BLOCKING,
                        field="verifier_control_execution_status",
                        detail=(f"The {side} executed verifier disagrees with its frozen control."),
                    )
                )
        if (
            left.verifier_execution_identity is not None
            and right.verifier_execution_identity is not None
            and left.verifier_execution_identity != right.verifier_execution_identity
        ):
            reasons.append(
                ComparabilityReason(
                    code=ReasonCode.VERIFIER_EXECUTION_MISMATCH,
                    severity=ReasonSeverity.BLOCKING,
                    field="verifier_execution_identity",
                    detail="Executed verifier identities differ.",
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
        if intent is ComparabilityIntent.CONTROLLED_ABLATION:
            if left.reasoning_effort is None or right.reasoning_effort is None:
                reasons.append(
                    ComparabilityReason(
                        code=ReasonCode.DECLARED_TREATMENT_MISSING,
                        severity=ReasonSeverity.BLOCKING,
                        field="reasoning_effort",
                        detail="The declared reasoning-effort treatment identity is absent.",
                    )
                )
            elif left.reasoning_effort == right.reasoning_effort:
                reasons.append(
                    ComparabilityReason(
                        code=ReasonCode.DECLARED_TREATMENT_NOT_DIFFERENT,
                        severity=ReasonSeverity.BLOCKING,
                        field="reasoning_effort",
                        detail="The declared reasoning-effort treatment did not differ.",
                    )
                )
            for side, facts in (("left", left), ("right", right)):
                if (
                    facts.observed_model is not None
                    and facts.requested_model is not None
                    and facts.observed_model != facts.requested_model
                ):
                    reasons.append(
                        ComparabilityReason(
                            code=ReasonCode.REQUESTED_OBSERVED_MISMATCH,
                            severity=ReasonSeverity.BLOCKING,
                            field="observed_model",
                            detail=f"The {side} observed model conflicts with its frozen model.",
                        )
                    )
            if left.observed_model is None and right.observed_model is None:
                reasons.append(
                    ComparabilityReason(
                        code=(ReasonCode.OPERATOR_TRUSTED_ROUTE_MODEL_NOT_RUNTIME_EXPOSED),
                        severity=ReasonSeverity.INFORMATIONAL,
                        field="observed_model",
                        detail=(
                            "Association under the same frozen operator-trusted route and "
                            "configuration; runtime model identity was not exposed, so this is "
                            "not an independently proven first-party model-level causal claim."
                        ),
                    )
                )
            elif (left.observed_model is None) != (right.observed_model is None):
                reasons.append(
                    ComparabilityReason(
                        code=ReasonCode.OBSERVED_MODEL_ASYMMETRIC,
                        severity=ReasonSeverity.BLOCKING,
                        field="observed_model",
                        detail="Observed-model exposure is asymmetric across the ablation pair.",
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


def capability_pair_eligible(report: ComparabilityReport) -> bool:
    """Allow controlled partial evidence while excluding every blocking comparison."""

    return all(reason.severity is not ReasonSeverity.BLOCKING for reason in report.reasons)
