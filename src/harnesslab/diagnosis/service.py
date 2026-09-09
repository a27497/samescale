from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from harnesslab.db.models.experiment import ExperimentRecord, ExperimentRunRecord
from harnesslab.diagnosis.models import (
    Attribution,
    AttributionKind,
    BadCase,
    BadCaseExport,
    BadCaseExportRequest,
    CausalStrength,
    CellDiagnosis,
    DiagnosisInput,
    DiagnosisReport,
    DiagnosisRun,
    EvidenceOrigin,
    FailureClass,
    FailureCluster,
    FailureScope,
    TaskFamilyDiagnosis,
    ToolCallEvidence,
    TraceEventEvidence,
    TraceEvidence,
    VerifierEvidence,
    WorkspaceDiffEvidence,
    WorkspacePathEvidence,
)
from harnesslab.evidence.reader import (
    EvidenceReadError,
    load_normalized_trace,
    load_verified_manifest,
)
from harnesslab.experiment.plan import AnyExperimentPlan, load_experiment_plan_payload
from harnesslab.experiment.tool_metrics import manifest_tool_calls
from harnesslab.tasks.package import TaskPackage, TaskPackageError

CLUSTER_DIMENSIONS = (
    "model",
    "harness",
    "task",
    "language",
    "task_family",
    "failure_class",
    "failure_scope",
    "trace_pattern",
    "tool_pattern",
    "workspace_diff_pattern",
)


class DiagnosisEvidenceError(RuntimeError):
    """Immutable evidence or frozen task metadata could not be verified."""


class DiagnosisRequestError(ValueError):
    """A BadCase export request references evidence outside its diagnosis report."""


def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _scope(item: DiagnosisInput) -> FailureScope:
    return (
        FailureScope.CAPABILITY
        if item.normalized_outcome == "capability_fail"
        else FailureScope.INFRASTRUCTURE
    )


def _failure_class(item: DiagnosisInput) -> FailureClass:
    if item.declared_failure_class is not None:
        return item.declared_failure_class
    if not item.artifact_available:
        return FailureClass.ARTIFACT_FAILURE
    if item.provider_failure is not None:
        return (
            FailureClass.TIMEOUT
            if item.provider_failure.lower() == "timeout"
            else FailureClass.PROVIDER_FAILURE
        )
    if item.harness_failure is not None:
        category = item.harness_failure.lower()
        if category in {"timeout", "execution_budget_exhausted"}:
            return FailureClass.TIMEOUT
        if category == "artifact_error":
            return FailureClass.ARTIFACT_FAILURE
        return FailureClass.HARNESS_PROTOCOL_FAILURE
    if item.verifier.failure_subtype is not None:
        subtype = item.verifier.failure_subtype.upper()
        if "TIMEOUT" in subtype:
            return FailureClass.TIMEOUT
        if "ARTIFACT" in subtype or "CLEANUP" in subtype:
            return FailureClass.ARTIFACT_FAILURE
        return FailureClass.VERIFIER_FAILURE
    if item.verifier.sandbox_status in {"timeout"}:
        return FailureClass.TIMEOUT
    if item.verifier.sandbox_status in {"artifact_error", "cleanup_error"}:
        return FailureClass.ARTIFACT_FAILURE
    if item.verifier.sandbox_status in {"failed", "cancelled"}:
        return FailureClass.VERIFIER_FAILURE
    if item.workspace_diff.protected_paths_changed:
        return FailureClass.PROTECTED_FILE_MUTATION
    if item.workspace_diff.pattern == "no-modification":
        return FailureClass.NO_MODIFICATION
    if item.tool_calls.failed_exit_codes:
        return FailureClass.TOOL_FAILURE
    if item.verifier.status == "FAILED":
        return FailureClass.TEST_FAILURE
    return FailureClass.HARNESS_PROTOCOL_FAILURE


