from __future__ import annotations

import os
import tempfile
from pathlib import Path

from pydantic import ValidationError

from harnesslab.analyst.models import (
    AnalysisRequest,
    AnalysisScope,
    AttributionDraft,
    AttributionReport,
    ClaimClass,
    EvidenceEntry,
    ExecutionMetadata,
    ExecutionStatus,
    FactAssertion,
    FactOperator,
    VerifiedFact,
    canonical_fact_statement,
    canonical_json_value,
    fact_evidence_refs,
    resolve_fact_assertion,
)


class AttributionValidationError(ValueError):
    """A draft contains fabricated citations or unsupported structured facts."""


def _validate_assertion(assertion: FactAssertion, entry: EvidenceEntry) -> None:
    try:
        actual = resolve_fact_assertion(assertion, entry)
    except ValueError as exc:
        raise AttributionValidationError(str(exc)) from exc
    if assertion.operator is not FactOperator.EQ:
        raise AttributionValidationError("unsupported fact assertion operator")
    if canonical_json_value(actual) != canonical_json_value(assertion.expected_value):
        raise AttributionValidationError(
            "fact assertion expected value contradicts the cited evidence"
        )


def validate_and_build_report(
    *,
    request: AnalysisRequest,
    scope: AnalysisScope,
    draft: AttributionDraft,
    catalog: tuple[EvidenceEntry, ...],
    status: ExecutionStatus,
    decision_iterations: int,
    tool_calls: int,
) -> AttributionReport:
    ids = tuple(entry.ref.id for entry in catalog)
    if len(ids) != len(set(ids)):
        raise AttributionValidationError("evidence catalog contains duplicate identities")
    by_id = {entry.ref.id: entry for entry in catalog}
    known = set(by_id)
    verified: list[VerifiedFact] = []
    hypotheses = []
    for claim in draft.claims:
        if claim.classification is ClaimClass.VERIFIED_FACT:
            missing = {assertion.evidence_ref for assertion in claim.assertions} - known
            if missing:
                raise AttributionValidationError("claim cites evidence absent from the catalog")
            for assertion in claim.assertions:
                _validate_assertion(assertion, by_id[assertion.evidence_ref])
            verified.append(
                VerifiedFact(
                    statement=canonical_fact_statement(claim.assertions),
                    evidence_refs=fact_evidence_refs(claim.assertions),
                    assertions=claim.assertions,
                )
            )
        else:
            missing = set(claim.evidence_refs) - known
            if missing:
                raise AttributionValidationError("claim cites evidence absent from the catalog")
            hypotheses.append(claim)
    if any(ref not in known or not ref.startswith("ablation:") for ref in draft.ablation_refs):
        raise AttributionValidationError(
            "ablation reference is missing or not an ablation identity"
        )
    return AttributionReport(
        analysis_id=request.analysis_id,
        source_experiment_id=request.experiment_id,
        source_plan_digest=scope.plan_digest,
        analysis_question=request.question,
        execution=ExecutionMetadata(
            status=status,
            decision_iterations=decision_iterations,
            tool_calls=tool_calls,
        ),
        summary=draft.summary,
        evidence_catalog=catalog,
        verified_facts=tuple(verified),
        hypotheses=tuple(hypotheses),
        ablation_refs=draft.ablation_refs,
        limitations=draft.limitations,
    )


def persist_report(report: AttributionReport, artifact_root: Path) -> tuple[Path, Path]:
    """Atomically persist only the validated Analyst report under its deterministic identity."""

    try:
        report = AttributionReport.model_validate(report.model_dump(mode="python"))
    except ValidationError as exc:
        raise AttributionValidationError(
            "report failed structured fact binding revalidation"
        ) from exc
    artifact_root.mkdir(parents=True, exist_ok=True)
    resolved_root = artifact_root.resolve(strict=True)
    target = resolved_root / report.analysis_id
    if target.exists() and target.is_symlink():
        raise AttributionValidationError("analysis artifact directory cannot be a symlink")
    target.mkdir(mode=0o750, exist_ok=True)
    resolved_target = target.resolve(strict=True)
    if resolved_root not in resolved_target.parents:
        raise AttributionValidationError("analysis artifact directory escapes its trusted root")
    json_path = resolved_target / "report.json"
    markdown_path = resolved_target / "report.md"
    _atomic_write(json_path, report.canonical_json() + "\n")
    _atomic_write(markdown_path, report.markdown())
    return json_path, markdown_path


def _atomic_write(path: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
