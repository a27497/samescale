from __future__ import annotations

import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.run import RunStatus
from harnesslab.db.models.experiment import ExperimentRecord
from harnesslab.db.models.judgelab import JudgeCalibrationRecord, JudgeEvaluationRecord
from harnesslab.evidence.reader import (
    EvidenceReadError,
    load_normalized_trace,
    trusted_artifact_path,
)
from harnesslab.experiment.outcomes import (
    StatisticalOutcome,
    validate_terminal_run_lifecycle,
)
from harnesslab.experiment.plan import ExperimentPlan
from harnesslab.experiment.report import (
    ExperimentReport,
    build_experiment_report,
    load_verified_experiment_evidence,
)
from harnesslab.judgelab.models import JudgeCalibrationPlan
from harnesslab.judgelab.report import JudgeCalibrationReport
from harnesslab.release.contracts import CoreReleaseError
from harnesslab.release.models import (
    BadCasePlan,
    CanonicalModel,
    CoreCorpusManifest,
    EvidenceState,
    PairedClaimPolicy,
    RealEvidencePlan,
    ReleaseEvidenceManifest,
    ResumeClaimMap,
    SemanticReleaseReceipt,
    StrictModel,
)

EXPECTED_WORKFLOW = " + ".join(f"Gate {letter}" for letter in "ABCDEFGHIJK")
EXPECTED_GATES = tuple(f"Gate {letter}" for letter in "ABCDEFGHIJK")


class RunEvidenceSummary(StrictModel):
    run_id: str
    slot_id: str
    cell_id: str
    task_id: str
    task_version: str
    task_digest: str
    verifier_identity: str
    repeat_index: int
    status: RunStatus
    normalized_outcome: StatisticalOutcome
    source_outcome: str
    evidence_digest: str | None
    safe_trace_available: bool
    normalized_trace_digest: str | None
    safe_trace_facts: tuple[str, ...]


class PairEvidenceSummary(CanonicalModel):
    pair_id: str
    left_cell_id: str
    right_cell_id: str
    total_observations: int
    comparable: int
    partially_comparable: int
    not_comparable: int
    per_task_observations: dict[str, int]
    formal_eligible: bool
    source_digest: str


class AblationEvidenceSummary(CanonicalModel):
    ablation_id: str
    base_cell_id: str
    variant_cell_id: str
    changed_dimension: str
    total_observations: int
    comparable: int
    per_task_observations: dict[str, int]
    formal_eligible: bool
    source_digest: str


class ExperimentEvidenceSummary(StrictModel):
    experiment_id: str
    record_status: str
    plan: ExperimentPlan
    runs: tuple[RunEvidenceSummary, ...]
    report_experiment_id: str
    report_plan_digest: str
    report_run_count: int
    report_digest: str
    pair: PairEvidenceSummary
    ablation: AblationEvidenceSummary
    authoritative_loader_verified: bool


class JudgeEvidenceSummary(StrictModel):
    calibration_id: str
    record_status: str
    plan: JudgeCalibrationPlan
    evaluation_count: int
    completed_evaluation_count: int
    observed_models: tuple[str, ...]
    report_calibration_id: str
    report_plan_digest: str
    report_suite_id: str
    report_suite_version: str
    report_suite_digest: str
    report_digest: str
    l0_override_count: int
    real_judge_smoke: str
    authoritative_report_verified: bool


class AuthoritativeReleaseSnapshot(StrictModel):
    experiment: ExperimentEvidenceSummary
    judge: JudgeEvidenceSummary


class RemoteCIAttestation(CanonicalModel):
    run_id: str = Field(min_length=1, max_length=100)
    head_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    workflow_name: str
    conclusion: Literal["success"]
    successful_gates: tuple[str, ...]
    url: str = Field(min_length=1)


def _binding(manifest: ReleaseEvidenceManifest, name: str, identity: str, digest: str) -> None:
    value = getattr(manifest, name)
    if (
        value.state is not EvidenceState.VERIFIED
        or value.identity != identity
        or value.digest != digest
    ):
        raise CoreReleaseError(f"{name} does not bind authoritative semantic evidence")


