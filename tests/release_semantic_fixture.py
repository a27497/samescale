from __future__ import annotations

from pathlib import Path
from typing import Any

from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.common import EvaluationLane, NetworkPolicy, Protocol
from harnesslab.contracts.model import ModelProfile, ReasoningProfile
from harnesslab.contracts.provider import ThinkingMode, ThinkingTransport
from harnesslab.contracts.run import RunStatus
from harnesslab.experiment.outcomes import StatisticalOutcome
from harnesslab.experiment.plan import (
    ExperimentPlan,
    ExperimentRunSlot,
    PlannedCell,
    PlannedTask,
)
from harnesslab.experiment.spec import AblationSpec, PairedComparisonSpec
from harnesslab.judgelab.models import JudgeCellSpec, digest
from harnesslab.judgelab.plan import (
    build_calibration_plan,
    load_calibration_spec,
    resolve_definitions,
    resolve_suite,
)
from harnesslab.model_lane.models import DirectModelOutcome
from harnesslab.release.contracts import (
    load_core_corpus,
    load_real_evidence_plan,
    load_release_evidence,
    load_resume_claim_map,
)
from harnesslab.release.final_verifier import (
    EXPECTED_GATES,
    EXPECTED_WORKFLOW,
    AblationEvidenceSummary,
    AuthoritativeReleaseSnapshot,
    ExperimentEvidenceSummary,
    JudgeEvidenceSummary,
    PairEvidenceSummary,
    RemoteCIAttestation,
    RunEvidenceSummary,
)
from harnesslab.release.models import (
    BadCasePlan,
    BadCaseSlot,
    EvidenceBinding,
    EvidenceState,
    PairedClaimPolicy,
    ReleaseEvidenceManifest,
    ResumeClaimMap,
)

ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 40


def _experiment_plan() -> ExperimentPlan:
    corpus = load_core_corpus(ROOT / "release/core-corpus.json")
    release = load_real_evidence_plan(ROOT / "release/core-real-evidence-plan.json")
    budget = canonical_digest({"budget": "core"})
    tasks = tuple(
        PlannedTask(
            package_path=item.package_path,
            task_id=item.task_id,
            task_version=item.version,
            task_digest=item.task_digest,
            workspace_input_digest=item.workspace_input_identity,
            context_identity=None,
            verifier_identity=item.verifier_identity,
            budget_identity=budget,
            network_policy=NetworkPolicy.DENY,
        )
        for item in corpus.tasks
    )
    harness_names = {
        "direct-model": "direct-model",
        "codex": "codex",
        "claude-code": "claude-code",
        "deepseek-e1": "deepseek",
    }
    cells = tuple(
        PlannedCell(
            id=item.cell_id,
            lane=EvaluationLane(item.lane),
            requested_model=item.requested_model or f"resolved-{item.cell_id}",
            provider_route=item.provider_route or "unresolved-provider-route",
            profile_reference="builtin:core-release-test",
            profile_identity=canonical_digest(
                {"cell": item.cell_id, "reasoning": item.reasoning_effort}
            ),
            harness=harness_names[item.runtime],
            harness_version="1.0.0",
            harness_config_identity=canonical_digest(
                {"harness": item.runtime, "reasoning": item.reasoning_effort}
            ),
            reasoning_effort=item.reasoning_effort,
            resource_budget_identity=budget,
            network_policy=NetworkPolicy.DENY,
            runner_contract="provider-adapter-v1",
            credential_reference="CORE_TEST_CREDENTIAL",
        )
        for item in release.cells
    )
    slots: list[ExperimentRunSlot] = []
    for cell in cells:
        for task in tasks:
            for repeat_index in range(5):
                pair_identity = canonical_digest(
                    {
                        "experiment_id": release.experiment_id,
                        "task_id": task.task_id,
                        "task_version": task.task_version,
                        "task_digest": task.task_digest,
                        "repeat_index": repeat_index,
                    }
                )
                identity = canonical_digest(
                    {
                        "cell": cell.id,
                        "task": task.task_id,
                        "repeat": repeat_index,
                    }
                )
                slots.append(
                    ExperimentRunSlot(
                        slot_id=identity,
                        slot_order=len(slots),
                        experiment_id=release.experiment_id,
                        cell_id=cell.id,
                        lane=cell.lane,
                        task=task,
                        repeat_index=repeat_index,
                        paired_slot_identity=pair_identity,
                        requested_model=cell.requested_model,
                        provider_route=cell.provider_route,
                        profile_identity=cell.profile_identity,
                        harness=cell.harness,
                        harness_version=cell.harness_version,
                        harness_config_identity=cell.harness_config_identity,
                        reasoning_effort=cell.reasoning_effort,
                        runner_contract=cell.runner_contract,
                    )
                )
    return ExperimentPlan(
        experiment_id=release.experiment_id,
        name="Core release semantic fixture",
        execution_seed=release.execution_seed,
        repeat_count=5,
        comparison_intent="GENERAL",
        tasks=tasks,
        cells=cells,
        paired_comparisons=(
            PairedComparisonSpec(
                id=release.paired_lane.pair_id,
                left_cell_id=release.paired_lane.left_cell_id,
                right_cell_id=release.paired_lane.right_cell_id,
            ),
        ),
        ablations=(
            AblationSpec(
                id=release.ablation.ablation_id,
                base_cell_id=release.ablation.base_cell_id,
                variant_cell_id=release.ablation.variant_cell_id,
                changed_dimension="reasoning_effort",
            ),
        ),
        run_slots=tuple(slots),
    )


