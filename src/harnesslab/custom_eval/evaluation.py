from __future__ import annotations

from collections import defaultdict

from harnesslab.custom_eval.models import (
    CriteriaDecision,
    CriterionEvidence,
    CriterionKind,
    CriterionStatus,
    CustomEvaluationPlan,
    CustomEvaluationReport,
    CustomPlannedTask,
    CustomPlanRequest,
    CustomRunEvidence,
    CustomRunSlot,
    CustomTargetReport,
    EvaluationCriterion,
    canonical_digest,
)
from harnesslab.custom_eval.store import (
    ManagedTaskStore,
    ManagedTaskStoreError,
)
from harnesslab.experiment.outcomes import StatisticalOutcome
from harnesslab.experiment.statistics import RunObservation, summarize_cell


class CustomEvaluationError(ValueError):
    """A custom evaluation plan or evidence set is incoherent."""


def build_custom_plan(request: CustomPlanRequest, store: ManagedTaskStore) -> CustomEvaluationPlan:
    """Expand custom snapshots with the canonical 1/3/5 methodology repeat semantics."""

    tasks: list[CustomPlannedTask] = []
    for reference in request.task_references:
        try:
            record, _package = store.load_package(reference)
        except ManagedTaskStoreError as exc:
            raise CustomEvaluationError(f"cannot resolve custom task {reference}") from exc
        tasks.append(
            CustomPlannedTask(
                reference=record.reference,
                task_id=record.task_id,
                task_version=record.task_version,
                task_identity=record.task_identity,
                workspace_identity=record.workspace_identity,
                verifier_identity=record.verifier_identity,
                managed_snapshot_identity=record.managed_snapshot_identity,
                criteria=record.criteria,
            )
        )
    planned_tasks = tuple(sorted(tasks, key=lambda item: (item.task_id, item.task_version)))
    targets = tuple(sorted(request.targets, key=lambda item: item.id))
    slots: list[CustomRunSlot] = []
    for task in planned_tasks:
        for target in targets:
            for repeat_index in range(request.preset.repeat_count):
                identity = {
                    "namespace": "CUSTOM",
                    "evaluation_id": request.evaluation_id,
                    "task_snapshot": task.managed_snapshot_identity,
                    "target": target.model_dump(mode="json"),
                    "repeat_index": repeat_index,
                    "execution_seed": request.execution_seed,
                }
                slots.append(
                    CustomRunSlot(
                        slot_id=canonical_digest(identity),
                        slot_order=len(slots),
                        evaluation_id=request.evaluation_id,
                        task=task,
                        target=target,
                        repeat_index=repeat_index,
                    )
                )
    if len({slot.slot_id for slot in slots}) != len(slots):
        raise CustomEvaluationError("custom plan produced duplicate logical run slots")
    return CustomEvaluationPlan(
        evaluation_id=request.evaluation_id,
        name=request.name,
        preset=request.preset,
        evaluation_mode=request.preset.evaluation_mode,
        repeat_count=request.preset.repeat_count,
        execution_seed=request.execution_seed,
        tasks=planned_tasks,
        targets=targets,
        run_slots=tuple(slots),
    )


def evaluate_criteria(
    criteria: tuple[EvaluationCriterion, ...],
    evidence: tuple[CriterionEvidence, ...],
) -> CriteriaDecision:
    """Apply deterministic L0 authority; Judge evidence can never reverse an L0 failure."""

    expected = {criterion.id: criterion for criterion in criteria}
    observed = {item.criterion_id: item for item in evidence}
    if len(observed) != len(evidence):
        raise CustomEvaluationError("duplicate criterion evidence")
    unknown = set(observed) - set(expected)
    if unknown:
        raise CustomEvaluationError("criterion evidence references an unknown rule")

    deterministic_failures: list[str] = []
    other_failures: list[str] = []
    for criterion in criteria:
        result = observed.get(criterion.id)
        if result is None:
            if criterion.required:
                raise CustomEvaluationError(
                    f"required criterion evidence is missing: {criterion.id}"
                )
            continue
        if result.status in {
            CriterionStatus.INFRA,
            CriterionStatus.MISSING,
            CriterionStatus.NOT_EVALUATED,
        }:
            if criterion.required:
                raise CustomEvaluationError(
                    f"required criterion is not terminal capability evidence: {criterion.id}"
                )
            continue
        failed = result.status is CriterionStatus.FAIL
        if criterion.kind is CriterionKind.PERFORMANCE_THRESHOLD:
            if result.measured_value is None:
                raise CustomEvaluationError("performance criterion requires a measured value")
            assert criterion.threshold is not None
            failed = result.measured_value > criterion.threshold
        if failed and criterion.kind.deterministic:
            deterministic_failures.append(criterion.id)
        elif failed:
            other_failures.append(criterion.id)

    if deterministic_failures:
        return CriteriaDecision(
            status=CriterionStatus.FAIL,
            deterministic_l0_failed=True,
            reason_codes=tuple(f"L0_FAIL:{item}" for item in sorted(deterministic_failures)),
        )
    if other_failures:
        return CriteriaDecision(
            status=CriterionStatus.FAIL,
            deterministic_l0_failed=False,
            reason_codes=tuple(f"JUDGE_FAIL:{item}" for item in sorted(other_failures)),
        )
    return CriteriaDecision(
        status=CriterionStatus.PASS,
        deterministic_l0_failed=False,
        reason_codes=("ALL_REQUIRED_DETERMINISTIC_CRITERIA_PASS",),
    )


