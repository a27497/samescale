from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from harnesslab.db.models.experiment import ExperimentRecord, ExperimentRunRecord
from harnesslab.diagnosis.models import (
    DiagnosisInput,
    EvidenceOrigin,
    FailureClass,
    FailureScope,
    ToolCallEvidence,
    TraceEventEvidence,
    TraceEvidence,
)
from harnesslab.diagnosis.projection_models import (
    FAILURE_FACT_CONTRACT_VERSION,
    FAILURE_NORMALIZATION_VERSION,
    UNKNOWN_DIMENSION_VALUE,
    AttemptReadPath,
    AttemptReadSummary,
    AttemptSelectionPolicy,
    ClusterProjection,
    ClusterProjectionRequest,
    CohortMember,
    CohortPolicy,
    ControlledEvidenceBinding,
    ExcludedFailureFact,
    FailureCohort,
    MissingValuePolicy,
    OperationalTerminalCounts,
    ProjectedClusterReadRequest,
    ProjectedClusterReport,
    ProjectedFailureCluster,
    ProjectionDimension,
    RawFailureFact,
)
from harnesslab.diagnosis.service import (
    DiagnosisEvidenceError,
    DiagnosisRequestError,
    _declared_failure,
    _diagnosed_run,
    _digest,
    _safe_str,
    _task_metadata,
    _trace_pattern,
    _verifier,
    _workspace_diff,
)
from harnesslab.evidence.reader import (
    EvidenceReadError,
    load_normalized_trace,
    load_verified_manifest,
)
from harnesslab.experiment.lifecycle import LifecycleState, lifecycle_state_from_persisted
from harnesslab.experiment.plan import load_experiment_plan_payload

if TYPE_CHECKING:
    from harnesslab.experiment.authoritative import AttemptSnapshot

_ZERO_DIGEST = "sha256:" + "0" * 64
_DIMENSION_FIELDS: dict[ProjectionDimension, str] = {
    ProjectionDimension.MODEL: "model",
    ProjectionDimension.HARNESS: "harness",
    ProjectionDimension.TASK: "task_id",
    ProjectionDimension.LANGUAGE: "language",
    ProjectionDimension.TASK_FAMILY: "task_family",
    ProjectionDimension.FAILURE_CLASS: "failure_class",
    ProjectionDimension.FAILURE_SCOPE: "failure_scope",
    ProjectionDimension.TRACE_PATTERN: "trace_pattern",
    ProjectionDimension.TOOL_PATTERN: "tool_pattern",
    ProjectionDimension.WORKSPACE_DIFF_PATTERN: "workspace_diff_pattern",
}


@dataclass(frozen=True)
class _AttemptEvidenceRecord:
    run_id: str
    attempt: int
    artifact_manifest_path: str | None
    evidence_digest: str | None


@dataclass(frozen=True)
class _ExperimentFailureRead:
    member: CohortMember
    facts: tuple[RawFailureFact, ...]
    attempts: tuple[AttemptReadSummary, ...]
    selected_counts: OperationalTerminalCounts
    all_attempt_counts: OperationalTerminalCounts


def _raw_failure_fact(**values: Any) -> RawFailureFact:
    provisional = RawFailureFact.model_construct(fact_digest=_ZERO_DIGEST, **values)
    payload = provisional.model_dump(
        mode="json", exclude={"fact_digest", "is_effective_attempt_at_snapshot"}
    )
    return RawFailureFact(fact_digest=_digest(payload), **values)


def build_cluster_projection(
    request: ClusterProjectionRequest, *, evidence_snapshot_identity: str
) -> ClusterProjection:
    if request.normalization_version != FAILURE_NORMALIZATION_VERSION:
        raise DiagnosisRequestError("unsupported failure-fact normalization version")
    values = {
        **request.model_dump(),
        "evidence_snapshot_identity": evidence_snapshot_identity,
        "cohort_policy": CohortPolicy.EXPLICIT_COMPATIBLE_EXPERIMENTS,
    }
    provisional = ClusterProjection.model_construct(projection_digest=_ZERO_DIGEST, **values)
    return ClusterProjection(
        projection_digest=_digest(
            provisional.model_dump(mode="json", exclude={"projection_digest"})
        ),
        **values,
    )


