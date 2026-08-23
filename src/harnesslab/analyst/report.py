from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from harnesslab.analyst.models import (
    AnalysisRequest,
    AnalysisScope,
    AttributionDraft,
    AttributionReport,
    ClaimClass,
    EvidenceEntry,
    ExecutionMetadata,
    ExecutionStatus,
)


class AttributionValidationError(ValueError):
    """A draft contains fabricated citations or violates the fact/hypothesis boundary."""


_CAUSAL_WORDING = re.compile(
    r"(?i)\b(?:because|caused?|causal(?:ly)?|due to|led to|resulted from|attribut(?:e|ed|ion))\b"
)
_EXECUTION_WORDING = re.compile(
    r"(?i)\b(?:command executed|command ran|shell ran|provider called|browser opened|tool added)\b"
)


def _execution_fact_is_supported(
    statement: str, evidence_refs: tuple[str, ...], catalog: dict[str, EvidenceEntry]
) -> bool:
    if not _EXECUTION_WORDING.search(statement):
        return True
    for ref in evidence_refs:
        entry = catalog[ref]
        trace = entry.data_by_tool.get("inspect_trace")
        if trace is not None and trace.get("type") == "COMMAND_EXECUTION":
            return True
    return False


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
    verified = []
    hypotheses = []
    for claim in draft.claims:
        missing = set(claim.evidence_refs) - known
        if missing:
            raise AttributionValidationError("claim cites evidence absent from the catalog")
        if claim.classification is ClaimClass.VERIFIED_FACT:
            if _CAUSAL_WORDING.search(claim.statement):
                raise AttributionValidationError(
                    "causal language cannot be emitted as a VERIFIED_FACT"
                )
            if not _execution_fact_is_supported(claim.statement, claim.evidence_refs, by_id):
                raise AttributionValidationError(
                    "cited evidence does not support the factual execution statement"
                )
            verified.append(claim)
        else:
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
