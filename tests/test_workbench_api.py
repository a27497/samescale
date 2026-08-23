from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from harnesslab.api.app import create_app
from harnesslab.api.workbench_dependencies import workbench_session
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
from harnesslab.harness_lane.fake import FakeCodexBackend
from harnesslab.harness_lane.profile import canonical_codex_profile
from harnesslab.harness_lane.runner import CodexHarnessRunner
from harnesslab.judgelab.calibration import execute_calibration
from harnesslab.judgelab.plan import build_calibration_plan, load_calibration_spec
from harnesslab.judgelab.suite import load_judge_definition, load_judge_suite
from harnesslab.model_lane.fake import FakeDirectProvider
from harnesslab.model_lane.runner import DirectModelRunner
from harnesslab.tasks.package import TaskPackage
from tests.phase_g_helpers import PYTHON_TASK_PATH, ROOT
from tests.test_experiment_e2e import PATCH, _cell, _image

SUITE_ROOT = ROOT / "judge_suites/core-calibration/1.0.0"
EXPERIMENT_IDS = ("phase-i-matrix-baseline", "phase-i-matrix-candidate")
CALIBRATION_ID = "phase-i-judge-keyless"
PRIVATE_SENTINEL = "PRIVATE_REASONING_SENTINEL"


@dataclass(frozen=True)
class PhaseIEvidence:
    factory: async_sessionmaker[AsyncSession]
    app: Any
    baseline_id: str
    candidate_id: str
    calibration_id: str
    trace_run_id: str
    no_trace_run_id: str