def _dimensions(item: DiagnosisInput, failure: FailureClass, scope: FailureScope) -> dict[str, str]:
    return {
        "model": item.model,
        "harness": item.harness,
        "task": item.task_id,
        "language": item.language,
        "task_family": item.task_family,
        "failure_class": failure.value,
        "failure_scope": scope.value,
        "trace_pattern": item.trace.pattern,
        "tool_pattern": item.tool_calls.pattern,
        "workspace_diff_pattern": item.workspace_diff.pattern,
    }


def _diagnosed_run(item: DiagnosisInput, *, ablation_supported: bool) -> DiagnosisRun:
    failure = _failure_class(item)
    scope = _scope(item)
    fact_refs = [f"run:{item.run_id}"]
    if item.artifact_available:
        fact_refs.append(f"trace:{item.trace.digest}" if item.trace.digest else "manifest:verified")
    else:
        fact_refs.append("artifact:not-reported")
    strength = (
        CausalStrength.CONTROLLED_ABLATION_ASSOCIATION
        if ablation_supported
        else CausalStrength.CORRELATION_ONLY
    )
    hypothesis = (
        "The failure pattern is associated with a preregistered controlled-ablation pair."
        if ablation_supported
        else "The shared trace, tool, and workspace patterns may help explain this failure cluster."
    )
    return DiagnosisRun(
        run_id=item.run_id,
        origin=item.origin,
        task_id=item.task_id,
        task_version=item.task_version,
        model=item.model,
        harness=item.harness,
        language=item.language,
        task_family=item.task_family,
        failure_class=failure,
        failure_scope=scope,
        artifact_verified=item.artifact_available and item.evidence_identity is not None,
        evidence_identity=item.evidence_identity,
        trace=item.trace,
        workspace_diff=item.workspace_diff,
        tool_calls=item.tool_calls,
        verifier=item.verifier,
        attributions=(
            Attribution(
                kind=AttributionKind.VERIFIED_FACT,
                statement=(
                    f"Structured evidence classifies this run as {failure.value} "
                    f"with {scope.value} scope."
                ),
                evidence_references=tuple(fact_refs),
                causal_strength=CausalStrength.NOT_APPLICABLE,
            ),
            Attribution(
                kind=AttributionKind.HYPOTHESIS,
                statement=hypothesis,
                evidence_references=(f"cluster-dimensions:{item.run_id}",),
                causal_strength=strength,
                caveat=(
                    "Controlled ablation strengthens association but does not by itself prove "
                    "causality."
                    if ablation_supported
                    else "Trace correlation is not causality; a controlled ablation is required "
                    "to strengthen attribution."
                ),
            ),
        ),
    )


