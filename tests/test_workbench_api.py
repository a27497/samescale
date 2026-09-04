from __future__ import annotations

import json
import os
import shutil
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from harnesslab.api.app import create_app
from harnesslab.api.workbench_dependencies import workbench_artifact_roots, workbench_session
from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.common import EvaluationLane, Protocol
from harnesslab.contracts.model import ModelProfile, ReasoningProfile
from harnesslab.core.config import Settings
from harnesslab.db.models.experiment import ExperimentRecord, ExperimentRunRecord
from harnesslab.db.models.judgelab import JudgeCalibrationRecord
from harnesslab.db.session import create_engine, create_session_factory
from harnesslab.experiment.executor import (
    CodexHarnessBinding,
    DirectModelBinding,
    ExperimentLaneBinding,
    ExperimentRunExecutor,
    resolved_comparison_profile_identity,
)
from harnesslab.experiment.plan import ExperimentPlan, build_experiment_plan
from harnesslab.experiment.queue import enqueue_plan
from harnesslab.experiment.spec import ExperimentSpec
from harnesslab.harness_lane.adapter import CodexExecutionPlan
from harnesslab.harness_lane.fake import FakeCodexBackend, FakeCodexScenario
from harnesslab.harness_lane.models import CodexProcessCapture
from harnesslab.harness_lane.profile import canonical_codex_profile
from harnesslab.harness_lane.runner import CodexHarnessRunner
from harnesslab.judgelab.calibration import execute_calibration
from harnesslab.judgelab.plan import build_calibration_plan, load_calibration_spec
from harnesslab.judgelab.suite import load_judge_definition, load_judge_suite
from harnesslab.model_lane.fake import FakeDirectProvider
from harnesslab.model_lane.runner import DirectModelRunner
from harnesslab.sandbox.artifacts import sha256_file
from harnesslab.tasks.package import TaskPackage
from tests.phase_g_helpers import PYTHON_TASK_PATH, ROOT
from tests.test_experiment_e2e import PATCH, _cell, _image

SUITE_ROOT = ROOT / "judge_suites/core-calibration/1.0.0"
REGRESSION_EXPERIMENT_IDS = ("phase-i-matrix-baseline", "phase-i-matrix-candidate")
MULTI_TASK_EXPERIMENT_ID = "phase-i-matrix-multi-task"
EXPERIMENT_IDS = (*REGRESSION_EXPERIMENT_IDS, MULTI_TASK_EXPERIMENT_ID)
TYPESCRIPT_TASK_PATH = "tasks/micro-typescript-clamp/1.0.0"
CALIBRATION_ID = "phase-i-judge-keyless"
PRIVATE_SENTINEL = "PRIVATE_REASONING_SENTINEL"


@dataclass(frozen=True)
class PhaseIEvidence:
    factory: async_sessionmaker[AsyncSession]
    app: Any
    baseline_id: str
    candidate_id: str
    multi_task_id: str
    calibration_id: str
    trace_run_id: str
    no_trace_run_id: str


class TaskSelectiveFakeCodexBackend:
    """Deterministically solves Python while leaving TypeScript unchanged."""

    @property
    def artifact_secret_values(self) -> tuple[str, ...]:
        return ()

    async def run(self, plan: CodexExecutionPlan) -> CodexProcessCapture:
        scenario = (
            FakeCodexScenario.SOLVE
            if plan.task_id == "micro-python-clamp"
            else FakeCodexScenario.FILE_CHANGE_LIE
        )
        return await FakeCodexBackend(scenario).run(plan)


