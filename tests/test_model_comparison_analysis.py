from __future__ import annotations

from harnesslab.comparability.models import ComparisonFacts, canonical_digest
from harnesslab.contracts.common import EvaluationLane
from harnesslab.contracts.run import RunStatus
from harnesslab.db.models.experiment import ExperimentRunRecord
from harnesslab.experiment.model_comparison import (
    Availability,
    FailurePresentationCategory,
    analyze_model_comparison,
)
from harnesslab.experiment.outcomes import StatisticalOutcome
from harnesslab.experiment.plan import ExperimentPlan, ExperimentRunSlot, build_experiment_plan
from harnesslab.experiment.report import VerifiedExperimentEvidence, VerifiedRunObservation
from harnesslab.experiment.spec import ExperimentSpec
from harnesslab.experiment.statistics import RunObservation
from tests.phase_g_helpers import ROOT, cell, identity

TEST_FIXTURE_EXPERIMENT_ID = "synthetic-model-comparison-analysis-fixture"
TEST_FIXTURE_TASKS = (
    "tasks/core-java-deduplicate/1.0.2",
    "tasks/core-java-feature-flag/1.0.2",
    "tasks/core-python-deduplicate/1.0.2",
    "tasks/core-python-feature-flag/1.0.2",
    "tasks/core-typescript-deduplicate/1.0.2",
    "tasks/core-typescript-feature-flag/1.0.2",
    "tasks/micro-java-clamp/1.0.2",
)


def _fixture_plan() -> ExperimentPlan:
    """Schema-valid synthetic plan; it is never persisted as release or v3 evidence."""

    shared_profile = identity("synthetic-model-comparison-shared-profile")
    resource_envelope = identity("synthetic-model-comparison-resource-envelope")
    cells = tuple(
        cell(
            cell_id,
            EvaluationLane.MODEL,
            requested_model=requested_model,
            provider_route="synthetic-provider|responses|https://fixture.invalid/v1/responses",
            harness="direct-model",
            harness_version="fixture-schema-1",
            profile_identity=shared_profile,
            harness_config_identity=identity("synthetic-direct-control"),
            runner_contract="direct-model-v1",
        ).model_copy(update={"resource_envelope_identity": resource_envelope})
        for cell_id, requested_model in (("a", "fixture-model-a"), ("b", "fixture-model-b"))
    )
    return build_experiment_plan(
        ExperimentSpec(
            experiment_id=TEST_FIXTURE_EXPERIMENT_ID,
            name="Synthetic model-comparison analysis fixture",
            task_packages=TEST_FIXTURE_TASKS,
            cells=cells,
            repeat_count=1,
            execution_seed=7,
            comparison_intent="MODEL_COMPARISON",
        ),
        ROOT,
    )


def _facts(
    slot: ExperimentRunSlot, *, trace_coverage: str | None = "FULL_STREAM"
) -> ComparisonFacts:
    return ComparisonFacts(
        evidence_identity=canonical_digest({"synthetic_fixture_slot": slot.slot_id}),
        task_id=slot.task.task_id,
        task_version=slot.task.task_version,
        task_digest=slot.task.task_digest,
        workspace_input_digest=slot.task.workspace_input_digest,
        context_identity=identity("synthetic-context"),
        verifier_control_identity=slot.task.verifier_identity,
        verifier_execution_identity=slot.task.verifier_identity,
        verifier_execution_status="EXECUTED",
        verifier_control_execution_status="MATCH",
        requested_model=slot.requested_model,
        observed_model=slot.requested_model,
        provider_route=slot.provider_route,
        budget_identity=slot.task.budget_identity,
        resource_envelope_identity=slot.resource_envelope_identity,
        network_policy=slot.task.network_policy.value,
        harness=slot.harness,
        harness_version=slot.harness_version,
        harness_profile_identity=identity("synthetic-direct-harness-profile"),
        prompt_identity=identity("synthetic-prompt"),
        trace_coverage=trace_coverage,
    )


