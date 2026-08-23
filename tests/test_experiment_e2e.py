from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from sqlalchemy import delete, select

from harnesslab.comparability.models import ComparabilityStatus, canonical_digest
from harnesslab.contracts.common import EvaluationLane, Protocol
from harnesslab.contracts.model import ModelProfile, ReasoningProfile
from harnesslab.core.config import Settings
from harnesslab.db.models.experiment import ExperimentRecord, ExperimentRunRecord
from harnesslab.db.session import create_engine, create_session_factory
from harnesslab.experiment.executor import (
    CodexHarnessBinding,
    DirectModelBinding,
    ExperimentLaneBinding,
    ExperimentRunExecutor,
    resolved_comparison_profile_identity,
)
from harnesslab.experiment.plan import build_experiment_plan
from harnesslab.experiment.queue import enqueue_plan
from harnesslab.experiment.report import ExperimentReportError, build_experiment_report
from harnesslab.experiment.spec import ExperimentCellSpec, ExperimentSpec
from harnesslab.harness_lane.fake import FakeCodexBackend
from harnesslab.harness_lane.profile import canonical_codex_profile
from harnesslab.harness_lane.runner import CodexHarnessRunner
from harnesslab.model_lane.fake import FakeDirectProvider
from harnesslab.model_lane.runner import DirectModelRunner
from harnesslab.sandbox.models import ImageIdentity
from harnesslab.tasks.package import TaskPackage
from tests.phase_g_helpers import PYTHON_TASK_PATH, ROOT

PATCH = (
    '{"version":1,"operations":[{"op":"write","path":"calculator.py",'
    '"content":"def clamp(value: int, lower: int, upper: int) -> int:\\n'
    '    return max(lower, min(value, upper))\\n"}]}'
)


def _image() -> ImageIdentity:
    return ImageIdentity(
        reference="phase-g-fake-codex:1",
        image_id="sha256:" + "7" * 64,
    )


def _cell(
    cell_id: str,
    lane: EvaluationLane,
    *,
    provider_route: str,
    profile_identity: str,
    harness_config_identity: str,
    reasoning_effort: str | None,
    harness: str,
    harness_version: str,
    runner_contract: str,
) -> ExperimentCellSpec:
    package = TaskPackage.load(ROOT / PYTHON_TASK_PATH)
    budget = canonical_digest(package.definition.budget.model_dump(mode="json"))
    return ExperimentCellSpec(
        id=cell_id,
        lane=lane,
        requested_model="fake-shared-model",
        provider_route=provider_route,
        profile_reference=(
            "builtin:phase-g-direct" if lane is EvaluationLane.MODEL else "builtin:phase-g-codex"
        ),
        profile_identity=profile_identity,
        harness=harness,
        harness_version=harness_version,
        harness_config_identity=harness_config_identity,
        reasoning_effort=reasoning_effort,
        resource_budget_identity=budget,
        network_policy="deny",
        runner_contract=runner_contract,
    )