def _matrix_plan(experiment_id: str) -> tuple[ExperimentPlan, dict[str, ExperimentLaneBinding]]:
    is_candidate = experiment_id == REGRESSION_EXPERIMENT_IDS[1]
    direct_requested_model = "fake-model-a"
    codex_low_requested_model = "fake-model-b" if is_candidate else "fake-shared-model"
    direct_profile = ModelProfile(
        requested_model=direct_requested_model,
        provider="fake-provider",
        base_url="https://fake.invalid/v1",
        route="/responses",
        protocol=Protocol.RESPONSES,
        reasoning=ReasoningProfile(effort="low", max_output_tokens=2048),
    )
    codex_low = canonical_codex_profile(
        _image(), requested_model=codex_low_requested_model, reasoning_effort="low"
    )
    codex_high = canonical_codex_profile(
        _image(), requested_model="fake-shared-model", reasoning_effort="high"
    )
    package = TaskPackage.load(ROOT / PYTHON_TASK_PATH)
    budget_identity = canonical_digest(package.definition.budget.model_dump(mode="json"))
    direct_cell = _cell(
        "direct",
        EvaluationLane.MODEL,
        provider_route="fake-provider|responses|https://fake.invalid/v1/responses",
        profile_identity=resolved_comparison_profile_identity(direct_profile),
        harness_config_identity=canonical_digest(direct_profile.model_dump(mode="json")),
        reasoning_effort="low",
        harness="direct-model",
        harness_version="evidence-schema-1",
        runner_contract="direct-model-v1",
    ).model_copy(update={"requested_model": direct_requested_model})
    cells = (
        direct_cell,
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
        ).model_copy(update={"requested_model": codex_low_requested_model}),
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
    assert all(cell.resource_budget_identity == budget_identity for cell in cells)
    plan = build_experiment_plan(
        ExperimentSpec(
            experiment_id=experiment_id,
            name=f"Phase I keyless Matrix {experiment_id}",
            task_packages=(PYTHON_TASK_PATH,),
            cells=cells,
            repeat_count=3,
            execution_seed=20260824,
            comparison_intent="HARNESS_UPLIFT",
            paired_comparisons=(
                ()
                if is_candidate
                else (
                    {
                        "id": "direct-vs-codex",
                        "left_cell_id": "direct",
                        "right_cell_id": "codex-low",
                    },
                )
            ),
            ablations=(
                ()
                if is_candidate
                else (
                    {
                        "id": "codex-effort",
                        "base_cell_id": "codex-low",
                        "variant_cell_id": "codex-high",
                        "changed_dimension": "reasoning_effort",
                    },
                )
            ),
        ),
        ROOT,
    )
    return plan, {
        "direct": DirectModelBinding(
            DirectModelRunner(
                artifact_root=ROOT / ".phase-i-test-artifacts",
                runtime_root=ROOT / ".phase-i-test-runtime" / experiment_id / "direct",
                allow_custom_endpoint=True,
            ),
            direct_profile,
            FakeDirectProvider(PATCH, observed_model=direct_requested_model),
        ),
        "codex-low": CodexHarnessBinding(
            CodexHarnessRunner(
                artifact_root=ROOT / ".phase-i-test-artifacts",
                runtime_root=ROOT / ".phase-i-test-runtime" / experiment_id / "codex-low",
            ),
            codex_low,
            TaskSelectiveFakeCodexBackend(),
        ),
        "codex-high": CodexHarnessBinding(
            CodexHarnessRunner(
                artifact_root=ROOT / ".phase-i-test-artifacts",
                runtime_root=ROOT / ".phase-i-test-runtime" / experiment_id / "codex-high",
            ),
            codex_high,
            TaskSelectiveFakeCodexBackend(),
        ),
    }


def _multi_task_matrix_plan() -> tuple[ExperimentPlan, dict[str, ExperimentLaneBinding]]:
    codex_low = canonical_codex_profile(
        _image(), requested_model="fake-shared-model", reasoning_effort="low"
    )
    codex_high = canonical_codex_profile(
        _image(), requested_model="fake-shared-model", reasoning_effort="high"
    )
    cells = (
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
        _cell(
            "codex-unpaired",
            EvaluationLane.HARNESS,
            provider_route=codex_low.provider_route,
            profile_identity=resolved_comparison_profile_identity(codex_low),
            harness_config_identity=codex_low.fingerprint,
            reasoning_effort="low",
            harness="codex",
            harness_version=codex_low.codex_cli_version,
            runner_contract="codex-harness-v1",
        ),
    )
    plan = build_experiment_plan(
        ExperimentSpec(
            experiment_id=MULTI_TASK_EXPERIMENT_ID,
            name="Phase I authoritative multi-task Matrix",
            task_packages=(PYTHON_TASK_PATH, TYPESCRIPT_TASK_PATH),
            cells=cells,
            repeat_count=3,
            execution_seed=20260825,
            comparison_intent="HARNESS_UPLIFT",
            ablations=(
                {
                    "id": "codex-effort-treatment",
                    "base_cell_id": "codex-low",
                    "variant_cell_id": "codex-high",
                    "changed_dimension": "reasoning_effort",
                },
            ),
        ),
        ROOT,
    )
    artifact_root = ROOT / ".phase-i-test-artifacts"
    return plan, {
        "codex-low": CodexHarnessBinding(
            CodexHarnessRunner(
                artifact_root=artifact_root,
                runtime_root=ROOT / ".phase-i-test-runtime" / MULTI_TASK_EXPERIMENT_ID / "low",
            ),
            codex_low,
            TaskSelectiveFakeCodexBackend(),
        ),
        "codex-high": CodexHarnessBinding(
            CodexHarnessRunner(
                artifact_root=artifact_root,
                runtime_root=ROOT / ".phase-i-test-runtime" / MULTI_TASK_EXPERIMENT_ID / "high",
            ),
            codex_high,
            TaskSelectiveFakeCodexBackend(),
        ),
        "codex-unpaired": CodexHarnessBinding(
            CodexHarnessRunner(
                artifact_root=artifact_root,
                runtime_root=(
                    ROOT / ".phase-i-test-runtime" / MULTI_TASK_EXPERIMENT_ID / "unpaired"
                ),
            ),
            codex_low,
            TaskSelectiveFakeCodexBackend(),
        ),
    }