def _fixture_outcome(
    task_index: int, cell_id: str
) -> tuple[StatisticalOutcome, str, dict[str, object] | None] | None:
    pass_manifest: dict[str, object] = {
        "outcome": "verified_pass",
        "provider": "synthetic-provider",
        "summary": "synthetic fixture verifier passed",
    }
    fail_manifest: dict[str, object] = {
        "outcome": "verified_fail",
        "provider": "synthetic-provider",
        "summary": "synthetic fixture capability failure",
    }
    if task_index == 0:
        return StatisticalOutcome.CAPABILITY_PASS, "verified_pass", pass_manifest
    if task_index == 1:
        return (
            (StatisticalOutcome.CAPABILITY_PASS, "verified_pass", pass_manifest)
            if cell_id == "a"
            else (StatisticalOutcome.CAPABILITY_FAIL, "verified_fail", fail_manifest)
        )
    if task_index == 2:
        if cell_id == "a":
            return (
                StatisticalOutcome.CAPABILITY_FAIL,
                "subject_output_error",
                {
                    "outcome": "subject_output_error",
                    "provider": "synthetic-provider",
                    "summary": "public model output exhausted the frozen output-token budget",
                    "provider_result": {
                        "provider": "synthetic-provider",
                        "incomplete_reason": "max_output_tokens",
                        "stop_reason": "max_output_tokens",
                    },
                },
            )
        return StatisticalOutcome.CAPABILITY_FAIL, "verified_fail", fail_manifest
    if task_index == 3:
        if cell_id == "a":
            return (
                StatisticalOutcome.INFRA_FAILURE,
                "provider_error",
                {
                    "outcome": "provider_error",
                    "provider": "synthetic-provider",
                    "provider_failure": "timeout",
                    "summary": "synthetic fixture provider timeout",
                },
            )
        return StatisticalOutcome.CAPABILITY_PASS, "verified_pass", pass_manifest
    if task_index == 4:
        if cell_id == "a":
            return (
                StatisticalOutcome.INFRA_FAILURE,
                "provider_error",
                {
                    "outcome": "provider_error",
                    "provider": "synthetic-provider",
                    "provider_failure": "incomplete_response",
                    "summary": "synthetic fixture incomplete provider output",
                },
            )
        return (
            StatisticalOutcome.INFRA_FAILURE,
            "infra_error",
            {
                "outcome": "infra_error",
                "provider": "synthetic-provider",
                "summary": "isolated verification failed: SyntheticFixtureError",
            },
        )
    if task_index == 5:
        if cell_id == "a":
            return StatisticalOutcome.INFRA_FAILURE, "control_identity_mismatch", None
        return None
    if cell_id == "a":
        marked = dict(pass_manifest)
        marked["recovery_attempt_identity"] = identity("synthetic-recovery-attempt")
        return StatisticalOutcome.CAPABILITY_PASS, "verified_pass", marked
    return None


def _run_status(outcome: StatisticalOutcome | None) -> RunStatus:
    if outcome is StatisticalOutcome.CAPABILITY_PASS:
        return RunStatus.COMPLETED
    if outcome is StatisticalOutcome.CAPABILITY_FAIL:
        return RunStatus.FAILED_SUBJECT
    if outcome is StatisticalOutcome.INFRA_FAILURE:
        return RunStatus.FAILED_INFRA
    return RunStatus.QUEUED


def _fixture_evidence() -> VerifiedExperimentEvidence:
    """Synthetic in-memory observations only; no provider, database, or evidence writes occur."""

    plan = _fixture_plan()
    task_indexes = {task.task_id: index for index, task in enumerate(plan.tasks)}
    runs: list[ExperimentRunRecord] = []
    observations: list[VerifiedRunObservation] = []
    for slot in plan.run_slots:
        fixture = _fixture_outcome(task_indexes[slot.task.task_id], slot.cell_id)
        outcome = fixture[0] if fixture is not None else None
        source = fixture[1] if fixture is not None else None
        manifest = fixture[2] if fixture is not None else None
        run = ExperimentRunRecord(
            run_id=f"synthetic-fixture-run-{slot.slot_order}",
            experiment_id=plan.experiment_id,
            cell_id=slot.cell_id,
            slot_id=slot.slot_id,
            slot_order=slot.slot_order,
            slot_json=slot.model_dump(mode="json"),
            lane=slot.lane.value,
            task_id=slot.task.task_id,
            task_version=slot.task.task_version,
            task_digest=slot.task.task_digest,
            repeat_index=slot.repeat_index,
            paired_slot_identity=slot.paired_slot_identity,
            status=_run_status(outcome).value,
            attempt=1 if outcome is not None else 0,
            normalized_outcome=outcome.value if outcome is not None else None,
            source_outcome=source,
            input_tokens=100 if outcome is not None else None,
            output_tokens=20 if outcome is not None else None,
            explicit_cost=(None if outcome is None or slot.slot_order == 0 else 0.01),
        )
        runs.append(run)
        if outcome is None or source is None:
            continue
        trace: str | None = None if slot.slot_order == 1 else "FULL_STREAM"
        facts = (
            None if source == "control_identity_mismatch" else _facts(slot, trace_coverage=trace)
        )
        observations.append(
            VerifiedRunObservation(
                run=run,
                observation=RunObservation(
                    run_id=run.run_id,
                    task_id=run.task_id,
                    repeat_index=run.repeat_index,
                    paired_slot_identity=run.paired_slot_identity,
                    outcome=outcome,
                    source_outcome=source,
                    input_tokens=float(run.input_tokens) if run.input_tokens is not None else None,
                    output_tokens=(
                        float(run.output_tokens) if run.output_tokens is not None else None
                    ),
                    explicit_cost=run.explicit_cost,
                ),
                facts=facts,
                manifest=manifest,
            )
        )
    return VerifiedExperimentEvidence(plan=plan, runs=tuple(runs), observations=tuple(observations))


