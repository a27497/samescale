from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from harnesslab.egress import preflight_egress_network_isolation
from harnesslab.release.evidence import SafeCallFacts, summarize_call_artifact
from harnesslab.release.smoke import (
    EXPECTED_CALL_IDS,
    ProductionSmokeInvoker,
    ResolvedSmokeBinding,
    SmokeCallFailure,
    SmokeCallResult,
    SmokeControlPlane,
    SmokeControlPlaneError,
    SmokeExecutionReceipt,
    SmokeFailureCategory,
    SmokeInvoker,
    resolve_runtime_identities,
)
from harnesslab.sandbox.artifacts import sha256_file
from harnesslab.tasks.package import digest_tree


class ComponentDiagnosticError(SmokeControlPlaneError):
    """The bounded non-release component sweep cannot execute safely."""


class DiagnosticCallRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    call_id: str
    requested_model: str
    outcome: str
    failure_category: SmokeFailureCategory | None = None
    evidence_digest_domain: Literal["ARTIFACT_TREE_DIGEST", "RAW_FILE_SHA256"] | None = None
    evidence_digest: str | None = None
    egress_attestation_digest_count: int = Field(default=0, ge=0)
    facts: SafeCallFacts | None = None


class ComponentDiagnosticReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    evidence_class: Literal["DIAGNOSTIC_ONLY"] = "DIAGNOSTIC_ONLY"
    release_promotable: Literal[False] = False
    plan_id: str
    smoke_plan_digest: str
    release_plan_digest: str
    attempt_receipt_reference: str
    smoke_attempted_call_ids: tuple[str, ...]
    diagnostic_call_ids: tuple[str, ...]
    diagnostic_top_level_launches: int = Field(ge=0, le=8)
    retry_count: Literal[0] = 0
    fallback_count: Literal[0] = 0
    status: Literal["IN_PROGRESS", "COMPLETE"] = "COMPLETE"
    results: tuple[DiagnosticCallRecord, ...]

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    def candidate_history_summary(self, source_commit: str) -> dict[str, object]:
        if self.status != "COMPLETE":
            raise ComponentDiagnosticError("diagnostic report is not complete")
        return {
            "schema_version": 1,
            "diagnostic_id": f"{self.plan_id}-attempt-1-diagnostic",
            "source_commit": source_commit,
            "evidence_class": self.evidence_class,
            "release_promotable": self.release_promotable,
            "plan_id": self.plan_id,
            "smoke_plan_digest": self.smoke_plan_digest,
            "release_plan_digest": self.release_plan_digest,
            "status": self.status,
            "smoke_attempted_call_ids": list(self.smoke_attempted_call_ids),
            "diagnostic_top_level_launches": self.diagnostic_top_level_launches,
            "retry_count": self.retry_count,
            "fallback_count": self.fallback_count,
            "calls": [item.model_dump(mode="json") for item in self.results],
            "release_state_effect": "NONE",
        }


def summarize_component_diagnostic_report(path: Path) -> ComponentDiagnosticReport:
    try:
        return ComponentDiagnosticReport.model_validate_json(path.read_bytes())
    except (OSError, ValidationError) as exc:
        raise ComponentDiagnosticError("invalid component diagnostic report") from exc


def _load_attempt_receipt(path: Path, control: SmokeControlPlane) -> SmokeExecutionReceipt:
    try:
        receipt = SmokeExecutionReceipt.model_validate_json(path.read_bytes())
    except (OSError, ValidationError) as exc:
        raise ComponentDiagnosticError("invalid skip-attempted SmokeExecutionReceipt") from exc
    if (
        receipt.plan_id != control.smoke_plan.plan_id
        or receipt.smoke_plan_digest != control.smoke_plan_digest
        or receipt.release_plan_digest != control.release_plan.digest
    ):
        raise ComponentDiagnosticError("skip-attempted receipt uses the wrong frozen plan")
    if receipt.status.value != "ABORTED":
        raise ComponentDiagnosticError("only an aborted smoke can have diagnostic continuation")
    attempted = EXPECTED_CALL_IDS[: receipt.attempted_top_level_launches]
    if receipt.failing_call_id is not None and (
        not attempted or receipt.failing_call_id != attempted[-1]
    ):
        raise ComponentDiagnosticError("skip-attempted receipt violates frozen call order")
    if tuple(result.call_id for result in receipt.results) != attempted[: len(receipt.results)]:
        raise ComponentDiagnosticError("skip-attempted receipt result sequence drifted")
    return receipt


def _artifact_record(
    binding: ResolvedSmokeBinding,
    result: SmokeCallResult,
    failure: SmokeFailureCategory | None,
) -> DiagnosticCallRecord:
    references = tuple(
        reference
        for reference in result.evidence_references
        if not reference.startswith(("egress-proxy:", "egress-network:"))
    )
    if len(references) != 1 or not result.evidence_digests:
        raise ComponentDiagnosticError("diagnostic result lacks one authoritative artifact")
    artifact = Path(references[0]).resolve()
    if artifact.is_dir():
        domain: Literal["ARTIFACT_TREE_DIGEST", "RAW_FILE_SHA256"] = "ARTIFACT_TREE_DIGEST"
        digest = digest_tree(artifact)
    elif artifact.is_file():
        domain = "RAW_FILE_SHA256"
        digest = sha256_file(artifact)
    else:
        raise ComponentDiagnosticError("diagnostic artifact is unavailable")
    if digest != result.evidence_digests[0]:
        raise ComponentDiagnosticError("diagnostic artifact digest mismatch")
    facts = summarize_call_artifact(result.call_id, artifact)
    return DiagnosticCallRecord(
        call_id=result.call_id,
        requested_model=binding.frozen.call.requested_model,
        outcome=facts.outcome or ("SUCCEEDED" if failure is None else "FAILED"),
        failure_category=failure,
        evidence_digest_domain=domain,
        evidence_digest=digest,
        egress_attestation_digest_count=max(0, len(result.evidence_digests) - 1),
        facts=facts,
    )