@pytest_asyncio.fixture(scope="module")
async def phase_i_evidence(
    tmp_path_factory: pytest.TempPathFactory,
) -> AsyncIterator[PhaseIEvidence]:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.fail("DATABASE_URL is required for Gate I persisted evidence")
    engine = create_engine(Settings.without_dotenv(database_url=database_url))
    factory = create_session_factory(engine)
    artifact_root = ROOT / ".phase-i-test-artifacts"
    runtime_root = ROOT / ".phase-i-test-runtime"
    shutil.rmtree(artifact_root, ignore_errors=True)
    shutil.rmtree(runtime_root, ignore_errors=True)
    artifact_root.mkdir(exist_ok=True)
    runtime_root.mkdir(exist_ok=True)
    async with factory() as cleanup, cleanup.begin():
        await cleanup.execute(
            delete(ExperimentRecord).where(ExperimentRecord.id.in_(EXPERIMENT_IDS))
        )
        await cleanup.execute(
            delete(JudgeCalibrationRecord).where(JudgeCalibrationRecord.id == CALIBRATION_ID)
        )

    for experiment_id in EXPERIMENT_IDS:
        plan, bindings = (
            _multi_task_matrix_plan()
            if experiment_id == MULTI_TASK_EXPERIMENT_ID
            else _matrix_plan(experiment_id)
        )
        async with factory() as session, session.begin():
            await enqueue_plan(session, plan)
        executor = ExperimentRunExecutor(
            repository_root=ROOT,
            session_factory=factory,
            bindings=bindings,
            owner=f"phase-i-{experiment_id}",
        )
        completed = await executor.run_until_idle(experiment_id)
        assert len(completed) == (18 if experiment_id == MULTI_TASK_EXPERIMENT_ID else 9)

    suite = load_judge_suite(SUITE_ROOT)
    definition = load_judge_definition(SUITE_ROOT / "definition.yaml")
    spec = load_calibration_spec(SUITE_ROOT / "calibration.yaml").model_copy(
        update={"calibration_id": CALIBRATION_ID}
    )
    judge_plan = build_calibration_plan(
        spec, suite, {cell.id: definition for cell in spec.judge_cells}
    )
    judge_artifact_root = tmp_path_factory.mktemp("phase-i-judge-artifacts")
    async with factory() as session:
        await execute_calibration(
            session,
            plan=judge_plan,
            suite=suite,
            definitions={cell.id: definition for cell in judge_plan.judge_cells},
            artifact_root=judge_artifact_root,
        )

    async with factory() as session:
        runs = tuple(
            (
                await session.scalars(
                    select(ExperimentRunRecord)
                    .where(ExperimentRunRecord.experiment_id == EXPERIMENT_IDS[0])
                    .order_by(ExperimentRunRecord.slot_order)
                )
            ).all()
        )
    trace_run = next(run for run in runs if run.cell_id == "codex-low")
    no_trace_run = next(run for run in runs if run.cell_id == "direct")
    assert trace_run.artifact_manifest_path is not None
    native = Path(trace_run.artifact_manifest_path).parent / "native" / "codex.sanitized.jsonl"
    with native.open("a", encoding="utf-8") as stream:
        stream.write(PRIVATE_SENTINEL + "\n")

    app = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[workbench_session] = override_session
    app.dependency_overrides[workbench_artifact_roots] = lambda: (
        artifact_root.resolve(),
        judge_artifact_root.resolve(),
    )
    if evidence_path := os.environ.get("HARNESSLAB_GATE_I_EVIDENCE_PATH"):
        Path(evidence_path).write_text(
            json.dumps(
                {
                    "baseline_experiment_id": EXPERIMENT_IDS[0],
                    "candidate_experiment_id": EXPERIMENT_IDS[1],
                    "matrix_task_count": 2,
                    "matrix_cell_count": 3,
                    "matrix_run_count": 18,
                    "trace_coverage": "FULL_STREAM",
                    "missing_trace_status": "NOT_REPORTED",
                    "missing_cost_status": "NOT_REPORTED",
                    "regression_status": "TREATMENT_AWARE",
                    "judge_calibration_id": CALIBRATION_ID,
                    "core_readiness": "NOT_READY",
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
    evidence = PhaseIEvidence(
        factory=factory,
        app=app,
        baseline_id=EXPERIMENT_IDS[0],
        candidate_id=EXPERIMENT_IDS[1],
        multi_task_id=MULTI_TASK_EXPERIMENT_ID,
        calibration_id=CALIBRATION_ID,
        trace_run_id=trace_run.run_id,
        no_trace_run_id=no_trace_run.run_id,
    )
    try:
        yield evidence
    finally:
        async with factory() as cleanup, cleanup.begin():
            await cleanup.execute(
                delete(ExperimentRecord).where(ExperimentRecord.id.in_(EXPERIMENT_IDS))
            )
            await cleanup.execute(
                delete(JudgeCalibrationRecord).where(JudgeCalibrationRecord.id == CALIBRATION_ID)
            )
        await engine.dispose()
        shutil.rmtree(artifact_root, ignore_errors=True)
        shutil.rmtree(runtime_root, ignore_errors=True)


@pytest_asyncio.fixture
async def client(phase_i_evidence: PhaseIEvidence) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=phase_i_evidence.app), base_url="http://test"
    ) as http:
        yield http


@pytest.mark.integration
async def test_workbench_routes_are_read_only_and_have_no_execution_or_analyst_surface(
    phase_i_evidence: PhaseIEvidence,
) -> None:
    schema = phase_i_evidence.app.openapi()
    paths = {
        path: set(methods)
        for path, methods in schema["paths"].items()
        if path.startswith("/api/workbench")
    }
    assert len(paths) == 16
    assert paths["/api/workbench/regression/compare"] == {"post"}
    assert paths["/api/workbench/experiments/{experiment_id}/diagnosis/badcases"] == {"post"}
    assert paths["/api/workbench/experiments/{experiment_id}/diagnosis/projected-clusters"] == {
        "post"
    }
    assert paths["/api/workbench/experiments/{experiment_id}/model-comparison-analysis"] == {"get"}
    assert all(
        methods == {"get"}
        for path, methods in paths.items()
        if path
        not in {
            "/api/workbench/regression/compare",
            "/api/workbench/experiments/{experiment_id}/diagnosis/badcases",
            "/api/workbench/experiments/{experiment_id}/diagnosis/projected-clusters",
        }
    )
    serialized = json.dumps(
        {key: sorted(value) for key, value in paths.items()}, sort_keys=True
    ).lower()
    assert "execute" not in serialized
    assert "provider" not in serialized
    assert "calibrate" not in serialized
    assert "analyst" not in serialized


@pytest.mark.integration
async def test_experiment_list_detail_status_and_pagination_use_persisted_database(
    client: AsyncClient, phase_i_evidence: PhaseIEvidence
) -> None:
    listing = await client.get(
        "/api/workbench/experiments", params={"search": "phase-i-matrix", "limit": 3}
    )
    assert listing.status_code == 200
    assert listing.json()["total"] == 3
    assert {item["experiment_id"] for item in listing.json()["items"]} == set(EXPERIMENT_IDS)
    detail = await client.get(f"/api/workbench/experiments/{phase_i_evidence.baseline_id}")
    assert detail.status_code == 200
    assert detail.json()["planned_run_count"] == 9
    assert detail.json()["completed_capability_count"] == 9
    assert detail.json()["comparison_intent"] == "HARNESS_UPLIFT"
    assert detail.json()["evaluation_mode"] == "NOT_AVAILABLE"
    status = await client.get(f"/api/workbench/experiments/{phase_i_evidence.baseline_id}/status")
    assert status.json()["terminal"] is True
    assert status.json()["run_status_counts"] == {"completed": 6, "failed_subject": 3}
    assert (
        await client.get("/api/workbench/experiments", params={"limit": 101})
    ).status_code == 422


@pytest.mark.integration
async def test_model_comparison_analysis_route_rejects_other_intents_without_mutation(
    client: AsyncClient, phase_i_evidence: PhaseIEvidence
) -> None:
    response = await client.get(
        f"/api/workbench/experiments/{phase_i_evidence.baseline_id}/model-comparison-analysis"
    )
    assert response.status_code == 422
    assert response.json()["error"] == {
        "code": "ANALYSIS_NOT_APPLICABLE",
        "message": "experiment is not a MODEL_COMPARISON",
    }


@pytest.mark.integration
async def test_complete_matrix_snapshot_and_report_identity_are_browsable(
    client: AsyncClient, phase_i_evidence: PhaseIEvidence
) -> None:
    matrix = (
        await client.get(f"/api/workbench/experiments/{phase_i_evidence.baseline_id}/matrix")
    ).json()
    report = (
        await client.get(f"/api/workbench/experiments/{phase_i_evidence.baseline_id}/report")
    ).json()
    assert matrix["tasks"] == ["micro-python-clamp"]
    assert matrix["cells"] == ["codex-high", "codex-low", "direct"]
    assert len(matrix["points"]) == 3
    assert matrix["report_digest"] == report["report_digest"]
    assert matrix["infra_count"] == 0
    assert {point["tier"] for point in matrix["points"]} == {"INFORMAL"}
    assert any(point["comparability"] == "NOT_COMPARABLE" for point in matrix["points"])
    assert any(point["comparability"] == "PARTIALLY_COMPARABLE" for point in matrix["points"])
    assert all(
        point["metrics"]["pass_at_5"] == {"status": "NOT_REPORTED", "value": None}
        for point in matrix["points"]
    )


@pytest.mark.integration
async def test_multi_task_matrix_uses_task_scoped_verified_observations(
    client: AsyncClient, phase_i_evidence: PhaseIEvidence
) -> None:
    response = await client.get(
        f"/api/workbench/experiments/{phase_i_evidence.multi_task_id}/matrix"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tasks"] == ["micro-python-clamp", "micro-typescript-clamp"]
    assert body["cells"] == ["codex-high", "codex-low", "codex-unpaired"]
    assert len(body["points"]) == 6
    assert all(point["n"] == 3 for point in body["points"])
    assert all(point["metrics"]["success_rate"]["status"] == "REPORTED" for point in body["points"])
    assert all(
        point["metrics"]["infra_rate"] == {"status": "REPORTED", "value": 0.0}
        for point in body["points"]
    )
    assert all(point["metrics"]["pass_at_3"]["status"] == "REPORTED" for point in body["points"])
    assert all(
        point["metrics"]["pass_at_5"]["status"] == "NOT_REPORTED" for point in body["points"]
    )
    task_values = {
        (point["task_id"], point["cell_id"]): point["metrics"]["success_rate"]["value"]
        for point in body["points"]
    }
    assert set(task_values.values()) == {0.0, 1.0}
    assert 0.5 not in task_values.values()
    assert all(
        point["comparability"] == "NOT_REPORTED" and point["reason_codes"] == []
        for point in body["points"]
        if point["cell_id"] == "codex-unpaired"
    )


@pytest.mark.integration
async def test_matrix_comparability_is_task_scoped_and_never_invented(
    client: AsyncClient, phase_i_evidence: PhaseIEvidence
) -> None:
    async with phase_i_evidence.factory() as session:
        run = await session.scalar(
            select(ExperimentRunRecord).where(
                ExperimentRunRecord.experiment_id == phase_i_evidence.multi_task_id,
                ExperimentRunRecord.cell_id == "codex-high",
                ExperimentRunRecord.task_id == "micro-typescript-clamp",
                ExperimentRunRecord.repeat_index == 0,
            )
        )
        assert run is not None and run.artifact_manifest_path is not None
        path = Path(run.artifact_manifest_path)
        original_digest = run.evidence_digest
    original = path.read_bytes()
    payload = json.loads(original)
    payload["trace_coverage"] = "FINAL_OUTPUT_ONLY"
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    async with phase_i_evidence.factory() as session, session.begin():
        run = await session.scalar(
            select(ExperimentRunRecord).where(
                ExperimentRunRecord.experiment_id == phase_i_evidence.multi_task_id,
                ExperimentRunRecord.cell_id == "codex-high",
                ExperimentRunRecord.task_id == "micro-typescript-clamp",
                ExperimentRunRecord.repeat_index == 0,
            )
        )
        assert run is not None
        run.evidence_digest = sha256_file(path)
    try:
        response = await client.get(
            f"/api/workbench/experiments/{phase_i_evidence.multi_task_id}/matrix"
        )
        assert response.status_code == 200, response.text
        points = {
            (point["task_id"], point["cell_id"]): point for point in response.json()["points"]
        }
        affected = points[("micro-typescript-clamp", "codex-high")]
        unrelated = points[("micro-python-clamp", "codex-high")]
        assert affected["comparability"] == "PARTIALLY_COMPARABLE"
        assert "TRACE_COVERAGE_LIMITED" in affected["reason_codes"]
        assert "TRACE_COVERAGE_LIMITED" not in unrelated["reason_codes"]
        assert unrelated["comparability"] != "NOT_REPORTED"
    finally:
        path.write_bytes(original)
        async with phase_i_evidence.factory() as session, session.begin():
            run = await session.scalar(
                select(ExperimentRunRecord).where(
                    ExperimentRunRecord.experiment_id == phase_i_evidence.multi_task_id,
                    ExperimentRunRecord.cell_id == "codex-high",
                    ExperimentRunRecord.task_id == "micro-typescript-clamp",
                    ExperimentRunRecord.repeat_index == 0,
                )
            )
            assert run is not None
            run.evidence_digest = original_digest


@pytest.mark.integration
async def test_run_filter_detail_identity_and_missing_cost_are_safe(
    client: AsyncClient, phase_i_evidence: PhaseIEvidence
) -> None:
    response = await client.get(
        f"/api/workbench/experiments/{phase_i_evidence.baseline_id}/runs",
        params={"cell": "codex-low", "lane": "H", "limit": 10},
    )
    assert response.status_code == 200
    assert response.json()["total"] == 3
    assert all(item["cell_id"] == "codex-low" for item in response.json()["items"])
    detail_response = await client.get(f"/api/workbench/runs/{phase_i_evidence.trace_run_id}")
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()
    assert detail["run_id"] == phase_i_evidence.trace_run_id
    assert detail["artifact_name"] == "manifest.json"
    assert detail["explicit_cost"] == {"status": "NOT_REPORTED", "value": None}
    assert "credential_reference" not in json.dumps(detail)
    assert "/home/" not in json.dumps(detail)


@pytest.mark.integration
async def test_workbench_manifest_reads_are_confined_to_server_artifact_roots(
    client: AsyncClient, phase_i_evidence: PhaseIEvidence, tmp_path: Path
) -> None:
    async with phase_i_evidence.factory() as session:
        record = await session.get(ExperimentRunRecord, phase_i_evidence.trace_run_id)
        assert record is not None and record.artifact_manifest_path is not None
        original_path = record.artifact_manifest_path
    original = Path(original_path)
    outside = tmp_path / "matching-run-manifest.json"
    outside.write_bytes(original.read_bytes())

    async with phase_i_evidence.factory() as session, session.begin():
        record = await session.get(ExperimentRunRecord, phase_i_evidence.trace_run_id)
        assert record is not None
        record.artifact_manifest_path = str(outside)
    rejected = await client.get(f"/api/workbench/runs/{phase_i_evidence.trace_run_id}")
    assert rejected.status_code == 409
    assert rejected.json()["error"] == {
        "code": "ARTIFACT_INTEGRITY_ERROR",
        "message": "artifact is outside trusted storage",
    }

    trusted_link = original.parents[1] / "symlink-escape-manifest.json"
    trusted_link.symlink_to(outside)
    try:
        async with phase_i_evidence.factory() as session, session.begin():
            record = await session.get(ExperimentRunRecord, phase_i_evidence.trace_run_id)
            assert record is not None
            record.artifact_manifest_path = str(trusted_link)
        symlink_rejected = await client.get(f"/api/workbench/runs/{phase_i_evidence.trace_run_id}")
        assert symlink_rejected.status_code == 409
        assert symlink_rejected.json()["error"]["code"] == "ARTIFACT_INTEGRITY_ERROR"
    finally:
        trusted_link.unlink()
        async with phase_i_evidence.factory() as session, session.begin():
            record = await session.get(ExperimentRunRecord, phase_i_evidence.trace_run_id)
            assert record is not None
            record.artifact_manifest_path = original_path

    legitimate = await client.get(f"/api/workbench/runs/{phase_i_evidence.trace_run_id}")
    assert legitimate.status_code == 200
    assert legitimate.json()["artifact_name"] == "manifest.json"


@pytest.mark.integration
async def test_trace_uses_verified_normalized_evidence_and_never_native_reasoning(
    client: AsyncClient, phase_i_evidence: PhaseIEvidence
) -> None:
    trace_response = await client.get(f"/api/workbench/runs/{phase_i_evidence.trace_run_id}/trace")
    assert trace_response.status_code == 200, trace_response.text
    trace = trace_response.json()
    assert trace["status"] == "REPORTED"
    assert trace["coverage"] == "FULL_STREAM"
    assert any(item["type"] == "REASONING_PRESENT" for item in trace["events"])
    assert PRIVATE_SENTINEL not in json.dumps(trace)
    missing = (
        await client.get(f"/api/workbench/runs/{phase_i_evidence.no_trace_run_id}/trace")
    ).json()
    assert missing == {
        "run_id": phase_i_evidence.no_trace_run_id,
        "status": "NOT_REPORTED",
        "coverage": None,
        "trace_digest": None,
        "events": [],
    }


@pytest.mark.integration
async def test_trace_rejects_client_paths_and_symlink_escape(
    client: AsyncClient, phase_i_evidence: PhaseIEvidence, tmp_path: Path
) -> None:
    rejected = await client.get(
        f"/api/workbench/runs/{phase_i_evidence.trace_run_id}/trace",
        params={"path": "../../etc/passwd"},
    )
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "INVALID_ARTIFACT_REFERENCE"
    async with phase_i_evidence.factory() as session:
        record = await session.get(ExperimentRunRecord, phase_i_evidence.trace_run_id)
        assert record is not None and record.artifact_manifest_path is not None
        trace_path = Path(record.artifact_manifest_path).parent / "trace" / "normalized.json"
    original = trace_path.read_bytes()
    outside = tmp_path / "outside.json"
    outside.write_bytes(original)
    trace_path.unlink()
    trace_path.symlink_to(outside)
    try:
        escaped = await client.get(f"/api/workbench/runs/{phase_i_evidence.trace_run_id}/trace")
        assert escaped.status_code == 409
        assert escaped.json()["error"]["code"] == "ARTIFACT_INTEGRITY_ERROR"
    finally:
        trace_path.unlink()
        trace_path.write_bytes(original)


@pytest.mark.integration
async def test_projected_diagnosis_api_is_explicit_versioned_and_allowlisted(
    client: AsyncClient, phase_i_evidence: PhaseIEvidence
) -> None:
    response = await client.post(
        f"/api/workbench/experiments/{phase_i_evidence.multi_task_id}/diagnosis/projected-clusters",
        json={
            "attempt_selection": "PRIMARY_ONLY",
            "projection": {
                "projection_id": "workbench-broad-failures",
                "projection_version": "1",
                "dimensions": ["FAILURE_CLASS", "FAILURE_SCOPE", "TRACE_PATTERN"],
                "missing_value_policy": "SEPARATE_UNKNOWN",
                "namespace": "workbench",
            },
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["attempt_selection"] == "PRIMARY_ONLY"
    assert body["projection"]["projection_version"] == "1"
    assert body["cohort"]["diagnostic_only"] is True
    assert body["cohort"]["comparability_claim"] is False
    assert body["attempt_reads"]
    assert all(item["read_path"] == "LEGACY_COMPATIBILITY" for item in body["attempt_reads"])
    serialized = json.dumps(body)
    assert "/home/" not in serialized
    assert "credential" not in serialized.lower()
    assert PRIVATE_SENTINEL not in serialized

    invalid = await client.post(
        f"/api/workbench/experiments/{phase_i_evidence.multi_task_id}/diagnosis/projected-clusters",
        json={
            "attempt_selection": "PRIMARY_ONLY",
            "projection": {
                "projection_id": "invalid",
                "projection_version": "1",
                "dimensions": ["ARBITRARY_FIELD"],
                "namespace": "workbench",
            },
        },
    )
    assert invalid.status_code == 422


@pytest.mark.integration
async def test_judgelab_list_and_detail_use_digest_verified_phase_h_report(
    client: AsyncClient, phase_i_evidence: PhaseIEvidence
) -> None:
    listing_response = await client.get("/api/workbench/judgelab/calibrations")
    assert listing_response.status_code == 200, listing_response.text
    listing = listing_response.json()
    item = next(item for item in listing["items"] if item["calibration_id"] == CALIBRATION_ID)
    assert set(item["qualifications"]) == {"QUALIFIED_FOR_SUITE", "NOT_QUALIFIED"}
    detail = (
        await client.get(f"/api/workbench/judgelab/calibrations/{phase_i_evidence.calibration_id}")
    ).json()
    assert detail["real_judge_smoke"] == "NOT_RUN"
    assert all(cell["qualification_scope"] == "core-calibration@1.0.0" for cell in detail["cells"])
    assert all(cell["l0_overrides"] == 0 for cell in detail["cells"])
    assert {cell["qualification"] for cell in detail["cells"]} == {
        "QUALIFIED_FOR_SUITE",
        "NOT_QUALIFIED",
    }


@pytest.mark.integration
async def test_regression_compare_accepts_declared_treatments_and_blocks_hard_controls(
    client: AsyncClient, phase_i_evidence: PhaseIEvidence
) -> None:
    async with phase_i_evidence.factory() as session:
        before_runs = tuple(
            (
                await session.scalars(
                    select(ExperimentRunRecord).where(
                        ExperimentRunRecord.experiment_id.in_(REGRESSION_EXPERIMENT_IDS)
                    )
                )
            ).all()
        )
    before_artifacts = {
        run.run_id: (
            run.artifact_manifest_path,
            Path(run.artifact_manifest_path).stat().st_mtime_ns
            if run.artifact_manifest_path
            else None,
        )
        for run in before_runs
    }

    model_response = await client.post(
        "/api/workbench/regression/compare",
        json={
            "baseline_experiment_id": phase_i_evidence.baseline_id,
            "candidate_experiment_id": phase_i_evidence.candidate_id,
            "intent": "MODEL_COMPARISON",
            "cell_mapping": {"codex-low": "codex-low"},
        },
    )
    assert model_response.status_code == 200, model_response.text
    model = model_response.json()
    assert model["intent"] == "MODEL_COMPARISON"
    assert model["comparisons"][0]["comparability"] == "NOT_COMPARABLE", json.dumps(
        model["comparisons"][0], sort_keys=True
    )
    assert "RESOURCE_ENVELOPE_MISSING" in model["comparisons"][0]["reason_codes"]
    assert "INTENDED_TREATMENT_DIFFERENCE" in model["comparisons"][0]["reason_codes"]
    assert model["comparisons"][0]["paired_observations"] == 3

    harness_response = await client.post(
        "/api/workbench/regression/compare",
        json={
            "baseline_experiment_id": phase_i_evidence.baseline_id,
            "candidate_experiment_id": phase_i_evidence.candidate_id,
            "intent": "HARNESS_UPLIFT",
            "cell_mapping": {"codex-low": "codex-high"},
        },
    )
    assert harness_response.status_code == 200, harness_response.text
    harness = harness_response.json()["comparisons"][0]
    assert harness["comparability"] == "NOT_COMPARABLE"
    assert "RESOURCE_ENVELOPE_MISSING" in harness["reason_codes"]
    # SUPERSEDED_LEGACY_EXPECTATION: effort drift is not an implicit uplift treatment.
    assert "HARD_CONTROL_MISMATCH" in harness["reason_codes"]
    assert harness["paired_observations"] == 3

    native_response = await client.post(
        "/api/workbench/regression/compare",
        json={
            "baseline_experiment_id": phase_i_evidence.baseline_id,
            "candidate_experiment_id": phase_i_evidence.candidate_id,
            "intent": "NATIVE_HARNESS_SYSTEM_COMPARISON",
            "cell_mapping": {"codex-low": "codex-high"},
        },
    )
    assert native_response.status_code == 200, native_response.text
    native = native_response.json()["comparisons"][0]
    assert native["comparability"] in {"COMPARABLE", "PARTIALLY_COMPARABLE"}
    assert "RESOURCE_ENVELOPE_MISSING" not in native["reason_codes"]

    hard_control_response = await client.post(
        "/api/workbench/regression/compare",
        json={
            "baseline_experiment_id": phase_i_evidence.baseline_id,
            "candidate_experiment_id": phase_i_evidence.candidate_id,
            "intent": "MODEL_COMPARISON",
            "cell_mapping": {"direct": "codex-low"},
        },
    )
    assert hard_control_response.status_code == 200
    hard_control = hard_control_response.json()["comparisons"][0]
    assert hard_control["comparability"] == "NOT_COMPARABLE"
    assert "HARD_CONTROL_MISMATCH" in hard_control["reason_codes"]
    assert "causal attribution" in hard_control_response.json()["limitation"]

    oversized = await client.post(
        "/api/workbench/regression/compare",
        json={
            "baseline_experiment_id": phase_i_evidence.baseline_id,
            "candidate_experiment_id": phase_i_evidence.candidate_id,
            "intent": "GENERAL",
            "cell_mapping": {f"cell-{index}": "direct" for index in range(101)},
        },
    )
    assert oversized.status_code == 422
    arbitrary_intent = await client.post(
        "/api/workbench/regression/compare",
        json={
            "baseline_experiment_id": phase_i_evidence.baseline_id,
            "candidate_experiment_id": phase_i_evidence.candidate_id,
            "intent": "CUSTOM_TREATMENT_FIELDS",
            "cell_mapping": {"codex-low": "codex-low"},
        },
    )
    assert arbitrary_intent.status_code == 422

    async with phase_i_evidence.factory() as session:
        after_count = int(
            await session.scalar(
                select(func.count())
                .select_from(ExperimentRunRecord)
                .where(ExperimentRunRecord.experiment_id.in_(REGRESSION_EXPERIMENT_IDS))
            )
            or 0
        )
    assert after_count == len(before_runs)
    assert before_artifacts == {
        run.run_id: (
            run.artifact_manifest_path,
            Path(run.artifact_manifest_path).stat().st_mtime_ns
            if run.artifact_manifest_path
            else None,
        )
        for run in before_runs
    }


@pytest.mark.integration
async def test_core_readiness_is_evidence_driven_and_stays_not_ready(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/workbench/core-readiness")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "NOT_READY"
    assert body["task_corpus_size"] == 18
    task_check = next(check for check in body["checks"] if check["key"] == "TASK_CORPUS")
    assert task_check["status"] == "READY"
    assert "15-25" in task_check["evidence"]
    for key in (
        "REAL_MATRIX_EVIDENCE",
        "JUDGE_EVIDENCE",
        "MODEL_ONLY_PROFILES",
        "PAIRED_LANE",
        "ABLATION",
    ):
        assert next(check for check in body["checks"] if check["key"] == key)["status"] == "READY"
    assert "RELEASE_EVIDENCE" in body["blockers"]
    assert "REMOTE_CI" in body["blockers"]
    assert "CORE_TAG" in body["blockers"]
    assert "PHASE_J" not in body["blockers"]


@pytest.mark.integration
async def test_public_error_shape_and_unknown_resource_do_not_leak_internals(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/workbench/experiments/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "NOT_FOUND", "message": "experiment does not exist"}
    }
    assert "/home/" not in response.text
    assert "Traceback" not in response.text


@pytest.mark.integration
async def test_judge_report_digest_mutation_fails_closed(
    client: AsyncClient, phase_i_evidence: PhaseIEvidence
) -> None:
    async with phase_i_evidence.factory() as session:
        record = await session.get(JudgeCalibrationRecord, phase_i_evidence.calibration_id)
        assert record is not None and record.report_json_path is not None
        report_path = Path(record.report_json_path)
    original = report_path.read_bytes()
    payload = json.loads(original)
    payload["limitations"] = [*payload["limitations"], "mutated"]
    report_path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        listing = await client.get("/api/workbench/judgelab/calibrations")
        assert listing.status_code == 200
        item = next(
            item
            for item in listing.json()["items"]
            if item["calibration_id"] == phase_i_evidence.calibration_id
        )
        assert item["report_evidence_status"] == "INTEGRITY_ERROR"
        assert item["qualifications"] == []
        response = await client.get(
            f"/api/workbench/judgelab/calibrations/{phase_i_evidence.calibration_id}"
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "ARTIFACT_INTEGRITY_ERROR"
        readiness = (await client.get("/api/workbench/core-readiness")).json()
        judge_check = next(
            check for check in readiness["checks"] if check["key"] == "JUDGE_CALIBRATION"
        )
        assert judge_check["status"] == "NOT_VERIFIED"
        assert judge_check["evidence"].startswith("0 integrity-validated")
    finally:
        report_path.write_bytes(original)


@pytest.mark.integration
async def test_frontend_dtos_contain_no_absolute_path_credential_or_private_sentinel(
    client: AsyncClient, phase_i_evidence: PhaseIEvidence
) -> None:
    responses = [
        await client.get(f"/api/workbench/experiments/{phase_i_evidence.baseline_id}"),
        await client.get(f"/api/workbench/experiments/{phase_i_evidence.baseline_id}/matrix"),
        await client.get(f"/api/workbench/runs/{phase_i_evidence.trace_run_id}"),
        await client.get(f"/api/workbench/runs/{phase_i_evidence.trace_run_id}/trace"),
        await client.get(f"/api/workbench/judgelab/calibrations/{phase_i_evidence.calibration_id}"),
    ]
    serialized = "\n".join(response.text for response in responses)
    assert all(response.status_code == 200 for response in responses)
    assert "/home/" not in serialized
    assert "credential_reference" not in serialized
    assert "DATABASE_URL" not in serialized
    assert PRIVATE_SENTINEL not in serialized