def test_synthetic_fixture_reports_capability_infra_pairs_and_descriptive_scope() -> None:
    closeout = analyze_model_comparison(_fixture_evidence(), repository_root=ROOT)
    analysis = closeout.analysis

    assert analysis.experiment_id == TEST_FIXTURE_EXPERIMENT_ID
    assert closeout.analysis_digest == analysis.digest
    assert analysis.conclusion_semantics.scope == "EXPLORATORY_DESCRIPTIVE"
    assert analysis.overall.planned_slots == 14
    assert analysis.overall.acquired_slots == 12
    assert analysis.overall.unacquired_slots == 2
    assert analysis.overall.capability_denominator == 8
    assert (analysis.overall.passed, analysis.overall.failed, analysis.overall.infra) == (5, 3, 4)
    assert analysis.pairs.planned_pairs == 7
    assert analysis.pairs.matched_capability_pairs == 3
    assert (analysis.pairs.both_pass, analysis.pairs.model_a_only_pass) == (1, 1)
    assert (analysis.pairs.model_b_only_pass, analysis.pairs.both_fail) == (0, 1)
    assert (analysis.pairs.infra_pairs, analysis.pairs.missing_pairs) == (3, 1)
    assert analysis.pairs.raw_percentage_point_difference == -(100 / 3)


def test_synthetic_fixture_distinguishes_failure_identity_trace_recovery_and_cost() -> None:
    analysis = analyze_model_comparison(_fixture_evidence(), repository_root=ROOT).analysis
    failures = analysis.overall.failure_categories

    expected = {
        FailurePresentationCategory.CAPABILITY_FAILURE,
        FailurePresentationCategory.PROVIDER_INFRASTRUCTURE,
        FailurePresentationCategory.VERIFIER_INFRASTRUCTURE,
        FailurePresentationCategory.BUDGET_EXHAUSTION,
        FailurePresentationCategory.INCOMPLETE_PROVIDER_OUTPUT,
        FailurePresentationCategory.CONTROL_DRIFT,
        FailurePresentationCategory.UNACQUIRED_SLOT,
    }
    assert expected <= set(failures)
    assert failures[FailurePresentationCategory.UNACQUIRED_SLOT] == 2
    assert analysis.control_drift.status == "DETECTED"
    assert analysis.control_drift.affected_runs == 1
    assert analysis.trace_coverage.status is Availability.PARTIAL
    assert analysis.observed_models.status is Availability.PARTIAL
    assert analysis.observed_providers.counts == {"synthetic-provider": 11}
    assert analysis.recovery_attempts.status == "NOT_AVAILABLE"
    assert analysis.recovery_attempts.explicitly_marked_recovery_acquisitions == 1
    assert analysis.recovery_attempts.lease_claim_attempts == 12
    by_label = {model.model_label: model for model in analysis.models}
    assert by_label["MODEL_A"].usage_and_cost.explicit_cost.status is Availability.NOT_AVAILABLE
    assert by_label["MODEL_A"].usage_and_cost.explicit_cost.total is None
    assert by_label["MODEL_B"].usage_and_cost.explicit_cost.status is Availability.AVAILABLE
    assert {row.dimension for row in analysis.breakdowns} == {"language", "task_family"}
    serialized = closeout_text = analyze_model_comparison(
        _fixture_evidence(), repository_root=ROOT
    ).canonical_json()
    assert TEST_FIXTURE_EXPERIMENT_ID in serialized
    assert "statistically significant" not in closeout_text.lower()
    assert "universally better" not in closeout_text.lower()
    assert "causal uplift" not in closeout_text.lower()