def _aggregate_snapshot_identity(
    members: tuple[CohortMember, ...], selection: AttemptSelectionPolicy
) -> str:
    ordered = tuple(sorted(members, key=lambda item: item.experiment_id))
    return _digest(
        {
            "attempt_selection": selection.value,
            "members": [member.model_dump(mode="json") for member in ordered],
        }
    )


def build_failure_cohort(
    projection: ClusterProjection, members: tuple[CohortMember, ...]
) -> FailureCohort:
    ordered = tuple(sorted(members, key=lambda item: item.experiment_id))
    if len({member.experiment_id for member in ordered}) != len(ordered):
        raise DiagnosisRequestError("cohort experiment identities must be unique")
    if any(member.evidence_contract_version != FAILURE_FACT_CONTRACT_VERSION for member in ordered):
        raise DiagnosisRequestError("cohort evidence contracts are incompatible")
    payload = {
        "namespace": projection.namespace,
        "projection_digest": projection.projection_digest,
        "projection_version": projection.projection_version,
        "normalization_version": projection.normalization_version,
        "policy": "EXPLICIT_COMPATIBLE_EXPERIMENTS",
        "members": [member.model_dump(mode="json") for member in ordered],
        "diagnostic_only": True,
        "comparability_claim": False,
    }
    return FailureCohort(
        namespace=projection.namespace,
        projection_digest=projection.projection_digest,
        projection_version=projection.projection_version,
        normalization_version=projection.normalization_version,
        members=ordered,
        cohort_digest=_digest(payload),
    )


def _dimension_value(fact: RawFailureFact, dimension: ProjectionDimension) -> str | None:
    value: object = getattr(fact, _DIMENSION_FIELDS[dimension])
    if isinstance(value, FailureClass | FailureScope):
        return value.value
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() in {"unknown", "not-reported"}:
        return None
    return str(value)


def _sum_terminal_counts(items: tuple[OperationalTerminalCounts, ...]) -> OperationalTerminalCounts:
    return OperationalTerminalCounts(
        failed_capability=sum(item.failed_capability for item in items),
        failed_infra=sum(item.failed_infra for item in items),
        cancelled=sum(item.cancelled for item in items),
        budget_exhausted=sum(item.budget_exhausted for item in items),
    )


