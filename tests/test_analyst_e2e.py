from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from harnesslab.analyst.evidence import AnalystEvidenceError, AnalystEvidenceRepository
from harnesslab.analyst.models import (
    AnalysisRequest,
    CompareCellsArgs,
    GetAblationArgs,
    GetTaskContractArgs,
    InspectTraceArgs,
    QueryRunsArgs,
    ToolName,
)
from harnesslab.analyst.service import AnalystService
from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.common import EvaluationLane
from harnesslab.core.config import Settings
from harnesslab.db.models.experiment import (
    ExperimentAblationRecord,
    ExperimentCellRecord,
    ExperimentPairRecord,
    ExperimentRecord,
    ExperimentRunRecord,
)
from harnesslab.db.models.judgelab import JudgeCalibrationRecord
from harnesslab.db.session import create_engine, create_session_factory
from harnesslab.experiment.executor import (
    CodexHarnessBinding,
    ExperimentLaneBinding,
    ExperimentRunExecutor,
    resolved_comparison_profile_identity,
)
from harnesslab.experiment.plan import build_experiment_plan
from harnesslab.experiment.queue import enqueue_plan
from harnesslab.experiment.report import ExperimentReport, build_experiment_report
from harnesslab.experiment.spec import ExperimentCellSpec, ExperimentSpec
from harnesslab.harness_lane.fake import PRIVATE_REASONING_SENTINEL, FakeCodexBackend
from harnesslab.harness_lane.profile import canonical_codex_profile
from harnesslab.harness_lane.runner import CodexHarnessRunner
from harnesslab.sandbox.artifacts import sha256_file
from harnesslab.sandbox.models import ImageIdentity
from harnesslab.tasks.package import TaskPackage
from tests.phase_g_helpers import PYTHON_TASK_PATH, ROOT

ABLATION_EXPERIMENT_ID = "phase-j-controlled-ablation"
NO_ABLATION_EXPERIMENT_ID = "phase-j-no-ablation"
EXPERIMENT_IDS = (ABLATION_EXPERIMENT_ID, NO_ABLATION_EXPERIMENT_ID)


@dataclass(frozen=True)
class PhaseJEvidence:
    factory: async_sessionmaker[AsyncSession]
    artifact_root: Path
    report_root: Path
    controlled_report: Any
    repeated_report: Any
    no_ablation_report: Any
    experiment_report: ExperimentReport
    before_database: str
    after_database: str
    before_artifacts: dict[str, tuple[str, int]]
    after_artifacts: dict[str, tuple[str, int]]
    ablation_run_ids: tuple[str, ...]
    no_ablation_run_id: str
    backend_calls_before: tuple[int, ...]
    backend_calls_after: tuple[int, ...]


def _image() -> ImageIdentity:
    return ImageIdentity(reference="phase-j-fake-codex:1", image_id="sha256:" + "9" * 64)


def _cell(cell_id: str, effort: str) -> tuple[ExperimentCellSpec, Any]:
    profile = canonical_codex_profile(
        _image(), requested_model="fake-shared-model", reasoning_effort=effort
    )
    package = TaskPackage.load(ROOT / PYTHON_TASK_PATH)
    budget_identity = canonical_digest(package.definition.budget.model_dump(mode="json"))
    return (
        ExperimentCellSpec(
            id=cell_id,
            lane=EvaluationLane.HARNESS,
            requested_model="fake-shared-model",
            provider_route=profile.provider_route,
            profile_reference="builtin:phase-j-codex",
            profile_identity=resolved_comparison_profile_identity(profile),
            harness="codex",
            harness_version=profile.codex_cli_version,
            harness_config_identity=profile.fingerprint,
            reasoning_effort=effort,
            resource_budget_identity=budget_identity,
            network_policy="deny",
            runner_contract="codex-harness-v1",
        ),
        profile,
    )


