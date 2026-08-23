from __future__ import annotations

import json
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from harnesslab.contracts.common import Sha256Digest


class ComparabilityStatus(StrEnum):
    COMPARABLE = "COMPARABLE"
    PARTIALLY_COMPARABLE = "PARTIALLY_COMPARABLE"
    NOT_COMPARABLE = "NOT_COMPARABLE"


class ComparabilityIntent(StrEnum):
    HARNESS_UPLIFT = "HARNESS_UPLIFT"
    MODEL_COMPARISON = "MODEL_COMPARISON"
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
    verifier_identity: str | None = None
    requested_model: str | None = None
    observed_model: str | None = None
    provider_route: str | None = None
    budget_identity: str | None = None
    network_policy: str | None = None
    harness: str | None = None
    harness_version: str | None = None
    harness_profile_identity: str | None = None
    prompt_identity: str | None = None
    trace_coverage: str | None = None


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