def _pair_source_digest(report: ExperimentReport, pair_id: str) -> str:
    statistics = next((item for item in report.pairs if item.pair_id == pair_id), None)
    if statistics is None:
        raise CoreReleaseError("authoritative report omits the planned pair")
    observations = tuple(item for item in report.pair_evidence if item.pair_id == pair_id)
    return canonical_digest(
        {
            "statistics": statistics.model_dump(mode="json"),
            "observations": [item.model_dump(mode="json") for item in observations],
        }
    )


def _ablation_source_digest(report: ExperimentReport, ablation_id: str) -> str:
    statistics = next((item for item in report.ablations if item.ablation_id == ablation_id), None)
    if statistics is None:
        raise CoreReleaseError("authoritative report omits the planned ablation")
    return canonical_digest(statistics.model_dump(mode="json"))


def _summarize_pair(
    report: ExperimentReport, plan: ExperimentPlan, pair_id: str
) -> PairEvidenceSummary:
    definition = next(item for item in plan.paired_comparisons if item.id == pair_id)
    statistics = next(item for item in report.pairs if item.pair_id == pair_id)
    observations = tuple(item for item in report.pair_evidence if item.pair_id == pair_id)
    counts = Counter(item.task_id for item in observations)
    return PairEvidenceSummary(
        pair_id=pair_id,
        left_cell_id=definition.left_cell_id,
        right_cell_id=definition.right_cell_id,
        total_observations=len(observations),
        comparable=statistics.comparable_pairs,
        partially_comparable=statistics.partially_comparable_pairs,
        not_comparable=statistics.not_comparable_pairs,
        per_task_observations=dict(sorted(counts.items())),
        formal_eligible=statistics.formal_eligible,
        source_digest=_pair_source_digest(report, pair_id),
    )


def _summarize_ablation(
    report: ExperimentReport, plan: ExperimentPlan, ablation_id: str
) -> AblationEvidenceSummary:
    definition = next(item for item in plan.ablations if item.id == ablation_id)
    statistics = next(item for item in report.ablations if item.ablation_id == ablation_id)
    comparison = statistics.comparison
    per_task = {item.task_id: item.comparable_pairs for item in comparison.per_task_evidence}
    return AblationEvidenceSummary(
        ablation_id=ablation_id,
        base_cell_id=definition.base_cell_id,
        variant_cell_id=definition.variant_cell_id,
        changed_dimension=definition.changed_dimension,
        total_observations=comparison.total_capability_pairs,
        comparable=comparison.comparable_pairs,
        per_task_observations=dict(sorted(per_task.items())),
        formal_eligible=comparison.formal_eligible,
        source_digest=_ablation_source_digest(report, ablation_id),
    )