def _plans_and_bindings(
    artifact_root: Path, runtime_root: Path
) -> tuple[tuple[Any, dict[str, ExperimentLaneBinding]], ...]:
    low_cell, low_profile = _cell("codex-low", "low")
    high_cell, high_profile = _cell("codex-high", "high")
    controlled = build_experiment_plan(
        ExperimentSpec(
            experiment_id=ABLATION_EXPERIMENT_ID,
            name="Phase J controlled ablation production fixture",
            task_packages=(PYTHON_TASK_PATH,),
            cells=(low_cell, high_cell),
            repeat_count=1,
            execution_seed=20260824,
            ablations=(
                {
                    "id": "reasoning-effort",
                    "base_cell_id": "codex-low",
                    "variant_cell_id": "codex-high",
                    "changed_dimension": "reasoning_effort",
                },
            ),
        ),
        ROOT,
    )
    single = build_experiment_plan(
        ExperimentSpec(
            experiment_id=NO_ABLATION_EXPERIMENT_ID,
            name="Phase J no-ablation production fixture",
            task_packages=(PYTHON_TASK_PATH,),
            cells=(low_cell,),
            repeat_count=1,
            execution_seed=20260824,
        ),
        ROOT,
    )
    backends = {
        "controlled-low": FakeCodexBackend(),
        "controlled-high": FakeCodexBackend(),
        "single-low": FakeCodexBackend(),
    }
    return (
        (
            controlled,
            {
                "codex-low": CodexHarnessBinding(
                    CodexHarnessRunner(
                        artifact_root=artifact_root,
                        runtime_root=runtime_root / "controlled-low",
                    ),
                    low_profile,
                    backends["controlled-low"],
                ),
                "codex-high": CodexHarnessBinding(
                    CodexHarnessRunner(
                        artifact_root=artifact_root,
                        runtime_root=runtime_root / "controlled-high",
                    ),
                    high_profile,
                    backends["controlled-high"],
                ),
            },
        ),
        (
            single,
            {
                "codex-low": CodexHarnessBinding(
                    CodexHarnessRunner(
                        artifact_root=artifact_root,
                        runtime_root=runtime_root / "single-low",
                    ),
                    low_profile,
                    backends["single-low"],
                )
            },
        ),
    )


def _row(record: object) -> dict[str, object]:
    table = cast_table(record)
    return {column.name: getattr(record, column.name) for column in table.columns}


def cast_table(record: object) -> Any:
    return cast(Any, record).__table__