def build_diagnosis_report(
    *,
    experiment_id: str,
    plan_digest: str,
    inputs: tuple[DiagnosisInput, ...],
    verified_ablation_contrast_run_ids: frozenset[str] = frozenset(),
) -> DiagnosisReport:
    """Build a stable drill-down tree without mutating or reinterpreting source evidence."""

    ordered_inputs = tuple(
        sorted(inputs, key=lambda item: (item.cell_id, item.task_family, item.run_id))
    )
    input_ids = {item.run_id for item in ordered_inputs}
    if not verified_ablation_contrast_run_ids <= input_ids:
        raise DiagnosisRequestError(
            "controlled-ablation contrast references an unknown diagnosed run"
        )
    grouped: dict[tuple[str, str, str], list[DiagnosisRun]] = defaultdict(list)
    cluster_dimensions: dict[tuple[str, str, str], dict[str, str]] = {}
    for item in ordered_inputs:
        run = _diagnosed_run(
            item,
            ablation_supported=item.run_id in verified_ablation_contrast_run_ids,
        )
        dimensions = _dimensions(item, run.failure_class, run.failure_scope)
        cluster_id = _digest(dimensions)
        key = (item.cell_id, item.task_family, cluster_id)
        grouped[key].append(run)
        cluster_dimensions[key] = dimensions

    by_cell: dict[str, dict[str, list[FailureCluster]]] = defaultdict(lambda: defaultdict(list))
    for key in sorted(grouped):
        cell_id, family, cluster_id = key
        runs = tuple(sorted(grouped[key], key=lambda item: item.run_id))
        first = runs[0]
        by_cell[cell_id][family].append(
            FailureCluster(
                cluster_id=cluster_id,
                dimensions=cluster_dimensions[key],
                failure_class=first.failure_class,
                failure_scope=first.failure_scope,
                run_count=len(runs),
                real_run_count=sum(
                    run.origin is EvidenceOrigin.IMMUTABLE_EXPERIMENT for run in runs
                ),
                synthetic_run_count=sum(
                    run.origin is EvidenceOrigin.SYNTHETIC_QUALIFICATION for run in runs
                ),
                runs=runs,
            )
        )
    cells = tuple(
        CellDiagnosis(
            cell_id=cell_id,
            task_families=tuple(
                TaskFamilyDiagnosis(
                    task_family=family,
                    clusters=tuple(sorted(clusters, key=lambda item: item.cluster_id)),
                )
                for family, clusters in sorted(families.items())
            ),
        )
        for cell_id, families in sorted(by_cell.items())
    )
    payload = {
        "schema_version": 1,
        "experiment_id": experiment_id,
        "plan_digest": plan_digest,
        "cluster_dimensions": CLUSTER_DIMENSIONS,
        "failure_run_count": len(ordered_inputs),
        "cells": [cell.model_dump(mode="json") for cell in cells],
    }
    return DiagnosisReport(
        experiment_id=experiment_id,
        plan_digest=plan_digest,
        report_digest=_digest(payload),
        cluster_dimensions=CLUSTER_DIMENSIONS,
        failure_run_count=len(ordered_inputs),
        real_run_count=sum(
            item.origin is EvidenceOrigin.IMMUTABLE_EXPERIMENT for item in ordered_inputs
        ),
        synthetic_run_count=sum(
            item.origin is EvidenceOrigin.SYNTHETIC_QUALIFICATION for item in ordered_inputs
        ),
        cells=cells,
    )


def _all_clusters(report: DiagnosisReport) -> tuple[FailureCluster, ...]:
    return tuple(
        cluster
        for cell in report.cells
        for family in cell.task_families
        for cluster in family.clusters
    )


def build_badcase_export(report: DiagnosisReport, request: BadCaseExportRequest) -> BadCaseExport:
    clusters = {cluster.cluster_id: cluster for cluster in _all_clusters(report)}
    requested = tuple(sorted(set(request.cluster_ids)))
    unknown = set(requested) - set(clusters)
    if unknown:
        raise DiagnosisRequestError("BadCase export references an unknown failure cluster")
    selected = tuple(clusters[item] for item in requested) if requested else _all_clusters(report)
    cases: list[BadCase] = []
    for cluster in sorted(selected, key=lambda item: item.cluster_id):
        for run in cluster.runs:
            if run.origin is EvidenceOrigin.IMMUTABLE_EXPERIMENT:
                eligible_real_badcase = (
                    run.failure_scope is FailureScope.CAPABILITY
                    and run.verifier.status == "FAILED"
                    and run.verifier.sandbox_status == "succeeded"
                    and run.artifact_verified
                    and run.evidence_identity is not None
                )
                if not eligible_real_badcase:
                    continue
            elif not request.include_synthetic_qualification:
                continue
            raw = {
                "report": report.report_digest,
                "cluster": cluster.cluster_id,
                "run": run.run_id,
                "origin": run.origin.value,
            }
            cases.append(
                BadCase(
                    case_id=_digest(raw),
                    run_id=run.run_id,
                    origin=run.origin,
                    cluster_id=cluster.cluster_id,
                    task_id=run.task_id,
                    task_version=run.task_version,
                    model=run.model,
                    harness=run.harness,
                    language=run.language,
                    task_family=run.task_family,
                    failure_class=run.failure_class,
                    failure_scope=run.failure_scope,
                    evidence_identity=run.evidence_identity
                    or _digest(
                        {
                            "origin": run.origin.value,
                            "run": run.run_id,
                            "qualification": "synthetic",
                        }
                    ),
                    identity_kind=(
                        "IMMUTABLE_EVIDENCE"
                        if run.origin is EvidenceOrigin.IMMUTABLE_EXPERIMENT
                        else "SYNTHETIC_QUALIFICATION"
                    ),
                    verifier_status=run.verifier.status,
                    verifier_score=run.verifier.score,
                    trace_pattern=run.trace.pattern,
                    tool_pattern=run.tool_calls.pattern,
                    workspace_diff_pattern=run.workspace_diff.pattern,
                    attribution_kinds=tuple(item.kind for item in run.attributions),
                )
            )
    ordered = tuple(sorted(cases, key=lambda item: (item.cluster_id, item.run_id)))
    payload = {
        "experiment_id": report.experiment_id,
        "source_report_digest": report.report_digest,
        "requested_cluster_ids": requested,
        "cases": [item.model_dump(mode="json") for item in ordered],
    }
    return BadCaseExport(
        experiment_id=report.experiment_id,
        source_report_digest=report.report_digest,
        export_digest=_digest(payload),
        requested_cluster_ids=requested,
        real_case_count=sum(item.origin is EvidenceOrigin.IMMUTABLE_EXPERIMENT for item in ordered),
        synthetic_qualification_case_count=sum(
            item.origin is EvidenceOrigin.SYNTHETIC_QUALIFICATION for item in ordered
        ),
        cases=ordered,
    )


