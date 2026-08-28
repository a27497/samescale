from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.common import Sha256Digest
from harnesslab.tasks.models import EvidenceManifest, TaskValidationResult
from harnesslab.tasks.validation import validate_task_package


class TaskHealthError(ValueError):
    """Repeated baseline/oracle health evidence is not deterministic and valid."""


class TaskHealthAttestation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str
    task_version: str
    task_digest: Sha256Digest
    verifier_health_repeats: int = Field(ge=1)
    oracle_health_repeats: int = Field(ge=1)
    baseline_expected: str = "FAIL"
    oracle_expected: str = "PASS"
    baseline_terminal_identity: Sha256Digest
    oracle_terminal_identity: Sha256Digest
    deterministic: bool
    valid: bool


def _terminal_facts(evidence: EvidenceManifest) -> dict[str, Any]:
    result = evidence.result.model_dump(mode="json", exclude={"duration_ms"})
    return {
        "task_id": evidence.task_id,
        "task_version": evidence.task_version,
        "task_digest": evidence.task_digest,
        "workspace_digest": evidence.workspace_digest,
        "verifier": evidence.verifier.model_dump(mode="json"),
        "run_kind": evidence.run_kind,
        "result": result,
    }


def _validate_repeated_results(
    results: tuple[TaskValidationResult, ...], repeats: int
) -> TaskHealthAttestation:
    first = results[0]
    baseline_identities = tuple(
        canonical_digest(_terminal_facts(item.baseline)) for item in results
    )
    oracle_identities = tuple(canonical_digest(_terminal_facts(item.oracle)) for item in results)
    deterministic = len(set(baseline_identities)) == 1 and len(set(oracle_identities)) == 1
    valid = (
        deterministic
        and all(item.valid for item in results)
        and all(not item.baseline.result.passed for item in results)
        and all(item.oracle.result.passed for item in results)
    )
    return TaskHealthAttestation(
        task_id=first.task_id,
        task_version=first.task_version,
        task_digest=first.task_digest,
        verifier_health_repeats=repeats,
        oracle_health_repeats=repeats,
        baseline_terminal_identity=baseline_identities[0],
        oracle_terminal_identity=oracle_identities[0],
        deterministic=deterministic,
        valid=valid,
    )


def validate_task_health(path: Path, *, repeats: int = 5) -> TaskHealthAttestation:
    """Run keyless baseline-fail/oracle-pass validation repeatedly and attest stability."""

    if repeats < 1:
        raise ValueError("task health repeats must be positive")
    results = tuple(validate_task_package(path) for _ in range(repeats))
    attestation = _validate_repeated_results(results, repeats)
    if not attestation.valid:
        raise TaskHealthError(
            "task failed repeated baseline/oracle polarity or deterministic terminal health"
        )
    return attestation