async def _database_snapshot(session: AsyncSession, experiment_ids: tuple[str, ...]) -> str:
    models = (
        ExperimentRecord,
        ExperimentCellRecord,
        ExperimentPairRecord,
        ExperimentAblationRecord,
        ExperimentRunRecord,
    )
    payload: dict[str, object] = {}
    for model in models:
        rows = tuple((await session.scalars(select(model))).all())
        selected = [
            _row(row)
            for row in rows
            if getattr(row, "experiment_id", getattr(row, "id", None)) in experiment_ids
        ]
        payload[model.__tablename__] = selected
    judge_rows = tuple((await session.scalars(select(JudgeCalibrationRecord))).all())
    payload["judge_calibration"] = [_row(row) for row in judge_rows]
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _artifact_snapshot(root: Path) -> dict[str, tuple[str, int]]:
    return {
        path.relative_to(root).as_posix(): (sha256_file(path), path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


@pytest_asyncio.fixture(scope="module")
async def phase_j_evidence(tmp_path_factory: pytest.TempPathFactory) -> Any:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.fail("DATABASE_URL is required for Gate J production evidence")
    root = tmp_path_factory.mktemp("phase-j")
    artifact_root = root / "source-artifacts"
    runtime_root = root / "runtime"
    report_root = root / "analyst-reports"
    artifact_root.mkdir()
    runtime_root.mkdir()
    engine = create_engine(Settings.without_dotenv(database_url=database_url))
    factory = create_session_factory(engine)
    plans_and_bindings = _plans_and_bindings(artifact_root, runtime_root)
    try:
        async with factory() as cleanup, cleanup.begin():
            await cleanup.execute(
                delete(ExperimentRecord).where(ExperimentRecord.id.in_(EXPERIMENT_IDS))
            )
        fake_backends: list[FakeCodexBackend] = []
        for plan, bindings in plans_and_bindings:
            async with factory() as session, session.begin():
                await enqueue_plan(session, plan)
            for binding in bindings.values():
                assert isinstance(binding, CodexHarnessBinding)
                backend = binding.backend
                assert isinstance(backend, FakeCodexBackend)
                fake_backends.append(backend)
            executor = ExperimentRunExecutor(
                repository_root=ROOT,
                session_factory=factory,
                bindings=bindings,
                owner=f"phase-j-{plan.experiment_id}",
            )
            completed = await executor.run_until_idle(plan.experiment_id)
            assert len(completed) == len(plan.run_slots)

        async with factory() as session:
            before_database = await _database_snapshot(session, EXPERIMENT_IDS)
            experiment_report = await build_experiment_report(
                session, ABLATION_EXPERIMENT_ID, bootstrap_resamples=99
            )
            controlled_runs = tuple(
                (
                    await session.scalars(
                        select(ExperimentRunRecord)
                        .where(ExperimentRunRecord.experiment_id == ABLATION_EXPERIMENT_ID)
                        .order_by(ExperimentRunRecord.slot_order)
                    )
                ).all()
            )
            no_ablation_run = await session.scalar(
                select(ExperimentRunRecord).where(
                    ExperimentRunRecord.experiment_id == NO_ABLATION_EXPERIMENT_ID
                )
            )
        assert no_ablation_run is not None
        before_artifacts = _artifact_snapshot(artifact_root)
        backend_calls_before = tuple(len(backend.plans) for backend in fake_backends)

        async with factory() as session:
            service = AnalystService(
                session,
                repository_root=ROOT,
                artifact_roots=(artifact_root,),
                report_root=report_root,
            )
            controlled = await service.analyze(
                AnalysisRequest(
                    experiment_id=ABLATION_EXPERIMENT_ID,
                    question="What does the controlled reasoning-effort ablation show?",
                )
            )
        async with factory() as session:
            repeated = await AnalystService(
                session,
                repository_root=ROOT,
                artifact_roots=(artifact_root,),
                report_root=report_root,
            ).analyze(
                AnalysisRequest(
                    experiment_id=ABLATION_EXPERIMENT_ID,
                    question="What does the controlled reasoning-effort ablation show?",
                )
            )
        async with factory() as session:
            no_ablation = await AnalystService(
                session,
                repository_root=ROOT,
                artifact_roots=(artifact_root,),
                report_root=report_root,
            ).analyze(
                AnalysisRequest(
                    experiment_id=NO_ABLATION_EXPERIMENT_ID,
                    question="Why did this configuration produce its observed result?",
                )
            )

        backend_calls_after = tuple(len(backend.plans) for backend in fake_backends)
        async with factory() as session:
            after_database = await _database_snapshot(session, EXPERIMENT_IDS)
        after_artifacts = _artifact_snapshot(artifact_root)
        if evidence_path := os.environ.get("HARNESSLAB_GATE_J_EVIDENCE_PATH"):
            Path(evidence_path).write_text(
                json.dumps(
                    {
                        "ablation_id": "reasoning-effort",
                        "analysis_id": controlled.report.analysis_id,
                        "decision_iterations": controlled.report.execution.decision_iterations,
                        "evidence_count": len(controlled.report.evidence_catalog),
                        "no_ablation_hypotheses": len(no_ablation.report.hypotheses),
                        "read_only_database": before_database == after_database,
                        "read_only_source_artifacts": before_artifacts == after_artifacts,
                        "report_digest": controlled.report.digest,
                        "tool_calls": controlled.report.execution.tool_calls,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
        yield PhaseJEvidence(
            factory=factory,
            artifact_root=artifact_root,
            report_root=report_root,
            controlled_report=controlled.report,
            repeated_report=repeated.report,
            no_ablation_report=no_ablation.report,
            experiment_report=experiment_report,
            before_database=before_database,
            after_database=after_database,
            before_artifacts=before_artifacts,
            after_artifacts=after_artifacts,
            ablation_run_ids=tuple(run.run_id for run in controlled_runs),
            no_ablation_run_id=no_ablation_run.run_id,
            backend_calls_before=backend_calls_before,
            backend_calls_after=backend_calls_after,
        )
    finally:
        async with factory() as cleanup, cleanup.begin():
            await cleanup.execute(
                delete(ExperimentRecord).where(ExperimentRecord.id.in_(EXPERIMENT_IDS))
            )
        await engine.dispose()


@pytest.mark.integration
async def test_production_queue_executor_manifests_report_and_ablation_are_read_and_cited(
    phase_j_evidence: PhaseJEvidence,
) -> None:
    report = phase_j_evidence.controlled_report
    refs = {entry.ref.id for entry in report.evidence_catalog}
    ablation_ref = f"ablation:{ABLATION_EXPERIMENT_ID}:reasoning-effort"
    assert ablation_ref in refs
    assert ablation_ref in report.ablation_refs
    assert any(ablation_ref in claim.evidence_refs for claim in report.verified_facts)
    entry = next(item for item in report.evidence_catalog if item.ref.id == ablation_ref)
    data = entry.data_by_tool[ToolName.GET_ABLATION.value]
    assert data["changed_dimension"] == "reasoning_effort"
    assert data["base_cell_id"] == "codex-low"
    assert data["variant_cell_id"] == "codex-high"
    assert data["partially_comparable_pairs"] == 1
    assert not data["formal_eligible"]


@pytest.mark.integration
async def test_compare_cells_reuses_approved_report_statistics_and_comparability(
    phase_j_evidence: PhaseJEvidence,
) -> None:
    report = phase_j_evidence.controlled_report
    approved = {
        cell.cell_id: cell.model_dump(mode="json")
        for cell in phase_j_evidence.experiment_report.cells
    }
    for cell_id in ("codex-low", "codex-high"):
        entry = next(
            item
            for item in report.evidence_catalog
            if item.ref.id == f"cell:{ABLATION_EXPERIMENT_ID}:{cell_id}"
        )
        assert entry.data_by_tool["compare_cells"]["statistics"] == approved[cell_id]
    assert phase_j_evidence.experiment_report.ablations[0].comparison.comparable_pairs == 0


@pytest.mark.integration
async def test_no_ablation_causal_attribution_remains_hypothesis(
    phase_j_evidence: PhaseJEvidence,
) -> None:
    report = phase_j_evidence.no_ablation_report
    assert report.ablation_refs == ()
    assert report.hypotheses
    assert "does not establish a causal attribution" in report.hypotheses[0].statement
    assert "controlled ablation" in (report.hypotheses[0].additional_evidence_needed or "")
    assert all("caus" not in claim.statement.lower() for claim in report.verified_facts)


@pytest.mark.integration
async def test_analysis_is_read_only_for_database_artifacts_judge_and_execution(
    phase_j_evidence: PhaseJEvidence,
) -> None:
    assert phase_j_evidence.before_database == phase_j_evidence.after_database
    assert phase_j_evidence.before_artifacts == phase_j_evidence.after_artifacts
    assert phase_j_evidence.backend_calls_before == phase_j_evidence.backend_calls_after
    report_files = sorted(path.name for path in phase_j_evidence.report_root.rglob("*"))
    assert report_files.count("report.json") == 2
    assert report_files.count("report.md") == 2


@pytest.mark.integration
async def test_scope_denies_cross_experiment_runs_cells_tasks_and_ablations(
    phase_j_evidence: PhaseJEvidence,
) -> None:
    async with phase_j_evidence.factory() as session:
        repository = AnalystEvidenceRepository(
            session,
            experiment_id=ABLATION_EXPERIMENT_ID,
            repository_root=ROOT,
            artifact_roots=(phase_j_evidence.artifact_root,),
        )
        with pytest.raises(AnalystEvidenceError, match="outside"):
            await repository.inspect_trace(
                InspectTraceArgs(run_id=phase_j_evidence.no_ablation_run_id)
            )
        with pytest.raises(AnalystEvidenceError, match="outside"):
            await repository.query_runs(QueryRunsArgs(cell_id="unknown"))
        with pytest.raises(AnalystEvidenceError, match="outside"):
            await repository.get_task_contract(GetTaskContractArgs(task_id="unknown"))
        with pytest.raises(AnalystEvidenceError, match="outside"):
            await repository.get_ablation(GetAblationArgs(ablation_id="unknown"))


@pytest.mark.integration
async def test_trace_is_digest_verified_normalized_and_private_reasoning_is_withheld(
    phase_j_evidence: PhaseJEvidence,
) -> None:
    report_text = phase_j_evidence.controlled_report.canonical_json()
    trace_entries = [
        entry
        for entry in phase_j_evidence.controlled_report.evidence_catalog
        if entry.ref.id.startswith("trace:")
    ]
    assert trace_entries
    reasoning = [
        entry
        for entry in trace_entries
        if entry.data_by_tool["inspect_trace"].get("type") == "REASONING_PRESENT"
    ]
    assert reasoning
    assert reasoning[0].data_by_tool["inspect_trace"]["summary"] == (
        "Reasoning was present; private content is withheld."
    )
    assert PRIVATE_REASONING_SENTINEL not in report_text
    assert "native" not in " ".join(entry.ref.id for entry in trace_entries).lower()


@pytest.mark.integration
async def test_task_contract_hides_verifier_oracle_content_and_returns_safe_identity(
    phase_j_evidence: PhaseJEvidence,
) -> None:
    entry = next(
        item
        for item in phase_j_evidence.controlled_report.evidence_catalog
        if item.ref.id.startswith("task:")
    )
    data = entry.data_by_tool["get_task_contract"]
    assert "instruction" in data
    assert "budget" in data
    assert "expected_tools" in data
    assert "verifier_identity" in data
    assert "oracle" not in data
    assert "entrypoint" not in json.dumps(data)


@pytest.mark.integration
async def test_fake_analyst_e2e_is_deterministic_bounded_and_report_safe(
    phase_j_evidence: PhaseJEvidence,
) -> None:
    first = phase_j_evidence.controlled_report
    second = phase_j_evidence.repeated_report
    assert first.canonical_json() == second.canonical_json()
    assert first.digest == second.digest
    assert first.execution.decision_iterations == 2
    assert first.execution.tool_calls == 6
    text = first.canonical_json() + first.markdown()
    assert "/home/" not in text
    assert "Authorization:" not in text
    assert "api_key" not in text.lower()
    assert PRIVATE_REASONING_SENTINEL not in text
    assert all(
        ref in {entry.ref.id for entry in first.evidence_catalog}
        for claim in (*first.verified_facts, *first.hypotheses)
        for ref in claim.evidence_refs
    )


@pytest.mark.integration
async def test_repository_methods_are_read_only_and_structured_not_arbitrary_sql_or_paths(
    phase_j_evidence: PhaseJEvidence,
) -> None:
    async with phase_j_evidence.factory() as session:
        repository = AnalystEvidenceRepository(
            session,
            experiment_id=ABLATION_EXPERIMENT_ID,
            repository_root=ROOT,
            artifact_roots=(phase_j_evidence.artifact_root,),
        )
        runs = await repository.query_runs(QueryRunsArgs(limit=1))
        comparison = await repository.compare_cells(
            CompareCellsArgs(left_cell_id="codex-low", right_cell_id="codex-high")
        )
        assert len(runs) == 1
        assert {item.tool for item in comparison} == {ToolName.COMPARE_CELLS}
        assert not hasattr(repository, "execute_sql")
        assert not hasattr(repository, "read_path")


def test_gate_j_langgraph_dependency_is_exact_and_no_agent_expansion() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")
    graph_source = (ROOT / "src/harnesslab/analyst/graph.py").read_text(encoding="utf-8")
    package_source = "\n".join(
        path.read_text(encoding="utf-8") for path in (ROOT / "src/harnesslab/analyst").glob("*.py")
    )
    assert '"langgraph==1.2.11"' in pyproject
    assert 'name = "langgraph"\nversion = "1.2.11"' in lock
    assert "StateGraph" in graph_source
    forbidden = (
        "create_react_agent",
        "vectorstore",
        "retriever",
        "redis",
        "celery",
        "kafka",
        "rocketmq",
        "kubernetes",
        "multi_agent",
    )
    assert not any(token in package_source.lower() for token in forbidden)