def _safe_str(value: object, fallback: str) -> str:
    return value if isinstance(value, str) and value else fallback


def _trace_pattern(events: tuple[TraceEventEvidence, ...], coverage: str | None) -> str:
    counts: dict[str, int] = defaultdict(int)
    for event in events:
        counts[event.type] += 1
    types = ",".join(f"{key}:{counts[key]}" for key in sorted(counts)) or "none"
    failed = sum(event.exit_code not in {None, 0} for event in events)
    return f"coverage={coverage or 'NOT_REPORTED'};types={types};failed_commands={failed}"


def _workspace_diff(raw: dict[str, Any], protected: frozenset[str]) -> WorkspaceDiffEvidence:
    input_digest = raw.get("workspace_input_digest")
    output_digest = raw.get("workspace_output_digest")
    input_digest = input_digest if isinstance(input_digest, str) else None
    output_digest = output_digest if isinstance(output_digest, str) else None
    paths: list[WorkspacePathEvidence] = []
    changed = raw.get("changed_paths")
    if isinstance(changed, list):
        for item in changed:
            if not isinstance(item, dict):
                continue
            path = item.get("path")
            status = item.get("status")
            if isinstance(path, str) and path and isinstance(status, str) and status:
                paths.append(WorkspacePathEvidence(path=path, status=status))
    paths_tuple = tuple(sorted(paths, key=lambda item: (item.path, item.status)))
    protected_changed = tuple(
        sorted(
            item.path
            for item in paths_tuple
            if any(
                item.path == protected_path
                or item.path.startswith(protected_path.rstrip("/") + "/")
                for protected_path in protected
            )
        )
    )
    if input_digest is not None and input_digest == output_digest:
        pattern = "no-modification"
    elif paths_tuple:
        suffixes: dict[str, int] = defaultdict(int)
        statuses: dict[str, int] = defaultdict(int)
        for item in paths_tuple:
            suffixes[Path(item.path).suffix or "[no-extension]"] += 1
            statuses[item.status] += 1
        pattern = "paths=" + str(len(paths_tuple))
        pattern += ";statuses=" + ",".join(f"{key}:{statuses[key]}" for key in sorted(statuses))
        pattern += ";extensions=" + ",".join(f"{key}:{suffixes[key]}" for key in sorted(suffixes))
        if protected_changed:
            pattern += ";protected=true"
    elif input_digest is not None and output_digest is not None:
        pattern = "content-changed;paths-not-reported"
    else:
        pattern = "not-reported"
    status = "REPORTED" if paths_tuple else "DIGEST_ONLY" if input_digest else "NOT_REPORTED"
    return WorkspaceDiffEvidence(
        status=status,
        input_digest=input_digest,
        output_digest=output_digest,
        pattern=pattern,
        changed_paths=paths_tuple,
        protected_paths_changed=protected_changed,
    )