async def resolve_authoritative_snapshot(
    database_url: str,
    artifact_roots: tuple[Path, ...],
    *,
    experiment_id: str,
    calibration_id: str,
) -> AuthoritativeReleaseSnapshot:
    """Resolve only through persisted records and the existing authoritative evidence loaders."""

    if not database_url.startswith(("postgresql+psycopg://", "postgresql+asyncpg://")):
        raise CoreReleaseError("final release requires an async-capable PostgreSQL evidence URL")
    engine = create_async_engine(database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            return await _resolve_snapshot_in_session(
                session,
                artifact_roots,
                experiment_id=experiment_id,
                calibration_id=calibration_id,
            )
    finally:
        await engine.dispose()


async def _resolve_snapshot_in_session(
    session: AsyncSession,
    artifact_roots: tuple[Path, ...],
    *,
    experiment_id: str,
    calibration_id: str,
) -> AuthoritativeReleaseSnapshot:
    experiment_record = await session.get(ExperimentRecord, experiment_id)
    if experiment_record is None:
        raise CoreReleaseError("authoritative experiment record does not exist")
    if experiment_record.status != "completed":
        raise CoreReleaseError("authoritative experiment is not completed")

    def guard(path: Path) -> Path:
        return trusted_artifact_path(path, artifact_roots)

    evidence = await load_verified_experiment_evidence(
        session, experiment_id, artifact_path_guard=guard
    )
    report = await build_experiment_report(
        session,
        experiment_id,
        bootstrap_resamples=9_999,
        artifact_path_guard=guard,
    )
    planned_slots = {slot.slot_id: slot for slot in evidence.plan.run_slots}
    run_summaries: list[RunEvidenceSummary] = []
    for run in evidence.runs:
        try:
            validate_terminal_run_lifecycle(run.status, run.normalized_outcome or "")
            status = RunStatus(run.status)
            normalized_outcome = StatisticalOutcome(run.normalized_outcome or "")
        except ValueError as exc:
            raise CoreReleaseError(
                f"persisted run {run.run_id} has an invalid Phase G terminal lifecycle"
            ) from exc
        trace_digest: str | None = None
        trace_facts: tuple[str, ...] = ()
        try:
            trace, trace_digest, _coverage = load_normalized_trace(run, artifact_roots)
            trace_facts = tuple(
                sorted({f"TRACE_EVENT_TYPE:{event.type.value}" for event in trace.events})
            )
        except EvidenceReadError:
            pass
        run_summaries.append(
            RunEvidenceSummary(
                run_id=run.run_id,
                slot_id=run.slot_id,
                cell_id=run.cell_id,
                task_id=run.task_id,
                task_version=run.task_version,
                task_digest=run.task_digest,
                verifier_identity=planned_slots[run.slot_id].task.verifier_identity,
                repeat_index=run.repeat_index,
                status=status,
                normalized_outcome=normalized_outcome,
                source_outcome=run.source_outcome or "",
                evidence_digest=run.evidence_digest,
                safe_trace_available=trace_digest is not None and bool(trace_facts),
                normalized_trace_digest=trace_digest,
                safe_trace_facts=trace_facts,
            )
        )
    if len(evidence.plan.paired_comparisons) != 1 or len(evidence.plan.ablations) != 1:
        raise CoreReleaseError(
            "authoritative ExperimentPlan must declare one pair and one ablation"
        )
    experiment_summary = ExperimentEvidenceSummary(
        experiment_id=experiment_id,
        record_status=experiment_record.status,
        plan=evidence.plan,
        runs=tuple(run_summaries),
        report_experiment_id=report.experiment_id,
        report_plan_digest=report.plan_digest,
        report_run_count=report.plan_run_count,
        report_digest=report.digest,
        pair=_summarize_pair(report, evidence.plan, evidence.plan.paired_comparisons[0].id),
        ablation=_summarize_ablation(report, evidence.plan, evidence.plan.ablations[0].id),
        authoritative_loader_verified=True,
    )

    judge_record = await session.get(JudgeCalibrationRecord, calibration_id)
    if judge_record is None or judge_record.status != "completed":
        raise CoreReleaseError("authoritative Judge calibration is absent or incomplete")
    judge_plan = JudgeCalibrationPlan.model_validate(judge_record.plan_json)
    if judge_plan.plan_digest != judge_record.plan_digest:
        raise CoreReleaseError("persisted Judge plan digest mismatch")
    if judge_record.report_json_path is None or judge_record.report_digest is None:
        raise CoreReleaseError("Judge calibration report identity is absent")
    report_path = trusted_artifact_path(judge_record.report_json_path, artifact_roots)
    try:
        judge_report = JudgeCalibrationReport.model_validate_json(
            report_path.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise CoreReleaseError("Judge calibration report is corrupt") from exc
    if (
        judge_report.calibration_id != judge_record.id
        or judge_report.report_digest != judge_record.report_digest
    ):
        raise CoreReleaseError("Judge calibration report binding mismatch")
    evaluations = tuple(
        (
            await session.scalars(
                select(JudgeEvaluationRecord)
                .where(JudgeEvaluationRecord.calibration_id == calibration_id)
                .order_by(JudgeEvaluationRecord.slot_order)
            )
        ).all()
    )
    observed = tuple(
        sorted({item.observed_judge_model for item in evaluations if item.observed_judge_model})
    )
    judge_summary = JudgeEvidenceSummary(
        calibration_id=calibration_id,
        record_status=judge_record.status,
        plan=judge_plan,
        evaluation_count=len(evaluations),
        completed_evaluation_count=sum(item.status == "completed" for item in evaluations),
        observed_models=observed,
        report_calibration_id=judge_report.calibration_id,
        report_plan_digest=judge_report.plan_digest,
        report_suite_id=judge_report.suite_id,
        report_suite_version=judge_report.suite_version,
        report_suite_digest=judge_report.suite_digest,
        report_digest=judge_report.report_digest,
        l0_override_count=sum(cell.l0_override_count for cell in judge_report.cells),
        real_judge_smoke=judge_report.real_judge_smoke,
        authoritative_report_verified=True,
    )
    return AuthoritativeReleaseSnapshot(experiment=experiment_summary, judge=judge_summary)


def resolve_github_ci(run_id: str) -> RemoteCIAttestation:
    result = subprocess.run(
        (
            "gh",
            "run",
            "view",
            run_id,
            "--json",
            "databaseId,headSha,workflowName,conclusion,jobs,url",
        ),
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    raw = json.loads(result.stdout)
    successful_steps = {
        step.get("name", "")
        for job in raw.get("jobs", [])
        if job.get("conclusion") == "success"
        for step in job.get("steps", [])
        if step.get("conclusion") == "success"
    }
    successful_gates = tuple(
        gate
        for gate in EXPECTED_GATES
        if any(
            f"{gate} verification" in step or f"{gate} contract" in step
            for step in successful_steps
        )
    )
    return RemoteCIAttestation(
        run_id=str(raw["databaseId"]),
        head_sha=raw["headSha"],
        workflow_name=raw["workflowName"],
        conclusion=raw["conclusion"],
        successful_gates=successful_gates,
        url=raw["url"],
    )


def _verify_plan(
    corpus: CoreCorpusManifest,
    release_plan: RealEvidencePlan,
    experiment: ExperimentEvidenceSummary,
) -> None:
    plan = experiment.plan
    if not experiment.authoritative_loader_verified:
        raise CoreReleaseError("experiment did not pass the authoritative manifest loader")
    if (
        experiment.record_status != "completed"
        or plan.experiment_id != release_plan.experiment_id
        or plan.execution_seed != release_plan.execution_seed
    ):
        raise CoreReleaseError("wrong or incomplete authoritative experiment")
    if plan.repeat_count != 5 or len(plan.tasks) != 18 or len(plan.cells) != 7:
        raise CoreReleaseError("authoritative plan does not contain the exact Core matrix")
    if len(plan.run_slots) != 630:
        raise CoreReleaseError("authoritative plan does not contain exactly 630 run slots")
    expected_tasks = {
        (
            item.package_path,
            item.task_id,
            item.version,
            item.task_digest,
            item.workspace_input_identity,
            item.verifier_identity,
        )
        for item in corpus.tasks
    }
    actual_tasks = {
        (
            item.package_path,
            item.task_id,
            item.task_version,
            item.task_digest,
            item.workspace_input_digest,
            item.verifier_identity,
        )
        for item in plan.tasks
    }
    if actual_tasks != expected_tasks:
        raise CoreReleaseError("authoritative ExperimentPlan uses the wrong Core corpus")
    expected_cells = {item.cell_id: item for item in release_plan.cells}
    actual_cells = {item.id: item for item in plan.cells}
    if set(actual_cells) != set(expected_cells):
        raise CoreReleaseError("authoritative ExperimentPlan cell identities drifted")
    expected_harness = {
        "direct-model": "direct-model",
        "codex": "codex",
        "claude-code": "claude-code",
        "deepseek-e1": "deepseek",
    }
    for cell_id, expected in expected_cells.items():
        actual = actual_cells[cell_id]
        if (
            actual.lane.value != expected.lane
            or actual.harness != expected_harness[expected.runtime]
        ):
            raise CoreReleaseError(f"authoritative cell runtime drifted: {cell_id}")
        if (
            expected.requested_model is not None
            and actual.requested_model != expected.requested_model
        ):
            raise CoreReleaseError(f"authoritative cell model drifted: {cell_id}")
        if expected.provider_route is not None and actual.provider_route != expected.provider_route:
            raise CoreReleaseError(f"authoritative cell provider route drifted: {cell_id}")
        if expected.reasoning_effort != actual.reasoning_effort:
            raise CoreReleaseError(f"authoritative cell reasoning effort drifted: {cell_id}")
        if not actual.requested_model or not actual.provider_route:
            raise CoreReleaseError(f"authoritative cell remains unresolved: {cell_id}")

    planned_slots = {item.slot_id: item for item in plan.run_slots}
    expected_slot_keys = {
        (cell.id, task.task_id, task.task_version, task.task_digest, repeat_index)
        for cell in plan.cells
        for task in plan.tasks
        for repeat_index in range(5)
    }
    actual_slot_keys = {
        (
            slot.cell_id,
            slot.task.task_id,
            slot.task.task_version,
            slot.task.task_digest,
            slot.repeat_index,
        )
        for slot in plan.run_slots
    }
    if actual_slot_keys != expected_slot_keys:
        raise CoreReleaseError("authoritative run slots are not the exact matrix expansion")
    for slot in plan.run_slots:
        cell = actual_cells[slot.cell_id]
        if (
            slot.lane != cell.lane
            or slot.requested_model != cell.requested_model
            or slot.provider_route != cell.provider_route
            or slot.profile_identity != cell.profile_identity
            or slot.harness != cell.harness
            or slot.harness_version != cell.harness_version
            or slot.harness_config_identity != cell.harness_config_identity
            or slot.reasoning_effort != cell.reasoning_effort
            or slot.runner_contract != cell.runner_contract
        ):
            raise CoreReleaseError(f"run slot controls drifted from cell {cell.id}")
    runs = {item.slot_id: item for item in experiment.runs}
    if len(runs) != 630 or set(runs) != set(planned_slots):
        raise CoreReleaseError("authoritative persisted run set is not the exact 630 slots")
    if len({item.run_id for item in experiment.runs}) != 630:
        raise CoreReleaseError("authoritative run identities are not unique")
    for slot_id, slot in planned_slots.items():
        run = runs[slot_id]
        if (
            run.cell_id != slot.cell_id
            or run.task_id != slot.task.task_id
            or run.task_version != slot.task.task_version
            or run.task_digest != slot.task.task_digest
            or run.repeat_index != slot.repeat_index
            or not run.source_outcome
        ):
            raise CoreReleaseError(f"persisted run disagrees with slot {slot_id}")
        try:
            validate_terminal_run_lifecycle(run.status, run.normalized_outcome)
        except ValueError as exc:
            raise CoreReleaseError(
                f"persisted run lifecycle disagrees with Phase G for slot {slot_id}"
            ) from exc
    if (
        experiment.report_experiment_id != plan.experiment_id
        or experiment.report_plan_digest != plan.digest
        or experiment.report_run_count != 630
    ):
        raise CoreReleaseError("authoritative ExperimentReport identity or plan binding drifted")


def _verify_pair_and_ablation(
    corpus: CoreCorpusManifest,
    release_plan: RealEvidencePlan,
    manifest: ReleaseEvidenceManifest,
    experiment: ExperimentEvidenceSummary,
) -> None:
    pair = experiment.pair
    expected_pair = release_plan.paired_lane
    plan_pairs = experiment.plan.paired_comparisons
    if len(plan_pairs) != 1 or (
        plan_pairs[0].id,
        plan_pairs[0].left_cell_id,
        plan_pairs[0].right_cell_id,
    ) != (
        expected_pair.pair_id,
        expected_pair.left_cell_id,
        expected_pair.right_cell_id,
    ):
        raise CoreReleaseError("authoritative ExperimentPlan pair definition drifted")
    if (
        pair.pair_id != expected_pair.pair_id
        or pair.left_cell_id != expected_pair.left_cell_id
        or pair.right_cell_id != expected_pair.right_cell_id
        or pair.total_observations != 90
        or pair.comparable + pair.partially_comparable + pair.not_comparable != 90
        or pair.per_task_observations != {item.task_id: 5 for item in corpus.tasks}
    ):
        raise CoreReleaseError("paired lane is not derived from the exact authoritative report")
    if manifest.paired_claim_policy is PairedClaimPolicy.NOT_SELECTED:
        raise CoreReleaseError("final release paired-claim policy is not selected")
    if manifest.paired_claim_policy is PairedClaimPolicy.HARNESS_UPLIFT_CLAIM and (
        pair.comparable != 90 or pair.formal_eligible is not True
    ):
        raise CoreReleaseError("Harness uplift claim lacks 90 genuinely COMPARABLE observations")
    _binding(
        manifest,
        "paired_lane",
        f"experiment-pair:{pair.pair_id}",
        pair.source_digest,
    )

    ablation = experiment.ablation
    expected_ablation = release_plan.ablation
    plan_ablations = experiment.plan.ablations
    if len(plan_ablations) != 1 or (
        plan_ablations[0].id,
        plan_ablations[0].base_cell_id,
        plan_ablations[0].variant_cell_id,
        plan_ablations[0].changed_dimension,
    ) != (
        expected_ablation.ablation_id,
        expected_ablation.base_cell_id,
        expected_ablation.variant_cell_id,
        expected_ablation.changed_dimension,
    ):
        raise CoreReleaseError("authoritative ExperimentPlan ablation definition drifted")
    if (
        ablation.ablation_id != expected_ablation.ablation_id
        or ablation.base_cell_id != expected_ablation.base_cell_id
        or ablation.variant_cell_id != expected_ablation.variant_cell_id
        or ablation.changed_dimension != "reasoning_effort"
        or ablation.total_observations != 90
        or ablation.comparable != 90
        or ablation.per_task_observations != {item.task_id: 5 for item in corpus.tasks}
        or not ablation.formal_eligible
    ):
        raise CoreReleaseError("controlled ablation is not the exact formal n=5 report evidence")
    cells = {item.id: item for item in experiment.plan.cells}
    base = cells[ablation.base_cell_id]
    variant = cells[ablation.variant_cell_id]
    hard_controls = (
        "lane",
        "requested_model",
        "provider_route",
        "profile_reference",
        "harness",
        "harness_version",
        "resource_budget_identity",
        "network_policy",
        "runner_contract",
        "credential_reference",
    )
    drift = [name for name in hard_controls if getattr(base, name) != getattr(variant, name)]
    if drift or base.reasoning_effort == variant.reasoning_effort:
        raise CoreReleaseError(f"controlled ablation hard-control drift: {','.join(drift)}")
    _binding(
        manifest,
        "controlled_ablation",
        f"experiment-ablation:{ablation.ablation_id}",
        ablation.source_digest,
    )


def _verify_judge(
    release_plan: RealEvidencePlan,
    manifest: ReleaseEvidenceManifest,
    judge: JudgeEvidenceSummary,
) -> None:
    plan = judge.plan
    expected = release_plan.judge
    expected_profiles = {item.profile_id: item for item in release_plan.selected_profiles}
    expected_profile = expected_profiles[expected.profile_id]
    if not judge.authoritative_report_verified or judge.record_status != "completed":
        raise CoreReleaseError("Judge evidence did not pass authoritative report verification")
    if (
        plan.calibration_id != judge.calibration_id
        or plan.plan_digest != judge.report_plan_digest
        or plan.suite_id != expected.suite_id
        or plan.suite_version != expected.suite_version
        or plan.suite_digest != expected.suite_digest
        or len(plan.judge_cells) != 1
        or plan.repeat_count != 3
        or len(plan.slots) != 63
        or judge.evaluation_count != 63
        or judge.completed_evaluation_count != 63
        or not judge.observed_models
    ):
        raise CoreReleaseError("Judge plan, suite, model, or evaluation completion drifted")
    if any(
        cell.runner_contract != "provider-adapter-v1"
        or cell.model_profile.requested_model != expected_profile.requested_model
        or cell.model_profile.provider != expected_profile.provider_id
        or cell.model_profile.protocol is not expected_profile.protocol
        or cell.model_profile.credential_reference != expected_profile.credential_reference
        or cell.model_profile.reasoning.max_output_tokens != expected_profile.max_output_tokens
        or cell.model_profile.thinking_mode is not expected_profile.thinking_mode
        or cell.model_profile.thinking_transport is not expected_profile.thinking_transport
        or cell.model_profile.route != expected_profile.route
        for cell in plan.judge_cells
    ):
        raise CoreReleaseError("Judge calibration did not use a real configured Judge profile")
    if judge.observed_models != (expected_profile.requested_model,):
        raise CoreReleaseError("Judge observed model conflicts with the configured Judge profile")
    _binding(
        manifest,
        "judge_suite",
        f"{expected.suite_id}@{expected.suite_version}",
        expected.suite_digest,
    )
    if (
        judge.report_calibration_id != judge.calibration_id
        or judge.report_suite_id != expected.suite_id
        or judge.report_suite_version != expected.suite_version
        or judge.report_suite_digest != expected.suite_digest
        or judge.l0_override_count != 0
        or judge.real_judge_smoke != "VERIFIED"
    ):
        raise CoreReleaseError("Judge report semantics are corrupt or L0 authority was overridden")
    _binding(
        manifest,
        "judge_report",
        f"judge-report:{judge.calibration_id}",
        judge.report_digest,
    )


def _verify_badcases_and_claims(
    manifest: ReleaseEvidenceManifest,
    badcases: BadCasePlan,
    claims: ResumeClaimMap,
    snapshot: AuthoritativeReleaseSnapshot,
) -> None:
    runs = {item.run_id: item for item in snapshot.experiment.runs}
    authoritative_refs = {
        f"experiment-report:{snapshot.experiment.experiment_id}",
        f"experiment-pair:{snapshot.experiment.pair.pair_id}",
        f"experiment-ablation:{snapshot.experiment.ablation.ablation_id}",
        f"judge-report:{snapshot.judge.calibration_id}",
    }
    for index, slot in enumerate(badcases.slots):
        if slot.status is not EvidenceState.VERIFIED or slot.run_identity is None:
            raise CoreReleaseError("all three BadCases require VERIFIED real evidence")
        run_id = slot.run_identity.removeprefix("run:")
        run = runs.get(run_id)
        if run is None or slot.run_identity != f"run:{run.run_id}":
            raise CoreReleaseError(f"BadCase {slot.slot_id} references the wrong run")
        if (
            run.status is not RunStatus.FAILED_SUBJECT
            or run.normalized_outcome is not StatisticalOutcome.CAPABILITY_FAIL
            or run.evidence_digest is None
        ):
            raise CoreReleaseError(
                f"BadCase {slot.slot_id} is not a verifier-backed capability failure"
            )
        task_identity = f"task:{run.task_id}@{run.task_version}#{run.task_digest}"
        required_refs = {
            f"run:{run.run_id}",
            f"cell:{run.cell_id}",
            task_identity,
            f"verifier:{run.verifier_identity}",
            f"manifest:{run.evidence_digest}",
            f"trace:{run.run_id}#{run.normalized_trace_digest}",
        }
        if (
            slot.task_identity != task_identity
            or slot.cell_identity != f"cell:{run.cell_id}"
            or not run.safe_trace_available
            or not set(slot.safe_trace_facts) <= set(run.safe_trace_facts)
            or not required_refs <= set(slot.evidence_refs)
            or slot.verifier_result != f"{run.normalized_outcome}:{run.source_outcome}"
        ):
            raise CoreReleaseError(f"BadCase {slot.slot_id} evidence is not factual")
        binding = manifest.badcase_evidence[index]
        if (
            binding.state is not EvidenceState.VERIFIED
            or binding.identity != f"badcase:{slot.slot_id}"
            or binding.digest != canonical_digest(slot.model_dump(mode="json"))
        ):
            raise CoreReleaseError(f"BadCase {slot.slot_id} release binding drifted")
        authoritative_refs.update(required_refs)

    _binding(manifest, "resume_claim_map", "release/resume-claim-evidence.json", claims.digest)
    by_id = {item.claim_id: item for item in claims.claims}
    real_matrix = by_id.get("real-matrix-results")
    real_judge = by_id.get("real-judge-quality")
    real_badcases = by_id.get("real-badcases")
    if (
        real_matrix is None
        or real_matrix.status is not EvidenceState.VERIFIED
        or f"experiment-report:{snapshot.experiment.experiment_id}" not in real_matrix.evidence_refs
        or real_judge is None
        or real_judge.status is not EvidenceState.VERIFIED
        or f"judge-report:{snapshot.judge.calibration_id}" not in real_judge.evidence_refs
        or real_badcases is None
        or real_badcases.status is not EvidenceState.VERIFIED
    ):
        raise CoreReleaseError("real release claims are not bound to their authoritative evidence")
    uplift = by_id.get("harness-uplift")
    if manifest.paired_claim_policy is PairedClaimPolicy.HARNESS_UPLIFT_CLAIM:
        if (
            uplift is None
            or uplift.status is not EvidenceState.VERIFIED
            or f"experiment-pair:{snapshot.experiment.pair.pair_id}" not in uplift.evidence_refs
        ):
            raise CoreReleaseError("selected Harness uplift claim lacks pair evidence")
    elif uplift is not None and uplift.status is EvidenceState.VERIFIED:
        raise CoreReleaseError("NO_HARNESS_UPLIFT_CLAIM cannot relabel pair evidence as uplift")
    for claim in claims.claims:
        if (
            claim.source_phase == "K-B"
            and claim.status is EvidenceState.VERIFIED
            and (not claim.evidence_refs or not set(claim.evidence_refs) <= authoritative_refs)
        ):
            raise CoreReleaseError(f"real claim has unsupported evidence refs: {claim.claim_id}")


def verify_semantic_final_release(
    *,
    repository_root: Path,
    checked_corpus: CoreCorpusManifest,
    rebuilt_corpus: CoreCorpusManifest,
    release_plan: RealEvidencePlan,
    manifest: ReleaseEvidenceManifest,
    claims: ResumeClaimMap,
    badcases: BadCasePlan,
    snapshot: AuthoritativeReleaseSnapshot,
    ci: RemoteCIAttestation,
    local_head: str,
) -> SemanticReleaseReceipt:
    if checked_corpus != rebuilt_corpus:
        raise CoreReleaseError("checked corpus differs from authoritative reconstruction")
    _binding(manifest, "core_corpus", checked_corpus.corpus_id, checked_corpus.digest)
    if (
        release_plan.corpus_reference != "release/core-corpus.json"
        or release_plan.corpus_digest != checked_corpus.digest
    ):
        raise CoreReleaseError("real-evidence preflight is bound to the wrong corpus")
    commit_digest = canonical_digest({"git_commit": local_head})
    _binding(manifest, "release_commit", f"git:{local_head}", commit_digest)

    _verify_plan(checked_corpus, release_plan, snapshot.experiment)
    _binding(
        manifest,
        "experiment_plan",
        f"experiment-plan:{snapshot.experiment.experiment_id}",
        snapshot.experiment.plan.digest,
    )
    _binding(
        manifest,
        "real_matrix",
        f"experiment-report:{snapshot.experiment.experiment_id}",
        snapshot.experiment.report_digest,
    )
    _verify_pair_and_ablation(checked_corpus, release_plan, manifest, snapshot.experiment)
    _verify_judge(release_plan, manifest, snapshot.judge)
    _verify_badcases_and_claims(manifest, badcases, claims, snapshot)

    if (
        ci.head_sha != local_head
        or ci.workflow_name != EXPECTED_WORKFLOW
        or ci.conclusion != "success"
        or ci.successful_gates != EXPECTED_GATES
    ):
        raise CoreReleaseError("remote CI attestation does not prove exact-head Gates A-K")
    _binding(manifest, "remote_ci", f"github-actions:{ci.run_id}", ci.digest)
    if not manifest.core_release_ready or manifest.real_evidence_authorization_required:
        raise CoreReleaseError("release manifest still reports a hard-stop state")
    if any(state is not EvidenceState.VERIFIED for state in manifest.real_statuses.values()):
        raise CoreReleaseError("one or more REAL_* classes is not VERIFIED")
    tag = subprocess.run(
        ("git", "tag", "--list", "v1.0.0-core"),
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if tag:
        raise CoreReleaseError("v1.0.0-core already exists before semantic authorization")
    return SemanticReleaseReceipt(
        release_manifest_digest=manifest.digest,
        release_head=local_head,
        remote_ci_run_id=ci.run_id,
    )