def _judge_plan() -> Any:
    spec = load_calibration_spec(ROOT / "judge_suites/core-calibration/1.0.0/calibration.yaml")
    suite = resolve_suite(spec, ROOT)
    definitions = resolve_definitions(spec, ROOT)
    profile = ModelProfile(
        requested_model="glm-5.2",
        provider="bailian-openai",
        base_url="https://bailian.example.test/v1",
        route="/chat/completions",
        protocol=Protocol.CHAT_COMPLETIONS,
        reasoning=ReasoningProfile(max_output_tokens=256),
        thinking_mode=ThinkingMode.DISABLED,
        thinking_transport=ThinkingTransport.BAILIAN_ENABLE_THINKING,
        credential_reference="DASHSCOPE_API_KEY",
    )
    source = spec.judge_cells[0]
    cell = JudgeCellSpec(
        id="real-judge",
        definition_reference=source.definition_reference,
        definition_digest=source.definition_digest,
        model_profile=profile,
        profile_identity=digest(profile),
        runner_contract="provider-adapter-v1",
    )
    real_spec = spec.model_copy(
        update={
            "calibration_id": "core-real-judge-v1",
            "name": "Core real Judge fixture",
            "judge_cells": (cell,),
        }
    )
    return build_calibration_plan(real_spec, suite, {cell.id: definitions[source.id]})