def _verifier(raw: dict[str, Any]) -> VerifierEvidence:
    passed = raw.get("verifier_passed")
    score = raw.get("verifier_score")
    manifest = raw.get("verifier_sandbox_manifest")
    sandbox_status: str | None = None
    if isinstance(manifest, dict):
        sandbox_status = manifest.get("status") if isinstance(manifest.get("status"), str) else None
    lifecycle = raw.get("verifier_lifecycle")
    subtype: str | None = None
    if isinstance(lifecycle, dict) and isinstance(lifecycle.get("failure_subtype"), str):
        subtype = lifecycle["failure_subtype"]
    status = (
        "PASSED"
        if passed is True
        else "FAILED"
        if passed is False
        else "NOT_RUN"
        if subtype
        else "NOT_REPORTED"
    )
    return VerifierEvidence(
        status=status,
        score=float(score)
        if isinstance(score, int | float) and not isinstance(score, bool)
        else None,
        sandbox_status=sandbox_status,
        failure_subtype=subtype,
    )


def _declared_failure(raw: dict[str, Any]) -> FailureClass | None:
    facts = raw.get("diagnosis_facts")
    if not isinstance(facts, dict) or not isinstance(facts.get("failure_class"), str):
        return None
    try:
        return FailureClass(facts["failure_class"])
    except ValueError:
        return None


def _task_metadata(
    plan: AnyExperimentPlan, repository_root: Path
) -> dict[str, tuple[str, str, frozenset[str]]]:
    result: dict[str, tuple[str, str, frozenset[str]]] = {}
    task_root = (repository_root / "tasks").resolve()
    for planned in plan.tasks:
        package_path = (repository_root / planned.package_path).resolve()
        if task_root not in package_path.parents:
            raise DiagnosisEvidenceError("planned task escapes the trusted task root")
        try:
            package = TaskPackage.load(package_path)
        except TaskPackageError as exc:
            raise DiagnosisEvidenceError("frozen task metadata cannot be verified") from exc
        if package.definition.content_digest != planned.task_digest:
            raise DiagnosisEvidenceError("frozen task identity does not match the experiment plan")
        metadata = package.definition.metadata
        result[planned.task_id] = (
            metadata.get("language", "unknown"),
            metadata.get("category", metadata.get("scenario_family", "unknown")),
            frozenset(package.manifest.protected_paths),
        )
    return result