def build_projected_cluster_report(
    *,
    projection: ClusterProjection,
    cohort: FailureCohort,
    attempt_selection: AttemptSelectionPolicy,
    facts: tuple[RawFailureFact, ...],
    attempt_reads: tuple[AttemptReadSummary, ...] = (),
    operational_terminal_counts: OperationalTerminalCounts | None = None,
    all_attempt_terminal_counts: OperationalTerminalCounts | None = None,
    controlled_evidence: tuple[ControlledEvidenceBinding, ...] = (),
) -> ProjectedClusterReport:
    """Derive deterministic associations without mutating facts or increasing causality."""

    if cohort.namespace != projection.namespace:
        raise DiagnosisRequestError("projection and cohort namespaces differ")
    if cohort.projection_digest != projection.projection_digest:
        raise DiagnosisRequestError("cohort is bound to a different projection")
    if cohort.projection_version != projection.projection_version:
        raise DiagnosisRequestError("projection and cohort versions differ")
    if cohort.normalization_version != projection.normalization_version:
        raise DiagnosisRequestError("projection and cohort normalization versions differ")
    expected_snapshot = _aggregate_snapshot_identity(cohort.members, attempt_selection)
    if projection.evidence_snapshot_identity != expected_snapshot:
        raise DiagnosisRequestError("projection evidence snapshot does not match the cohort")
    member_plans = {
        (member.experiment_id, member.plan_digest)
        for member in cohort.members
        if member.evidence_contract_version == FAILURE_FACT_CONTRACT_VERSION
    }
    fact_digests = [fact.fact_digest for fact in facts]
    if len(set(fact_digests)) != len(fact_digests):
        raise DiagnosisRequestError("raw failure facts must be unique")
    if any(
        fact.normalization_version != projection.normalization_version
        or fact.contract_version != FAILURE_FACT_CONTRACT_VERSION
        or (fact.experiment_id, fact.plan_digest) not in member_plans
        for fact in facts
    ):
        raise DiagnosisRequestError("raw facts are incompatible with the exact cohort evidence")

    grouped: dict[tuple[tuple[ProjectionDimension, str], ...], list[RawFailureFact]] = defaultdict(
        list
    )
    excluded: list[ExcludedFailureFact] = []
    unknown_grouped = 0
    for fact in sorted(facts, key=lambda item: item.fact_digest):
        values: list[tuple[ProjectionDimension, str]] = []
        missing: list[ProjectionDimension] = []
        for dimension in projection.dimensions:
            value = _dimension_value(fact, dimension)
            if value is None:
                missing.append(dimension)
                value = f"{UNKNOWN_DIMENSION_VALUE}:{dimension.value}"
            values.append((dimension, value))
        if missing and projection.missing_value_policy is MissingValuePolicy.EXCLUDE_WITH_REASON:
            excluded.append(
                ExcludedFailureFact(
                    fact_digest=fact.fact_digest,
                    missing_dimensions=tuple(missing),
                )
            )
            continue
        if missing:
            unknown_grouped += 1
        grouped[tuple(values)].append(fact)

    clusters: list[ProjectedFailureCluster] = []
    for key in sorted(grouped, key=lambda item: tuple((dim.value, value) for dim, value in item)):
        dimensions = dict(key)
        ordered_facts = tuple(sorted(grouped[key], key=lambda item: item.fact_digest))
        cluster_id = _digest(
            {
                "projection_digest": projection.projection_digest,
                "dimensions": {item.value: dimensions[item] for item in projection.dimensions},
                "cohort_digest": cohort.cohort_digest,
                "evidence_snapshot_identity": projection.evidence_snapshot_identity,
            }
        )
        clusters.append(
            ProjectedFailureCluster(
                cluster_id=cluster_id,
                projection_digest=projection.projection_digest,
                cohort_digest=cohort.cohort_digest,
                evidence_snapshot_identity=projection.evidence_snapshot_identity,
                dimensions=dimensions,
                raw_fact_digests=tuple(item.fact_digest for item in ordered_facts),
                facts=ordered_facts,
            )
        )
    ordered_clusters = tuple(sorted(clusters, key=lambda item: item.cluster_id))
    ordered_excluded = tuple(sorted(excluded, key=lambda item: item.fact_digest))
    ordered_attempts = tuple(
        sorted(attempt_reads, key=lambda item: (item.experiment_id, item.logical_run_id))
    )
    counts = operational_terminal_counts or OperationalTerminalCounts(
        failed_capability=0, failed_infra=0, cancelled=0, budget_exhausted=0
    )
    all_counts = all_attempt_terminal_counts or counts
    payload = {
        "projection": projection.model_dump(mode="json"),
        "cohort": cohort.model_dump(mode="json"),
        "attempt_selection": attempt_selection.value,
        "facts": sorted(fact_digests),
        "excluded": [item.model_dump(mode="json") for item in ordered_excluded],
        "clusters": [item.model_dump(mode="json") for item in ordered_clusters],
        "operational_terminal_counts": counts.model_dump(mode="json"),
        "all_attempt_terminal_counts": all_counts.model_dump(mode="json"),
    }
    return ProjectedClusterReport(
        report_digest=_digest(payload),
        projection=projection,
        cohort=cohort,
        attempt_selection=attempt_selection,
        raw_fact_count=len(facts),
        clustered_fact_count=sum(len(item.facts) for item in ordered_clusters),
        excluded_fact_count=len(ordered_excluded),
        unknown_grouped_fact_count=unknown_grouped,
        operational_terminal_counts=counts,
        all_attempt_terminal_counts=all_counts,
        attempt_reads=ordered_attempts,
        excluded_facts=ordered_excluded,
        controlled_evidence=tuple(
            sorted(
                controlled_evidence,
                key=lambda item: (item.fact_digest, item.evidence_reference),
            )
        ),
        clusters=ordered_clusters,
    )


def _terminal_counts(states: tuple[LifecycleState, ...]) -> OperationalTerminalCounts:
    return OperationalTerminalCounts(
        failed_capability=sum(state is LifecycleState.FAILED_CAPABILITY for state in states),
        failed_infra=sum(state is LifecycleState.FAILED_INFRA for state in states),
        cancelled=sum(state is LifecycleState.CANCELLED for state in states),
        budget_exhausted=sum(state is LifecycleState.BUDGET_EXHAUSTED for state in states),
    )


def _normalized_outcome(state: LifecycleState) -> str:
    if state is LifecycleState.FAILED_CAPABILITY:
        return "capability_fail"
    if state is LifecycleState.FAILED_INFRA:
        return "infra_failure"
    raise DiagnosisRequestError("only actual failures can become raw failure facts")