def _matrix_plan(experiment_id: str) -> tuple[ExperimentPlan, dict[str, ExperimentLaneBinding]]:
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
    package = TaskPackage.load(ROOT / PYTHON_TASK_PATH)
    budget_identity = canonical_digest(package.definition.budget.model_dump(mode="json"))
    cells = (
        _cell(
            "direct",
            EvaluationLane.MODEL,
            provider_route="fake-provider|responses|https://fake.invalid/v1/responses",
            profile_identity=resolved_comparison_profile_identity(direct_profile),
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
            FakeDirectProvider(PATCH, observed_model="fake-shared-model"),
        ),
        "codex-low": CodexHarnessBinding(
            CodexHarnessRunner(
                artifact_root=ROOT / ".phase-i-test-artifacts",
                runtime_root=ROOT / ".phase-i-test-runtime" / experiment_id / "codex-low",
            ),
            codex_low,
            FakeCodexBackend(),
        ),
        "codex-high": CodexHarnessBinding(
            CodexHarnessRunner(
                artifact_root=ROOT / ".phase-i-test-artifacts",
                runtime_root=ROOT / ".phase-i-test-runtime" / experiment_id / "codex-high",
            ),
            codex_high,
            FakeCodexBackend(),
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
        plan, bindings = _matrix_plan(experiment_id)
        async with factory() as session, session.begin():
            await enqueue_plan(session, plan)
        executor = ExperimentRunExecutor(
            repository_root=ROOT,
            session_factory=factory,
            bindings=bindings,
            owner=f"phase-i-{experiment_id}",
        )
        completed = await executor.run_until_idle(experiment_id)
        assert len(completed) == 9

    suite = load_judge_suite(SUITE_ROOT)
    definition = load_judge_definition(SUITE_ROOT / "definition.yaml")
    spec = load_calibration_spec(SUITE_ROOT / "calibration.yaml").model_copy(
        update={"calibration_id": CALIBRATION_ID}
    )
    judge_plan = build_calibration_plan(
        spec, suite, {cell.id: definition for cell in spec.judge_cells}
    )
    async with factory() as session:
        await execute_calibration(
            session,
            plan=judge_plan,
            suite=suite,
            definitions={cell.id: definition for cell in judge_plan.judge_cells},
            artifact_root=tmp_path_factory.mktemp("phase-i-judge-artifacts"),
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
    if evidence_path := os.environ.get("HARNESSLAB_GATE_I_EVIDENCE_PATH"):
        Path(evidence_path).write_text(
            json.dumps(
                {
                    "baseline_experiment_id": EXPERIMENT_IDS[0],
                    "candidate_experiment_id": EXPERIMENT_IDS[1],
                    "matrix_task_count": 1,
                    "matrix_cell_count": 3,
                    "matrix_run_count": 9,
                    "trace_coverage": "FULL_STREAM",
                    "missing_trace_status": "NOT_REPORTED",
                    "missing_cost_status": "NOT_REPORTED",
                    "regression_status": "NOT_COMPARABLE",
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
        import shutil

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
    assert len(paths) == 12
    assert paths["/api/workbench/regression/compare"] == {"post"}
    assert all(
        methods == {"get"}
        for path, methods in paths.items()
        if path != "/api/workbench/regression/compare"
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
        "/api/workbench/experiments", params={"search": "phase-i-matrix", "limit": 2}
    )
    assert listing.status_code == 200
    assert listing.json()["total"] == 2
    assert {item["experiment_id"] for item in listing.json()["items"]} == set(EXPERIMENT_IDS)
    detail = await client.get(f"/api/workbench/experiments/{phase_i_evidence.baseline_id}")
    assert detail.status_code == 200
    assert detail.json()["planned_run_count"] == 9
    assert detail.json()["completed_capability_count"] == 9
    status = await client.get(f"/api/workbench/experiments/{phase_i_evidence.baseline_id}/status")
    assert status.json()["terminal"] is True
    assert status.json()["run_status_counts"] == {"completed": 6, "failed_subject": 3}
    assert (
        await client.get("/api/workbench/experiments", params={"limit": 101})
    ).status_code == 422


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
async def test_regression_compare_uses_persisted_reports_and_blocks_control_mismatch(
    client: AsyncClient, phase_i_evidence: PhaseIEvidence
) -> None:
    response = await client.post(
        "/api/workbench/regression/compare",
        json={
            "baseline_experiment_id": phase_i_evidence.baseline_id,
            "candidate_experiment_id": phase_i_evidence.candidate_id,
            "cell_mapping": {"direct": "codex-low"},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["comparisons"][0]["comparability"] == "NOT_COMPARABLE"
    assert body["comparisons"][0]["reason_codes"] == ["HARD_CONTROL_MISMATCH"]
    assert "causal attribution" in body["limitation"]
    assert body["baseline_report_digest"].startswith("sha256:")
    assert body["candidate_report_digest"].startswith("sha256:")
    oversized = await client.post(
        "/api/workbench/regression/compare",
        json={
            "baseline_experiment_id": phase_i_evidence.baseline_id,
            "candidate_experiment_id": phase_i_evidence.candidate_id,
            "cell_mapping": {f"cell-{index}": "direct" for index in range(101)},
        },
    )
    assert oversized.status_code == 422

    async with phase_i_evidence.factory() as session, session.begin():
        record = await session.get(ExperimentRecord, phase_i_evidence.candidate_id)
        assert record is not None
        original_plan_json = record.plan_json
        original_plan_digest = record.plan_digest
        candidate_plan = ExperimentPlan.model_validate(record.plan_json)
        changed_task = candidate_plan.tasks[0].model_copy(
            update={"verifier_identity": "sha256:" + "0" * 64}
        )
        changed_plan = candidate_plan.model_copy(update={"tasks": (changed_task,)})
        record.plan_json = changed_plan.model_dump(mode="json")
        record.plan_digest = changed_plan.digest

    try:
        task_mismatch = await client.post(
            "/api/workbench/regression/compare",
            json={
                "baseline_experiment_id": phase_i_evidence.baseline_id,
                "candidate_experiment_id": phase_i_evidence.candidate_id,
                "cell_mapping": {"direct": "direct"},
            },
        )
        assert task_mismatch.status_code == 200, task_mismatch.text
        comparison = task_mismatch.json()["comparisons"][0]
        assert comparison["comparability"] == "NOT_COMPARABLE"
        assert comparison["reason_codes"] == ["TASK_CONTROL_MISMATCH"]
        assert task_mismatch.json()["common_tasks"] == []
    finally:
        async with phase_i_evidence.factory() as session, session.begin():
            record = await session.get(ExperimentRecord, phase_i_evidence.candidate_id)
            assert record is not None
            record.plan_json = original_plan_json
            record.plan_digest = original_plan_digest


@pytest.mark.integration
async def test_core_readiness_is_evidence_driven_and_stays_not_ready(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/workbench/core-readiness")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "NOT_READY"
    assert body["task_corpus_size"] >= 1
    assert "REAL_MATRIX_EVIDENCE" in body["blockers"]
    assert "REAL_JUDGE_EVIDENCE" in body["blockers"]
    assert "PHASE_J" in body["blockers"]


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
        response = await client.get(
            f"/api/workbench/judgelab/calibrations/{phase_i_evidence.calibration_id}"
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "ARTIFACT_INTEGRITY_ERROR"
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