async def diagnose_experiment(
    session: AsyncSession,
    experiment_id: str,
    artifact_roots: tuple[Path, ...],
    *,
    repository_root: Path,
) -> DiagnosisReport:
    record = await session.get(ExperimentRecord, experiment_id)
    if record is None:
        raise DiagnosisRequestError("experiment does not exist")
    try:
        plan = load_experiment_plan_payload(record.plan_json)
    except (ValidationError, ValueError) as exc:
        raise DiagnosisEvidenceError("experiment plan cannot be verified") from exc
    if plan.digest != record.plan_digest or plan.experiment_id != record.id:
        raise DiagnosisEvidenceError("experiment plan identity does not match")
    metadata = _task_metadata(plan, repository_root)
    all_runs = tuple(
        (
            await session.scalars(
                select(ExperimentRunRecord)
                .where(ExperimentRunRecord.experiment_id == experiment_id)
                .order_by(ExperimentRunRecord.slot_order)
            )
        ).all()
    )
    runs = tuple(
        run
        for run in all_runs
        if run.normalized_outcome is not None and run.normalized_outcome != "capability_pass"
    )
    inputs: list[DiagnosisInput] = []
    for run in runs:
        raw: dict[str, Any] = {}
        artifact_available = (
            run.artifact_manifest_path is not None and run.evidence_digest is not None
        )
        if artifact_available:
            try:
                raw = load_verified_manifest(run, artifact_roots).raw
            except EvidenceReadError as exc:
                raise DiagnosisEvidenceError("run artifact cannot be verified") from exc
        trace_events: tuple[TraceEventEvidence, ...] = ()
        trace_digest: str | None = None
        coverage = raw.get("trace_coverage") if isinstance(raw.get("trace_coverage"), str) else None
        if isinstance(raw.get("normalized_trace_digest"), str):
            try:
                trace, trace_digest, coverage = load_normalized_trace(run, artifact_roots)
            except EvidenceReadError as exc:
                raise DiagnosisEvidenceError("normalized trace cannot be verified") from exc
            trace_events = tuple(
                TraceEventEvidence(
                    ordinal=event.ordinal,
                    type=event.type.value,
                    status=event.status,
                    exit_code=event.exit_code,
                )
                for event in trace.events
            )
        trace_evidence = TraceEvidence(
            status="REPORTED" if trace_digest else "NOT_REPORTED",
            coverage=coverage,
            digest=trace_digest,
            pattern=_trace_pattern(trace_events, coverage),
            events=trace_events,
        )
        failed_codes = tuple(
            sorted(
                event.exit_code
                for event in trace_events
                if event.exit_code is not None and event.exit_code != 0
            )
        )
        tool_count = manifest_tool_calls(
            raw, Path(run.artifact_manifest_path) if run.artifact_manifest_path else None
        )
        tool_evidence = ToolCallEvidence(
            status="REPORTED" if tool_count is not None else "NOT_REPORTED",
            count=tool_count,
            pattern=(
                f"count={tool_count};failed={len(failed_codes)}"
                if tool_count is not None
                else "not-reported"
            ),
            failed_exit_codes=failed_codes,
        )
        language, family, protected = metadata.get(run.task_id, ("unknown", "unknown", frozenset()))
        slot = run.slot_json
        inputs.append(
            DiagnosisInput(
                run_id=run.run_id,
                origin=EvidenceOrigin.IMMUTABLE_EXPERIMENT,
                cell_id=run.cell_id,
                task_id=run.task_id,
                task_version=run.task_version,
                model=_safe_str(
                    raw.get("requested_model"), _safe_str(slot.get("requested_model"), "unknown")
                ),
                harness=_safe_str(raw.get("harness"), _safe_str(slot.get("harness"), run.lane)),
                language=language,
                task_family=family,
                normalized_outcome=run.normalized_outcome or "infra_failure",
                source_outcome=run.source_outcome,
                declared_failure_class=_declared_failure(raw),
                provider_failure=raw.get("provider_failure")
                if isinstance(raw.get("provider_failure"), str)
                else None,
                harness_failure=raw.get("harness_failure")
                if isinstance(raw.get("harness_failure"), str)
                else None,
                artifact_available=artifact_available,
                evidence_identity=run.evidence_digest if artifact_available else None,
                trace=trace_evidence,
                workspace_diff=_workspace_diff(raw, protected),
                tool_calls=tool_evidence,
                verifier=_verifier(raw),
            )
        )
    by_slot = {
        (run.cell_id, run.task_id, run.repeat_index): run
        for run in all_runs
        if run.normalized_outcome in {"capability_pass", "capability_fail"}
    }
    ablation_contrasts: set[str] = set()
    for ablation in plan.ablations:
        task_repeats = {
            (run.task_id, run.repeat_index)
            for run in all_runs
            if run.cell_id in {ablation.base_cell_id, ablation.variant_cell_id}
        }
        for task_id, repeat_index in task_repeats:
            base = by_slot.get((ablation.base_cell_id, task_id, repeat_index))
            variant = by_slot.get((ablation.variant_cell_id, task_id, repeat_index))
            if base is None or variant is None:
                continue
            if (
                base.normalized_outcome == "capability_fail"
                and variant.normalized_outcome == "capability_pass"
            ):
                ablation_contrasts.add(base.run_id)
            if (
                variant.normalized_outcome == "capability_fail"
                and base.normalized_outcome == "capability_pass"
            ):
                ablation_contrasts.add(variant.run_id)
    return build_diagnosis_report(
        experiment_id=experiment_id,
        plan_digest=record.plan_digest,
        inputs=tuple(inputs),
        verified_ablation_contrast_run_ids=frozenset(ablation_contrasts),
    )