def _criterion_terminal_state(
    criteria: tuple[EvaluationCriterion, ...], evidence: tuple[CriterionEvidence, ...]
) -> str:
    expected = {criterion.id: criterion for criterion in criteria}
    observed = {item.criterion_id: item for item in evidence}
    if len(observed) != len(evidence) or set(observed) - set(expected):
        raise CustomEvaluationError("criterion evidence identities are invalid")
    if any(
        item.status is CriterionStatus.FAIL and expected[item.criterion_id].kind.deterministic
        for item in evidence
    ):
        return "FAIL"
    required_results = tuple(
        observed.get(criterion.id) for criterion in criteria if criterion.required
    )
    if any(item is not None and item.status is CriterionStatus.INFRA for item in required_results):
        return "INFRA"
    if any(
        item is None or item.status in {CriterionStatus.MISSING, CriterionStatus.NOT_EVALUATED}
        for item in required_results
    ):
        return "MISSING"
    return evaluate_criteria(criteria, evidence).status.value


def _availability(present: int, total: int) -> str:
    if total == 0 or present == 0:
        return "NOT_AVAILABLE"
    return "AVAILABLE" if present == total else "PARTIAL"


def build_custom_report(
    plan: CustomEvaluationPlan,
    evidence: tuple[CustomRunEvidence, ...],
) -> CustomEvaluationReport:
    """Build a custom-only report while reusing canonical outcome/statistics primitives."""

    slot_by_id = {slot.slot_id: slot for slot in plan.run_slots}
    evidence_by_slot = {item.slot_id: item for item in evidence}
    if len(evidence_by_slot) != len(evidence):
        raise CustomEvaluationError("duplicate custom run evidence")
    if set(evidence_by_slot) - set(slot_by_id):
        raise CustomEvaluationError("custom evidence references a slot outside the plan")

    completed_evidence: list[CustomRunEvidence] = []
    observations_by_target: dict[str, list[RunObservation]] = defaultdict(list)
    states_by_target: dict[str, list[tuple[str, CustomRunEvidence]]] = defaultdict(list)
    for slot in plan.run_slots:
        item = evidence_by_slot.get(slot.slot_id)
        if item is None:
            item = CustomRunEvidence(slot_id=slot.slot_id, missing=True)
        completed_evidence.append(item)
        if item.missing:
            state = "MISSING"
            outcome = StatisticalOutcome.CANCELLED
        elif item.infrastructure_failure:
            state = "INFRA"
            outcome = StatisticalOutcome.INFRA_FAILURE
        else:
            state = _criterion_terminal_state(slot.task.criteria, item.criteria)
            outcome = {
                "PASS": StatisticalOutcome.CAPABILITY_PASS,
                "FAIL": StatisticalOutcome.CAPABILITY_FAIL,
                "INFRA": StatisticalOutcome.INFRA_FAILURE,
                "MISSING": StatisticalOutcome.CANCELLED,
            }[state]
        states_by_target[slot.target.id].append((state, item))
        observations_by_target[slot.target.id].append(
            RunObservation(
                run_id=slot.slot_id,
                task_id=slot.task.task_id,
                repeat_index=slot.repeat_index,
                paired_slot_identity=canonical_digest(
                    {
                        "evaluation_id": plan.evaluation_id,
                        "task": slot.task.managed_snapshot_identity,
                        "repeat_index": slot.repeat_index,
                    }
                ),
                outcome=outcome,
                source_outcome=f"custom_{state.lower()}",
                explicit_cost=item.cost,
            )
        )

    target_reports: list[CustomTargetReport] = []
    intended_task_ids = tuple(task.task_id for task in plan.tasks)
    for target in plan.targets:
        target_states = states_by_target[target.id]
        observations = tuple(observations_by_target[target.id])
        statistics = summarize_cell(
            target.id,
            len(target_states),
            observations,
            intended_task_ids=intended_task_ids,
            seed=plan.execution_seed,
            bootstrap_resamples=99,
        )
        costs = tuple(item.cost for _, item in target_states)
        traces = tuple(item.trace_identity for _, item in target_states)
        target_reports.append(
            CustomTargetReport(
                target=target,
                planned_runs=len(target_states),
                capability_passes=statistics.capability_passes,
                capability_failures=statistics.capability_failures,
                infrastructure_failures=statistics.infra_failures,
                missing_runs=statistics.cancelled_runs,
                pass_rate=statistics.success_rate,
                cost_availability=_availability(
                    sum(value is not None for value in costs), len(costs)
                ),
                total_cost=(
                    float(sum(value for value in costs if value is not None))
                    if costs and all(value is not None for value in costs)
                    else None
                ),
                trace_availability=_availability(
                    sum(value is not None for value in traces), len(traces)
                ),
            )
        )

    limits = [
        "Results apply only to the frozen CUSTOM task snapshots in this plan.",
        "CUSTOM results do not alter Official Core, Tier-A, or Tier-B qualification.",
        "Infrastructure and missing runs are excluded from the capability denominator.",
    ]
    if plan.repeat_count == 1:
        limits.append("Custom n=1 is smoke evidence and cannot support a universal model claim.")
    else:
        limits.append("Custom task evidence cannot support a universal model claim.")
    return CustomEvaluationReport(
        evaluation_id=plan.evaluation_id,
        plan_digest=plan.digest,
        preset=plan.preset,
        repeat_count=plan.repeat_count,
        custom_tasks=plan.tasks,
        targets=tuple(target_reports),
        deterministic_verifier_evidence=tuple(completed_evidence),
        comparability_limits=tuple(limits),
    )


__all__ = [
    "CustomEvaluationError",
    "build_custom_plan",
    "build_custom_report",
    "evaluate_criteria",
]