@pytest.mark.integration
async def test_keyless_experiment_e2e_uses_queue_runners_manifests_and_report(
    database_url: str, tmp_path: Path
) -> None:
    direct_profile = ModelProfile(
        requested_model="fake-shared-model",
        provider="fake-provider",
        base_url="https://fake.invalid/v1",
        route="/responses",
        protocol=Protocol.RESPONSES,
        reasoning=ReasoningProfile(effort="low", max_output_tokens=2048),
    )
    codex_low = canonical_codex_profile(
        _image(), requested_model="fake-shared-model", reasoning_effort="low"
    )
    codex_high = canonical_codex_profile(
        _image(), requested_model="fake-shared-model", reasoning_effort="high"
    )
    direct_identity = resolved_comparison_profile_identity(direct_profile)
    cells = (
        _cell(
            "direct",
            EvaluationLane.MODEL,
            provider_route="fake-provider|responses|https://fake.invalid/v1/responses",
            profile_identity=direct_identity,
            harness_config_identity=canonical_digest(direct_profile.model_dump(mode="json")),
            reasoning_effort="low",
            harness="direct-model",
            harness_version="evidence-schema-1",
            runner_contract="direct-model-v1",
        ),
        _cell(
            "codex-low",
            EvaluationLane.HARNESS,
            provider_route=codex_low.provider_route,
            profile_identity=resolved_comparison_profile_identity(codex_low),
            harness_config_identity=codex_low.fingerprint,
            reasoning_effort="low",
            harness="codex",
            harness_version=codex_low.codex_cli_version,
            runner_contract="codex-harness-v1",
        ),
        _cell(
            "codex-high",
            EvaluationLane.HARNESS,
            provider_route=codex_high.provider_route,
            profile_identity=resolved_comparison_profile_identity(codex_high),
            harness_config_identity=codex_high.fingerprint,
            reasoning_effort="high",
            harness="codex",
            harness_version=codex_high.codex_cli_version,
            runner_contract="codex-harness-v1",
        ),
    )
    experiment_id = "phase-g-e2e-authoritative"
    spec = ExperimentSpec(
        experiment_id=experiment_id,
        name="Phase G keyless queue-to-report E2E",
        task_packages=(PYTHON_TASK_PATH,),
        cells=cells,
        repeat_count=3,
        execution_seed=20260823,
        comparison_intent="HARNESS_UPLIFT",
        paired_comparisons=(
            {
                "id": "direct-vs-codex",
                "left_cell_id": "direct",
                "right_cell_id": "codex-low",
            },
        ),
        ablations=(
            {
                "id": "codex-effort",
                "base_cell_id": "codex-low",
                "variant_cell_id": "codex-high",
                "changed_dimension": "reasoning_effort",
            },
        ),
    )
    plan = build_experiment_plan(spec, ROOT)
    settings = Settings.without_dotenv(database_url=database_url)
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    artifacts = tmp_path / "artifacts"
    runtime = tmp_path / "runtime"
    bindings: dict[str, ExperimentLaneBinding] = {
        "direct": DirectModelBinding(
            DirectModelRunner(
                artifact_root=artifacts,
                runtime_root=runtime / "direct",
                allow_custom_endpoint=True,
            ),
            direct_profile,
            FakeDirectProvider(PATCH, observed_model="fake-shared-model"),
        ),
        "codex-low": CodexHarnessBinding(
            CodexHarnessRunner(
                artifact_root=artifacts,
                runtime_root=runtime / "codex-low",
            ),
            codex_low,
            FakeCodexBackend(),
        ),
        "codex-high": CodexHarnessBinding(
            CodexHarnessRunner(
                artifact_root=artifacts,
                runtime_root=runtime / "codex-high",
            ),
            codex_high,
            FakeCodexBackend(),
        ),
    }
    try:
        async with factory() as cleanup, cleanup.begin():
            await cleanup.execute(
                delete(ExperimentRecord).where(ExperimentRecord.id == experiment_id)
            )
        async with factory() as session, session.begin():
            enqueued = await enqueue_plan(session, plan)
        assert enqueued.logical_run_count == 9

        executor = ExperimentRunExecutor(
            repository_root=ROOT,
            session_factory=factory,
            bindings=bindings,
            owner="phase-g-e2e-worker",
        )
        completed = await executor.run_until_idle(experiment_id)
        assert len(completed) == 9

        async with factory() as session:
            first = await build_experiment_report(session, experiment_id, bootstrap_resamples=199)
            second = await build_experiment_report(session, experiment_id, bootstrap_resamples=199)
            persisted_runs = tuple(
                (
                    await session.scalars(
                        select(ExperimentRunRecord)
                        .where(ExperimentRunRecord.experiment_id == experiment_id)
                        .order_by(ExperimentRunRecord.slot_order)
                    )
                ).all()
            )
            persisted_experiment = await session.get(ExperimentRecord, experiment_id)

        assert first.canonical_json() == second.canonical_json()
        assert first.digest == second.digest
        assert first.markdown() == second.markdown()
        assert first.plan_run_count == 9
        assert persisted_experiment is not None
        assert persisted_experiment.status == "completed"
        assert persisted_experiment.started_at is not None
        assert persisted_experiment.finished_at is not None
        assert all(cell.completed_capability_runs == 3 for cell in first.cells)
        assert all(cell.evidence_tier.value == "INFORMAL" for cell in first.cells)
        assert first.pairs[0].not_comparable_pairs == 3
        assert first.pairs[0].comparable_pairs == 0
        assert not first.pairs[0].formal_eligible
        assert "HARD_CONTROL_MISMATCH" in first.pairs[0].excluded_reason_counts
        assert first.ablations[0].comparison.partially_comparable_pairs == 3
        assert not first.ablations[0].comparison.formal_eligible
        assert "OBSERVED_MODEL_MISSING" in (first.ablations[0].comparison.excluded_reason_counts)
        assert first.formal_ranking == ()
        assert all(run.artifact_manifest_path for run in persisted_runs)
        assert all(Path(run.artifact_manifest_path or "").is_file() for run in persisted_runs)
        assert all(run.evidence_digest for run in persisted_runs)
        assert {
            evidence.comparability
            for evidence in first.pair_evidence
            if evidence.pair_id == "direct-vs-codex"
        } == {ComparabilityStatus.NOT_COMPARABLE}
        if evidence_path := os.environ.get("HARNESSLAB_GATE_G_EVIDENCE_PATH"):
            Path(evidence_path).write_text(
                json.dumps(
                    {
                        "ablation_partial_pairs": (
                            first.ablations[0].comparison.partially_comparable_pairs
                        ),
                        "artifact_manifest_count": sum(
                            Path(run.artifact_manifest_path or "").is_file()
                            for run in persisted_runs
                        ),
                        "matrix_run_count": first.plan_run_count,
                        "p_lane_not_comparable_pairs": first.pairs[0].not_comparable_pairs,
                        "plan_digest": first.plan_digest,
                        "report_digest": first.digest,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
        direct_run = next(run for run in persisted_runs if run.cell_id == "direct")
        mutated_slot = dict(direct_run.slot_json)
        mutated_slot["profile_identity"] = canonical_digest({"mutated": True})
        async with factory() as session, session.begin():
            persisted = await session.get(ExperimentRunRecord, direct_run.run_id)
            assert persisted is not None
            persisted.slot_json = mutated_slot
        async with factory() as session:
            with pytest.raises(ExperimentReportError, match="immutable plan controls"):
                await build_experiment_report(session, experiment_id, bootstrap_resamples=99)
    finally:
        async with factory() as cleanup, cleanup.begin():
            await cleanup.execute(
                delete(ExperimentRecord).where(ExperimentRecord.id == experiment_id)
            )
        await engine.dispose()