def _attempt_evidence(run: ExperimentRunRecord, attempt: AttemptSnapshot) -> _AttemptEvidenceRecord:
    return _AttemptEvidenceRecord(
        run_id=run.run_id,
        attempt=attempt.attempt_number,
        artifact_manifest_path=attempt.artifact_manifest_path,
        evidence_digest=attempt.evidence_digest,
    )


def _compatibility_evidence(run: ExperimentRunRecord) -> _AttemptEvidenceRecord:
    return _AttemptEvidenceRecord(
        run_id=run.run_id,
        attempt=run.attempt,
        artifact_manifest_path=run.artifact_manifest_path,
        evidence_digest=run.evidence_digest,
    )


def _safe_projection_value(value: object) -> str | None:
    if not isinstance(value, str) or not value or value.strip().lower() == "unknown":
        return None
    return value


def _diagnosis_input_for_evidence(
    *,
    run: ExperimentRunRecord,
    state: LifecycleState,
    evidence: _AttemptEvidenceRecord,
    artifact_roots: tuple[Path, ...],
    model: str | None,
    harness: str | None,
    language: str | None,
    family: str | None,
    protected: frozenset[str],
    use_compatibility_metrics: bool,
) -> DiagnosisInput:
    if (evidence.artifact_manifest_path is None) != (evidence.evidence_digest is None):
        raise DiagnosisEvidenceError("attempt evidence identity is incomplete")
    raw: dict[str, Any] = {}
    artifact_available = evidence.artifact_manifest_path is not None
    if artifact_available:
        try:
            raw = load_verified_manifest(evidence, artifact_roots).raw
        except EvidenceReadError as exc:
            raise DiagnosisEvidenceError("attempt artifact cannot be verified") from exc
    trace_events: tuple[TraceEventEvidence, ...] = ()
    trace_digest: str | None = None
    coverage = raw.get("trace_coverage") if isinstance(raw.get("trace_coverage"), str) else None
    if isinstance(raw.get("normalized_trace_digest"), str):
        try:
            trace, trace_digest, coverage = load_normalized_trace(evidence, artifact_roots)
        except EvidenceReadError as exc:
            raise DiagnosisEvidenceError("attempt normalized trace cannot be verified") from exc
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
    command_count = sum(event.type == "COMMAND_EXECUTION" for event in trace_events)
    tool_count = (
        run.tool_calls
        if use_compatibility_metrics and run.tool_calls is not None
        else command_count
        if trace_digest
        else None
    )
    return DiagnosisInput(
        run_id=run.run_id,
        origin=EvidenceOrigin.IMMUTABLE_EXPERIMENT,
        cell_id=run.cell_id,
        task_id=run.task_id,
        task_version=run.task_version,
        model=_safe_str(raw.get("requested_model"), model or "unknown"),
        harness=_safe_str(raw.get("harness"), harness or "unknown"),
        language=language or "unknown",
        task_family=family or "unknown",
        normalized_outcome=_normalized_outcome(state),
        source_outcome=None,
        declared_failure_class=_declared_failure(raw),
        provider_failure=(
            raw.get("provider_failure") if isinstance(raw.get("provider_failure"), str) else None
        ),
        harness_failure=(
            raw.get("harness_failure") if isinstance(raw.get("harness_failure"), str) else None
        ),
        artifact_available=artifact_available,
        evidence_identity=evidence.evidence_digest if artifact_available else None,
        trace=trace_evidence,
        workspace_diff=_workspace_diff(raw, protected),
        tool_calls=ToolCallEvidence(
            status="REPORTED" if tool_count is not None else "NOT_REPORTED",
            count=tool_count,
            pattern=(
                f"count={tool_count};failed={len(failed_codes)}"
                if tool_count is not None
                else "not-reported"
            ),
            failed_exit_codes=failed_codes,
        ),
        verifier=_verifier(raw),
    )


