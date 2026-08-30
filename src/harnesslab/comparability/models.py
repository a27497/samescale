from __future__ import annotations

import json
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from harnesslab.contracts.common import Sha256Digest


class ComparabilityStatus(StrEnum):
    COMPARABLE = "COMPARABLE"
    PARTIALLY_COMPARABLE = "PARTIALLY_COMPARABLE"
    NOT_COMPARABLE = "NOT_COMPARABLE"


class ComparabilityIntent(StrEnum):
    HARNESS_UPLIFT = "HARNESS_UPLIFT"
    NATIVE_HARNESS_SYSTEM_COMPARISON = "NATIVE_HARNESS_SYSTEM_COMPARISON"
    MODEL_COMPARISON = "MODEL_COMPARISON"
    CONTROLLED_ABLATION = "CONTROLLED_ABLATION"
    GENERAL = "GENERAL"


class FieldState(StrEnum):
    MATCH = "MATCH"
    DIFFER = "DIFFER"
    INTENDED_DIFFERENCE = "INTENDED_DIFFERENCE"
    MISSING = "MISSING"


class ReasonSeverity(StrEnum):
    INFORMATIONAL = "INFORMATIONAL"
    PARTIAL = "PARTIAL"
    BLOCKING = "BLOCKING"


class ReasonCode(StrEnum):
    HARD_CONTROL_MISSING = "HARD_CONTROL_MISSING"
    HARD_CONTROL_MISMATCH = "HARD_CONTROL_MISMATCH"
    OBSERVED_MODEL_MISSING = "OBSERVED_MODEL_MISSING"
    OBSERVED_MODEL_MISMATCH = "OBSERVED_MODEL_MISMATCH"
    REQUESTED_MODEL_MISSING = "REQUESTED_MODEL_MISSING"
    REQUESTED_OBSERVED_MISMATCH = "REQUESTED_OBSERVED_MISMATCH"
    TRACE_COVERAGE_LIMITED = "TRACE_COVERAGE_LIMITED"
    INTENDED_TREATMENT_DIFFERENCE = "INTENDED_TREATMENT_DIFFERENCE"
    GENERAL_EVIDENCE_GAP = "GENERAL_EVIDENCE_GAP"
    VERIFIER_EXECUTION_MISMATCH = "VERIFIER_EXECUTION_MISMATCH"
    VERIFIER_CONTROL_EXECUTION_MISMATCH = "VERIFIER_CONTROL_EXECUTION_MISMATCH"
    RESOURCE_ENVELOPE_MISSING = "RESOURCE_ENVELOPE_MISSING"
    RESOURCE_ENVELOPE_MISMATCH = "RESOURCE_ENVELOPE_MISMATCH"
    OPERATOR_TRUSTED_ROUTE_MODEL_NOT_RUNTIME_EXPOSED = (
        "OPERATOR_TRUSTED_ROUTE_MODEL_NOT_RUNTIME_EXPOSED"
    )
    DECLARED_TREATMENT_MISSING = "DECLARED_TREATMENT_MISSING"
    DECLARED_TREATMENT_NOT_DIFFERENT = "DECLARED_TREATMENT_NOT_DIFFERENT"
    OBSERVED_MODEL_ASYMMETRIC = "OBSERVED_MODEL_ASYMMETRIC"


class ComparisonFacts(BaseModel):
    """Explicit identities extracted from one M-Lane or H-Lane manifest."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    evidence_identity: Sha256Digest
    task_id: str | None = None
    task_version: str | None = None
    task_digest: str | None = None
    workspace_input_digest: str | None = None
    context_identity: str | None = None
    # Legacy observed verifier identity retained for historical readers.
    verifier_identity: str | None = None
    verifier_control_identity: str | None = None
    verifier_execution_identity: str | None = None
    verifier_execution_status: Literal["EXECUTED", "NOT_EXECUTED"] | None = None
    verifier_control_execution_status: Literal["MATCH", "MISMATCH", "NOT_EXECUTED"] | None = None
    requested_model: str | None = None
    observed_model: str | None = None
    provider_route: str | None = None
    budget_identity: str | None = None
    resource_envelope_identity: str | None = None
    network_policy: str | None = None
    harness: str | None = None
    harness_version: str | None = None
    harness_profile_identity: str | None = None
    provider_config_identity: str | None = None
    harness_image_identity: str | None = None
    runner_contract: str | None = None
    credential_reference_identity: str | None = None
    tool_policy_identity: str | None = None
    mcp_policy_identity: str | None = None
    reasoning_effort: str | None = None
    prompt_identity: str | None = None
    trace_coverage: str | None = None

    @model_validator(mode="before")
    @classmethod
    def legacy_verifier_identity_remains_a_control(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        legacy = normalized.get("verifier_identity")
        if legacy is not None and normalized.get("verifier_control_identity") is None:
            normalized["verifier_control_identity"] = legacy
            normalized.setdefault("verifier_execution_identity", legacy)
            normalized.setdefault("verifier_execution_status", "EXECUTED")
            normalized.setdefault("verifier_control_execution_status", "MATCH")
        return normalized


class FieldComparison(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str
    left: str | None
    right: str | None
    state: FieldState


class ComparabilityReason(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: ReasonCode
    severity: ReasonSeverity
    field: str
    detail: str = Field(min_length=1, max_length=500)


class ComparabilityReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    intent: ComparabilityIntent
    status: ComparabilityStatus
    left_evidence_identity: Sha256Digest
    right_evidence_identity: Sha256Digest
    fields: tuple[FieldComparison, ...]
    reasons: tuple[ComparabilityReason, ...]

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    import hashlib

    return "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()