def _persist_report(path: Path, report: ComponentDiagnosticReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as file:
        file.write(report.canonical_json() + "\n")
        temporary = Path(file.name)
    os.replace(temporary, path)


async def execute_component_diagnostics(
    control: SmokeControlPlane,
    bindings: Sequence[ResolvedSmokeBinding],
    invoker: SmokeInvoker,
    *,
    attempt_receipt_path: Path,
    artifact_root: Path,
) -> ComponentDiagnosticReport:
    receipt = _load_attempt_receipt(attempt_receipt_path, control)
    attempted = EXPECTED_CALL_IDS[: receipt.attempted_top_level_launches]
    attempted_set = set(attempted)
    remaining = EXPECTED_CALL_IDS[receipt.attempted_top_level_launches :]
    if not remaining:
        raise ComponentDiagnosticError("complete smoke has no unattempted diagnostic calls")
    by_id = {binding.frozen.call.call_id: binding for binding in bindings}
    if tuple(by_id) != EXPECTED_CALL_IDS or len(by_id) != 8:
        raise ComponentDiagnosticError("diagnostic executor received mutated frozen bindings")
    records: list[DiagnosticCallRecord] = []
    output = artifact_root.resolve()
    report_path = output / "component-diagnostic-report.json"
    for call_id in remaining:
        if call_id in attempted_set:
            raise ComponentDiagnosticError("diagnostic attempted to repeat an Attempt-13 call")
        binding = by_id[call_id]
        try:
            result = await invoker.invoke(binding)
            if result.call_id != call_id:
                raise ComponentDiagnosticError("diagnostic result identity mismatch")
            record = _artifact_record(binding, result, None)
        except SmokeCallFailure as exc:
            if exc.evidence_result is None:
                record = DiagnosticCallRecord(
                    call_id=call_id,
                    requested_model=binding.frozen.call.requested_model,
                    outcome="FAILED_WITHOUT_ARTIFACT",
                    failure_category=exc.category,
                )
            else:
                record = _artifact_record(binding, exc.evidence_result, exc.category)
        except ComponentDiagnosticError:
            raise
        except Exception:
            record = DiagnosticCallRecord(
                call_id=call_id,
                requested_model=binding.frozen.call.requested_model,
                outcome="INFRASTRUCTURE_ERROR",
                failure_category=SmokeFailureCategory.INFRASTRUCTURE,
            )
        records.append(record)
        partial = ComponentDiagnosticReport(
            plan_id=control.smoke_plan.plan_id,
            smoke_plan_digest=control.smoke_plan_digest,
            release_plan_digest=control.release_plan.digest,
            attempt_receipt_reference=attempt_receipt_path.name,
            smoke_attempted_call_ids=attempted,
            diagnostic_call_ids=tuple(item.call_id for item in records),
            diagnostic_top_level_launches=len(records),
            status="IN_PROGRESS",
            results=tuple(records),
        )
        _persist_report(report_path, partial)
    if len(attempted_set | {record.call_id for record in records}) > 8:
        raise ComponentDiagnosticError("unique frozen call bound was exceeded")
    complete = ComponentDiagnosticReport(
        plan_id=control.smoke_plan.plan_id,
        smoke_plan_digest=control.smoke_plan_digest,
        release_plan_digest=control.release_plan.digest,
        attempt_receipt_reference=attempt_receipt_path.name,
        smoke_attempted_call_ids=attempted,
        diagnostic_call_ids=tuple(item.call_id for item in records),
        diagnostic_top_level_launches=len(records),
        results=tuple(records),
    )
    _persist_report(report_path, complete)
    return complete


async def execute_real_component_diagnostics(
    repository_root: Path,
    *,
    allow_real_diagnostic: bool,
    attempt_receipt_path: Path,
    artifact_root: Path,
    environment: Mapping[str, str] | None = None,
    plan_version: str = "v2",
) -> ComponentDiagnosticReport:
    if not allow_real_diagnostic:
        raise ComponentDiagnosticError("real diagnostic requires --allow-real-diagnostic")
    selected_environment = environment if environment is not None else os.environ
    control = SmokeControlPlane.load(repository_root, plan_version=plan_version)
    control.validate_real_environment(selected_environment)
    await preflight_egress_network_isolation()
    runtime = await resolve_runtime_identities()
    bindings = control.resolve_real_bindings(selected_environment, runtime)
    invoker = ProductionSmokeInvoker(
        repository_root,
        selected_environment,
        artifact_root,
        smoke_plan_id=control.smoke_plan.plan_id,
    )
    return await execute_component_diagnostics(
        control,
        bindings,
        invoker,
        attempt_receipt_path=attempt_receipt_path,
        artifact_root=artifact_root,
    )