def _fact_from_input(
    *,
    item: DiagnosisInput,
    run: ExperimentRunRecord,
    plan_digest: str,
    read_path: AttemptReadPath,
    attempt: AttemptSnapshot | None,
    is_effective: bool,
) -> RawFailureFact:
    diagnosed = _diagnosed_run(item, ablation_supported=False)
    return _raw_failure_fact(
        normalization_version=FAILURE_NORMALIZATION_VERSION,
        experiment_id=run.experiment_id,
        plan_digest=plan_digest,
        logical_run_id=run.run_id,
        cell_id=run.cell_id,
        slot_id=run.slot_id,
        physical_attempt_id=attempt.attempt_id if attempt else None,
        attempt_number=attempt.attempt_number if attempt else None,
        attempt_role=attempt.role.value if attempt else "LEGACY_COMPATIBILITY",
        is_primary_attempt=attempt is None or attempt.attempt_number == 1,
        is_effective_attempt_at_snapshot=is_effective,
        read_path=read_path,
        evidence_identity=diagnosed.evidence_identity,
        artifact_verified=diagnosed.artifact_verified,
        model=_safe_projection_value(diagnosed.model),
        harness=_safe_projection_value(diagnosed.harness),
        task_id=_safe_projection_value(diagnosed.task_id),
        task_version=diagnosed.task_version,
        language=_safe_projection_value(diagnosed.language),
        task_family=_safe_projection_value(diagnosed.task_family),
        failure_class=diagnosed.failure_class,
        failure_scope=diagnosed.failure_scope,
        trace_pattern=(diagnosed.trace.pattern if diagnosed.trace.status == "REPORTED" else None),
        tool_pattern=(
            diagnosed.tool_calls.pattern if diagnosed.tool_calls.status == "REPORTED" else None
        ),
        workspace_diff_pattern=(
            diagnosed.workspace_diff.pattern
            if diagnosed.workspace_diff.status != "NOT_REPORTED"
            else None
        ),
    )


async def _read_experiment_failure_facts(
    session: AsyncSession,
    *,
    experiment_id: str,
    selection: AttemptSelectionPolicy,
    artifact_roots: tuple[Path, ...],
    repository_root: Path,
) -> _ExperimentFailureRead:
    # Lazy import preserves the existing release -> diagnosis.models import boundary.
    from harnesslab.experiment.authoritative import read_authoritative_projection

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
    cell_metadata = {cell.id: (cell.requested_model, cell.harness) for cell in plan.cells}
    runs = tuple(
        (
            await session.scalars(
                select(ExperimentRunRecord)
                .where(ExperimentRunRecord.experiment_id == experiment_id)
                .order_by(ExperimentRunRecord.slot_order)
            )
        ).all()
    )
    facts: list[RawFailureFact] = []
    summaries: list[AttemptReadSummary] = []
    selected_states: list[LifecycleState] = []
    all_attempt_states: list[LifecycleState] = []
    snapshot_rows: list[dict[str, object]] = []
    for run in runs:
        authoritative = await read_authoritative_projection(session, run.run_id)
        model, harness = cell_metadata.get(run.cell_id, (None, None))
        language_raw, family_raw, protected = metadata.get(
            run.task_id, ("unknown", "unknown", frozenset())
        )
        language = _safe_projection_value(language_raw)
        family = _safe_projection_value(family_raw)
        selected_attempt: AttemptSnapshot | None
        if authoritative is None:
            state = lifecycle_state_from_persisted(run.status)
            selected_attempt = None
            selected_states.append(state)
            summary = AttemptReadSummary(
                experiment_id=experiment_id,
                logical_run_id=run.run_id,
                read_path=AttemptReadPath.LEGACY_COMPATIBILITY,
                selection_policy=selection,
                primary_outcome=state.value,
                selected_attempt_role="LEGACY_COMPATIBILITY",
                recovery_selected_as_effective=False,
            )
            evidence = _compatibility_evidence(run)
            is_effective = True
            snapshot_rows.append(
                {
                    "logical_run_id": run.run_id,
                    "read_path": AttemptReadPath.LEGACY_COMPATIBILITY.value,
                    "state": state.value,
                    "evidence_identity": run.evidence_digest,
                }
            )
        else:
            selected_attempt = (
                authoritative.primary_attempt
                if selection is AttemptSelectionPolicy.PRIMARY_ONLY
                else authoritative.effective_attempt
            )
            state = selected_attempt.state
            selected_states.append(state)
            physical_attempts = (
                authoritative.primary_attempt,
                *authoritative.recovery_attempts,
            )
            all_attempt_states.extend(item.state for item in physical_attempts)
            summary = AttemptReadSummary(
                experiment_id=experiment_id,
                logical_run_id=run.run_id,
                read_path=AttemptReadPath.AUTHORITATIVE_ATTEMPT,
                selection_policy=selection,
                primary_attempt_id=authoritative.primary_attempt.attempt_id,
                primary_outcome=authoritative.primary_attempt.state.value,
                recovery_attempt_ids=tuple(
                    item.attempt_id for item in authoritative.recovery_attempts
                ),
                recovery_outcomes=tuple(
                    item.state.value for item in authoritative.recovery_attempts
                ),
                selected_attempt_id=selected_attempt.attempt_id,
                selected_attempt_role=selected_attempt.role.value,
                recovery_selected_as_effective=selected_attempt.role.value == "RECOVERY",
            )
            evidence = _attempt_evidence(run, selected_attempt)
            is_effective = selected_attempt.attempt_id == authoritative.effective_attempt.attempt_id
            snapshot_rows.append(
                {
                    "logical_run_id": run.run_id,
                    "read_path": AttemptReadPath.AUTHORITATIVE_ATTEMPT.value,
                    "attempts": [
                        {
                            "attempt_id": item.attempt_id,
                            "attempt_number": item.attempt_number,
                            "role": item.role.value,
                            "state": item.state.value,
                            "evidence_identity": item.evidence_digest,
                        }
                        for item in physical_attempts
                    ],
                    "selected_attempt_id": selected_attempt.attempt_id,
                }
            )
        summaries.append(summary)
        if (evidence.artifact_manifest_path is None) != (evidence.evidence_digest is None):
            raise DiagnosisEvidenceError("selected attempt evidence identity is incomplete")
        if state not in {LifecycleState.FAILED_CAPABILITY, LifecycleState.FAILED_INFRA}:
            continue
        item = _diagnosis_input_for_evidence(
            run=run,
            state=state,
            evidence=evidence,
            artifact_roots=artifact_roots,
            model=model,
            harness=harness,
            language=language,
            family=family,
            protected=protected,
            use_compatibility_metrics=authoritative is None,
        )
        facts.append(
            _fact_from_input(
                item=item,
                run=run,
                plan_digest=record.plan_digest,
                read_path=(
                    AttemptReadPath.LEGACY_COMPATIBILITY
                    if authoritative is None
                    else AttemptReadPath.AUTHORITATIVE_ATTEMPT
                ),
                attempt=selected_attempt,
                is_effective=is_effective,
            )
        )
    member = CohortMember(
        experiment_id=record.id,
        plan_digest=record.plan_digest,
        evidence_snapshot_identity=_digest(
            {
                "experiment_id": record.id,
                "plan_digest": record.plan_digest,
                "attempt_selection": selection.value,
                "runs": snapshot_rows,
            }
        ),
    )
    return _ExperimentFailureRead(
        member=member,
        facts=tuple(sorted(facts, key=lambda item: item.fact_digest)),
        attempts=tuple(summaries),
        selected_counts=_terminal_counts(tuple(selected_states)),
        all_attempt_counts=_terminal_counts(tuple(all_attempt_states)),
    )