def semantic_fixture() -> dict[str, Any]:
    corpus = load_core_corpus(ROOT / "release/core-corpus.json")
    release_plan = load_real_evidence_plan(ROOT / "release/core-real-evidence-plan.json")
    plan = _experiment_plan()
    runs = tuple(
        RunEvidenceSummary(
            run_id=f"run-{index:03d}",
            slot_id=slot.slot_id,
            cell_id=slot.cell_id,
            task_id=slot.task.task_id,
            task_version=slot.task.task_version,
            task_digest=slot.task.task_digest,
            verifier_identity=slot.task.verifier_identity,
            repeat_index=slot.repeat_index,
            status=(RunStatus.FAILED_SUBJECT.value if index < 3 else RunStatus.COMPLETED.value),
            normalized_outcome=(
                StatisticalOutcome.CAPABILITY_FAIL.value
                if index < 3
                else StatisticalOutcome.CAPABILITY_PASS.value
            ),
            source_outcome=(
                DirectModelOutcome.VERIFIED_FAIL.value
                if index < 3
                else DirectModelOutcome.VERIFIED_PASS.value
            ),
            evidence_digest=canonical_digest({"run": index}),
            safe_trace_available=True,
            normalized_trace_digest=canonical_digest({"trace": index}),
            safe_trace_facts=("TRACE_EVENT_TYPE:TURN_FAILED",),
        )
        for index, slot in enumerate(plan.run_slots)
    )
    per_task = {item.task_id: 5 for item in corpus.tasks}
    pair = PairEvidenceSummary(
        pair_id=release_plan.paired_lane.pair_id,
        left_cell_id=release_plan.paired_lane.left_cell_id,
        right_cell_id=release_plan.paired_lane.right_cell_id,
        total_observations=90,
        comparable=0,
        partially_comparable=0,
        not_comparable=90,
        per_task_observations=per_task,
        formal_eligible=False,
        source_digest=canonical_digest({"actual_pair_report": 1}),
    )
    ablation = AblationEvidenceSummary(
        ablation_id=release_plan.ablation.ablation_id,
        base_cell_id=release_plan.ablation.base_cell_id,
        variant_cell_id=release_plan.ablation.variant_cell_id,
        changed_dimension="reasoning_effort",
        total_observations=90,
        comparable=90,
        per_task_observations=per_task,
        formal_eligible=True,
        source_digest=canonical_digest({"actual_ablation_report": 1}),
    )
    experiment = ExperimentEvidenceSummary(
        experiment_id=plan.experiment_id,
        record_status="completed",
        plan=plan,
        runs=runs,
        report_experiment_id=plan.experiment_id,
        report_plan_digest=plan.digest,
        report_run_count=630,
        report_digest=canonical_digest({"actual_experiment_report": 1}),
        pair=pair,
        ablation=ablation,
        authoritative_loader_verified=True,
    )
    judge_plan = _judge_plan()
    judge = JudgeEvidenceSummary(
        calibration_id=judge_plan.calibration_id,
        record_status="completed",
        plan=judge_plan,
        evaluation_count=63,
        completed_evaluation_count=63,
        observed_models=("glm-5.2",),
        report_calibration_id=judge_plan.calibration_id,
        report_plan_digest=judge_plan.plan_digest,
        report_suite_id=judge_plan.suite_id,
        report_suite_version=judge_plan.suite_version,
        report_suite_digest=judge_plan.suite_digest,
        report_digest=canonical_digest({"actual_judge_report": 1}),
        l0_override_count=0,
        real_judge_smoke="VERIFIED",
        authoritative_report_verified=True,
    )
    snapshot = AuthoritativeReleaseSnapshot(experiment=experiment, judge=judge)

    slots: list[BadCaseSlot] = []
    for index, run in enumerate(runs[:3], 1):
        task_identity = f"task:{run.task_id}@{run.task_version}#{run.task_digest}"
        slots.append(
            BadCaseSlot(
                slot_id=f"badcase-{index}",
                status=EvidenceState.VERIFIED,
                task_identity=task_identity,
                run_identity=f"run:{run.run_id}",
                cell_identity=f"cell:{run.cell_id}",
                evidence_refs=(
                    f"run:{run.run_id}",
                    f"cell:{run.cell_id}",
                    task_identity,
                    f"verifier:{run.verifier_identity}",
                    f"manifest:{run.evidence_digest}",
                    f"trace:{run.run_id}#{run.normalized_trace_digest}",
                ),
                observed_failure="Verifier-observed fixture failure",
                safe_trace_facts=run.safe_trace_facts,
                verifier_result=f"{run.normalized_outcome}:{run.source_outcome}",
                attribution_classification="VERIFIED_FACTS_ONLY",
                root_cause=None,
                mitigation_lesson="Inspect the bounded trace before changing the task.",
                harnesslab_detection="Manifest and verifier outcome were normalized.",
            )
        )
    badcases = BadCasePlan(slots=tuple(slots))

    base_claims = load_resume_claim_map(ROOT / "release/resume-claim-evidence.json")
    updates = {
        "real-matrix-results": (f"experiment-report:{plan.experiment_id}",),
        "real-judge-quality": (f"judge-report:{judge.calibration_id}",),
        "real-badcases": tuple(slot.run_identity for slot in slots),
    }
    claims = ResumeClaimMap(
        claims=tuple(
            claim.model_copy(
                update={"status": EvidenceState.VERIFIED, "evidence_refs": updates[claim.claim_id]}
            )
            if claim.claim_id in updates
            else claim
            for claim in base_claims.claims
        )
    )
    ci = RemoteCIAttestation(
        run_id="123456",
        head_sha=SHA,
        workflow_name=EXPECTED_WORKFLOW,
        conclusion="success",
        successful_gates=EXPECTED_GATES,
        url="https://github.com/example/harnesslab/actions/runs/123456",
    )
    base_manifest = load_release_evidence(ROOT / "release/release-evidence.json")

    def verified(identity: str, value: str) -> EvidenceBinding:
        return EvidenceBinding(state=EvidenceState.VERIFIED, identity=identity, digest=value)

    raw = base_manifest.model_dump(mode="json")
    raw.update(
        {
            "core_corpus": verified(corpus.corpus_id, corpus.digest).model_dump(mode="json"),
            "release_commit": verified(
                f"git:{SHA}", canonical_digest({"git_commit": SHA})
            ).model_dump(mode="json"),
            "experiment_plan": verified(
                f"experiment-plan:{plan.experiment_id}", plan.digest
            ).model_dump(mode="json"),
            "real_matrix": verified(
                f"experiment-report:{plan.experiment_id}", experiment.report_digest
            ).model_dump(mode="json"),
            "paired_lane": verified(
                f"experiment-pair:{pair.pair_id}", pair.source_digest
            ).model_dump(mode="json"),
            "controlled_ablation": verified(
                f"experiment-ablation:{ablation.ablation_id}", ablation.source_digest
            ).model_dump(mode="json"),
            "judge_report": verified(
                f"judge-report:{judge.calibration_id}", judge.report_digest
            ).model_dump(mode="json"),
            "badcase_evidence": [
                verified(
                    f"badcase:{slot.slot_id}",
                    canonical_digest(slot.model_dump(mode="json")),
                ).model_dump(mode="json")
                for slot in slots
            ],
            "resume_claim_map": verified(
                "release/resume-claim-evidence.json", claims.digest
            ).model_dump(mode="json"),
            "remote_ci": verified(f"github-actions:{ci.run_id}", ci.digest).model_dump(mode="json"),
            "paired_claim_policy": PairedClaimPolicy.NO_HARNESS_UPLIFT_CLAIM.value,
            "real_statuses": {
                key: EvidenceState.VERIFIED.value for key in base_manifest.real_statuses
            },
            "core_release_ready": True,
            "real_evidence_authorization_required": False,
        }
    )
    manifest = ReleaseEvidenceManifest.model_validate(raw)
    return {
        "repository_root": ROOT,
        "checked_corpus": corpus,
        "rebuilt_corpus": corpus,
        "release_plan": release_plan,
        "manifest": manifest,
        "claims": claims,
        "badcases": badcases,
        "snapshot": snapshot,
        "ci": ci,
        "local_head": SHA,
    }