async def read_projected_failure_clusters(
    session: AsyncSession,
    experiment_id: str,
    request: ProjectedClusterReadRequest,
    artifact_roots: tuple[Path, ...],
    *,
    repository_root: Path,
) -> ProjectedClusterReport:
    if experiment_id in request.additional_experiment_ids:
        raise DiagnosisRequestError("primary experiment cannot be repeated in its cohort")
    experiment_ids = (experiment_id, *request.additional_experiment_ids)
    reads = tuple(
        [
            await _read_experiment_failure_facts(
                session,
                experiment_id=item,
                selection=request.attempt_selection,
                artifact_roots=artifact_roots,
                repository_root=repository_root,
            )
            for item in experiment_ids
        ]
    )
    members = tuple(sorted((item.member for item in reads), key=lambda item: item.experiment_id))
    snapshot = _aggregate_snapshot_identity(members, request.attempt_selection)
    projection = build_cluster_projection(request.projection, evidence_snapshot_identity=snapshot)
    cohort = build_failure_cohort(projection, members)
    return build_projected_cluster_report(
        projection=projection,
        cohort=cohort,
        attempt_selection=request.attempt_selection,
        facts=tuple(fact for item in reads for fact in item.facts),
        attempt_reads=tuple(summary for item in reads for summary in item.attempts),
        operational_terminal_counts=_sum_terminal_counts(
            tuple(item.selected_counts for item in reads)
        ),
        all_attempt_terminal_counts=_sum_terminal_counts(
            tuple(item.all_attempt_counts for item in reads)
        ),
    )
