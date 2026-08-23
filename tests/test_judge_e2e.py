from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url

from harnesslab.core.config import Settings, get_settings
from harnesslab.db.models.experiment import (
    ExperimentCellRecord,
    ExperimentRecord,
    ExperimentRunRecord,
)
from harnesslab.db.models.judgelab import JudgeCalibrationRecord, JudgeEvaluationRecord
from harnesslab.db.session import create_engine, create_session_factory
from harnesslab.judgelab.calibration import execute_calibration
from harnesslab.judgelab.fake import FakeJudgeProvider
from harnesslab.judgelab.models import QualificationStatus
from harnesslab.judgelab.persistence import enqueue_calibration, evaluation_records
from harnesslab.judgelab.plan import build_calibration_plan, load_calibration_spec
from harnesslab.judgelab.report import build_judge_report
from harnesslab.judgelab.runner import JudgeArtifactError, load_and_verify_evidence
from harnesslab.judgelab.suite import load_judge_definition, load_judge_suite

ROOT = Path(__file__).resolve().parents[1]
SUITE_ROOT = ROOT / "judge_suites/core-calibration/1.0.0"


@pytest.mark.integration
async def test_persisted_good_vs_biased_judge_e2e_and_phase_g_read_only(
    database_url: str, tmp_path: Path
) -> None:
    settings = Settings.without_dotenv(database_url=database_url)
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    suite = load_judge_suite(SUITE_ROOT)
    definition = load_judge_definition(SUITE_ROOT / "definition.yaml")
    spec = load_calibration_spec(SUITE_ROOT / "calibration.yaml").model_copy(
        update={"calibration_id": "phase-h-gate-e2e"}
    )
    plan = build_calibration_plan(spec, suite, {cell.id: definition for cell in spec.judge_cells})
    definitions = {cell.id: definition for cell in plan.judge_cells}
    phase_g_id = "phase-h-read-only-regression"
    try:
        async with factory() as session, session.begin():
            await session.execute(
                delete(JudgeCalibrationRecord).where(
                    JudgeCalibrationRecord.id == plan.calibration_id
                )
            )
            await session.execute(delete(ExperimentRecord).where(ExperimentRecord.id == phase_g_id))
            session.add(
                ExperimentRecord(
                    id=phase_g_id,
                    schema_version=1,
                    name="Phase G immutable input regression",
                    plan_digest="sha256:" + "a" * 64,
                    plan_json={"phase": "G", "immutable": True},
                    status="completed",
                )
            )
            await session.flush()
            session.add(
                ExperimentCellRecord(
                    experiment_id=phase_g_id,
                    cell_id="phase-g-cell",
                    lane="M",
                    configuration_identity="sha256:" + "b" * 64,
                    configuration_json={"immutable": True},
                    repeat_target=1,
                )
            )
            await session.flush()
            session.add(
                ExperimentRunRecord(
                    run_id="phase-h-read-only-run",
                    experiment_id=phase_g_id,
                    cell_id="phase-g-cell",
                    slot_id="sha256:" + "c" * 64,
                    slot_order=0,
                    slot_json={"immutable": True},
                    lane="M",
                    task_id="phase-g-task",
                    task_version="1.0.0",
                    task_digest="sha256:" + "d" * 64,
                    repeat_index=0,
                    paired_slot_identity="sha256:" + "e" * 64,
                    status="completed",
                    attempt=1,
                    normalized_outcome="capability_fail",
                    source_outcome="VERIFIED_FAIL",
                )
            )
        async with factory() as session:
            before = await session.get(ExperimentRunRecord, "phase-h-read-only-run")
            assert before is not None
            frozen = (
                before.status,
                before.normalized_outcome,
                before.source_outcome,
                before.artifact_manifest_path,
                before.evidence_digest,
            )
            report = await execute_calibration(
                session,
                plan=plan,
                suite=suite,
                definitions=definitions,
                artifact_root=tmp_path / "artifacts",
            )
        cells = {cell.judge_cell_id: cell for cell in report.cells}
        good = cells["good-judge"]
        biased = cells["biased-unstable-judge"]
        assert good.qualification_status is QualificationStatus.QUALIFIED_FOR_SUITE
        assert biased.qualification_status is QualificationStatus.NOT_QUALIFIED
        assert good.label_metrics["accuracy"] == 0.8
        assert good.label_metrics["macro_f1"] == 1.0
        assert good.score_metrics["mae"] == 0.0
        assert good.score_metrics["spearman_rho"] == 1.0
        assert good.pairwise_metrics["gold_accuracy"] == 1.0
        assert good.pairwise_metrics["position_consistency_rate"] == 1.0
        assert good.pairwise_metrics["verbosity_bias_rate"] == 0.0
        assert good.label_metrics["repeat_consistency"] == 1.0
        assert good.score_metrics["mean_within_case_standard_deviation"] == 0.0
        assert good.pairwise_metrics["repeat_consistency"] == 1.0
        assert biased.pairwise_metrics["position_consistency_rate"] < 1.0
        assert biased.pairwise_metrics["verbosity_bias_rate"] == 1.0
        assert biased.pairwise_metrics["repeat_consistency"] < 1.0
        assert good.l0_override_count == biased.l0_override_count == 0
        assert biased.l0_judge_disagreement_count > good.l0_judge_disagreement_count
        biased_l0 = [
            item
            for item in biased.authority_resolutions
            if item.authority_level == "L0" and item.judge_disagreement
        ]
        assert biased_l0
        assert all(item.authoritative_value in {"PASS", "FAIL"} for item in biased_l0)
        assert all(item.l0_override_count == 0 for item in biased_l0)
        assert good.pairwise_metrics["logical_pair_count"] == 18
        assert good.pairwise_metrics["order_swapped_requests"] == 18

        async with factory() as session:
            after = await session.get(ExperimentRunRecord, "phase-h-read-only-run")
            assert after is not None
            assert (
                after.status,
                after.normalized_outcome,
                after.source_outcome,
                after.artifact_manifest_path,
                after.evidence_digest,
            ) == frozen
            second_enqueue = await enqueue_calibration(session, plan)
            assert not second_enqueue.created
            assert second_enqueue.slot_count == 126
            records = await evaluation_records(session, plan.calibration_id)
            rebuilt_a = build_judge_report(
                plan=plan,
                suite=suite,
                definitions={
                    cell_id: value.model_dump(mode="json") for cell_id, value in definitions.items()
                },
                records=records,
            )
            rebuilt_b = build_judge_report(
                plan=plan,
                suite=suite,
                definitions={
                    cell_id: value.model_dump(mode="json") for cell_id, value in definitions.items()
                },
                records=records,
            )
            assert (
                rebuilt_a.canonical_json() == rebuilt_b.canonical_json() == report.canonical_json()
            )
            assert rebuilt_a.markdown() == rebuilt_b.markdown() == report.markdown()
            assert rebuilt_a.report_digest == report.report_digest
            one_failure_plan = plan.model_copy(
                update={
                    "qualification_policy": plan.qualification_policy.model_copy(
                        update={"minimum_label_accuracy": 0.81}
                    )
                }
            )
            one_failure = build_judge_report(
                plan=one_failure_plan,
                suite=suite,
                definitions={
                    cell_id: value.model_dump(mode="json") for cell_id, value in definitions.items()
                },
                records=records,
            )
            one_failure_good = next(
                cell for cell in one_failure.cells if cell.judge_cell_id == "good-judge"
            )
            assert one_failure_good.qualification_status is QualificationStatus.NOT_QUALIFIED
            assert len(one_failure_good.qualification_reasons) == 1
            private_scan = json.dumps(
                [
                    {
                        "outcome": row.outcome,
                        "path": row.artifact_manifest_path,
                        "requested": row.requested_judge_model,
                        "observed": row.observed_judge_model,
                    }
                    for row in records
                ]
            )
            assert "PRIVATE_REASONING_SENTINEL" not in private_scan
            assert "GOLD_ONLY_SENTINEL" not in private_scan

        evidence_root = ROOT / "harnesslab-artifacts"
        evidence_root.mkdir(parents=True, exist_ok=True)
        (evidence_root / "gate-h-evidence.json").write_text(
            json.dumps(
                {
                    "suite_digest": suite.suite_digest,
                    "definition_digest": definition.definition_digest,
                    "plan_digest": plan.plan_digest,
                    "report_digest": report.report_digest,
                    "evaluation_slot_count": 126,
                    "good_status": good.qualification_status.value,
                    "biased_status": biased.qualification_status.value,
                    "good_metrics": {
                        "label_accuracy": good.label_metrics["accuracy"],
                        "macro_f1": good.label_metrics["macro_f1"],
                        "score_mae": good.score_metrics["mae"],
                        "spearman_rho": good.score_metrics["spearman_rho"],
                        "pairwise_accuracy": good.pairwise_metrics["gold_accuracy"],
                        "position_consistency": good.pairwise_metrics["position_consistency_rate"],
                        "verbosity_bias_rate": good.pairwise_metrics["verbosity_bias_rate"],
                        "repeat_consistency": good.pairwise_metrics["repeat_consistency"],
                        "l0_disagreements": good.l0_judge_disagreement_count,
                        "l0_overrides": good.l0_override_count,
                    },
                    "biased_metrics": {
                        "label_accuracy": biased.label_metrics["accuracy"],
                        "score_mae": biased.score_metrics["mae"],
                        "pairwise_accuracy": biased.pairwise_metrics["gold_accuracy"],
                        "position_consistency": biased.pairwise_metrics[
                            "position_consistency_rate"
                        ],
                        "verbosity_bias_rate": biased.pairwise_metrics["verbosity_bias_rate"],
                        "repeat_consistency": biased.label_metrics["repeat_consistency"],
                        "l0_disagreements": biased.l0_judge_disagreement_count,
                        "l0_overrides": biased.l0_override_count,
                    },
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
    finally:
        async with factory() as session, session.begin():
            await session.execute(
                delete(JudgeCalibrationRecord).where(
                    JudgeCalibrationRecord.id == plan.calibration_id
                )
            )
            await session.execute(delete(ExperimentRecord).where(ExperimentRecord.id == phase_g_id))
        await engine.dispose()


@pytest.mark.integration
async def test_judge_artifact_reload_digest_and_slot_identity_fail_closed(
    database_url: str, tmp_path: Path
) -> None:
    settings = Settings.without_dotenv(database_url=database_url)
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    suite = load_judge_suite(SUITE_ROOT)
    definition = load_judge_definition(SUITE_ROOT / "definition.yaml")
    spec = load_calibration_spec(SUITE_ROOT / "calibration.yaml").model_copy(
        update={"calibration_id": "phase-h-artifact-integrity"}
    )
    plan = build_calibration_plan(spec, suite, {cell.id: definition for cell in spec.judge_cells})
    definitions = {cell.id: definition for cell in plan.judge_cells}
    try:
        async with factory() as session, session.begin():
            await session.execute(
                delete(JudgeCalibrationRecord).where(
                    JudgeCalibrationRecord.id == plan.calibration_id
                )
            )
        async with factory() as session:
            await execute_calibration(
                session,
                plan=plan,
                suite=suite,
                definitions=definitions,
                artifact_root=tmp_path / "artifacts",
            )
        async with factory() as session:
            row = await session.scalar(
                select(JudgeEvaluationRecord)
                .where(JudgeEvaluationRecord.calibration_id == plan.calibration_id)
                .order_by(JudgeEvaluationRecord.slot_order)
                .limit(1)
            )
            assert row is not None and row.artifact_manifest_path and row.artifact_digest
            path = Path(row.artifact_manifest_path)
            original = path.read_bytes()
            slot = next(item for item in plan.slots if item.slot_id == row.slot_id)
            cell = next(item for item in plan.judge_cells if item.id == row.judge_cell_id)
            parsed = json.loads(original)
            mutations = (
                b" " + original,
                (
                    json.dumps(
                        dict(reversed(list(parsed.items()))),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    + "\n"
                ).encode(),
                original.replace(b'"case_id":"', b'"case_id":"tampered-', 1),
            )
            for mutation in mutations:
                path.write_bytes(mutation)
                with pytest.raises(JudgeArtifactError, match="artifact digest mismatch"):
                    load_and_verify_evidence(
                        path,
                        expected_slot=slot,
                        suite_digest=plan.suite_digest,
                        definition_digest=definition.definition_digest,
                        profile_identity=cell.profile_identity,
                        expected_artifact_digest=row.artifact_digest,
                    )
            path.write_bytes(original)
    finally:
        async with factory() as session, session.begin():
            await session.execute(
                delete(JudgeCalibrationRecord).where(
                    JudgeCalibrationRecord.id == plan.calibration_id
                )
            )
        await engine.dispose()


@pytest.mark.integration
async def test_provider_infra_only_lowers_coverage_and_cannot_dilute_capability_errors(
    database_url: str, tmp_path: Path
) -> None:
    settings = Settings.without_dotenv(database_url=database_url)
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    suite = load_judge_suite(SUITE_ROOT)
    definition = load_judge_definition(SUITE_ROOT / "definition.yaml")
    loaded = load_calibration_spec(SUITE_ROOT / "calibration.yaml")
    spec = loaded.model_copy(
        update={
            "calibration_id": "phase-h-infra-denominator",
            "judge_cells": (loaded.judge_cells[0],),
        }
    )
    definitions = {spec.judge_cells[0].id: definition}
    plan = build_calibration_plan(spec, suite, definitions)
    timeouts = frozenset(
        [
            (case_id, repeat, "NOT_APPLICABLE")
            for case_id in ("label-l0-pass", "label-l0-fail")
            for repeat in range(3)
        ]
        + [
            (case_id, repeat, "ORIGINAL")
            for case_id in ("pair-arithmetic", "pair-adversarial")
            for repeat in range(3)
        ]
    )
    try:
        async with factory() as session, session.begin():
            await session.execute(
                delete(JudgeCalibrationRecord).where(
                    JudgeCalibrationRecord.id == plan.calibration_id
                )
            )
        async with factory() as session:
            report = await execute_calibration(
                session,
                plan=plan,
                suite=suite,
                definitions=definitions,
                artifact_root=tmp_path / "infra-artifacts",
                adapters={
                    spec.judge_cells[0].id: FakeJudgeProvider(
                        "GOOD", provider_timeout_slots=timeouts
                    )
                },
            )
        cell = report.cells[0]
        assert cell.label_metrics["coverage"] == 0.6
        assert cell.label_metrics["accuracy"] <= 0.8
        assert cell.label_metrics["macro_f1"] == 1.0
        assert cell.pairwise_metrics["planned_logical_pairs"] == 18
        assert cell.pairwise_metrics["evaluable_logical_pairs"] == 12
        assert cell.pairwise_metrics["provider_infra_trials"] == 6
        assert cell.pairwise_metrics["coverage"] == 0.666667
        assert cell.pairwise_metrics["position_evaluable_count"] == 12
        assert cell.pairwise_metrics["position_consistency_rate"] == 1.0
        assert cell.pairwise_metrics["repeat_consistency"] == 1.0
        assert cell.capability_metrics["evaluable_opportunities"] == 33
        assert cell.capability_metrics["abstain_output_error_count"] == 6
        assert cell.capability_metrics["abstain_output_error_rate"] == 0.181818
        assert cell.qualification_status is QualificationStatus.NOT_QUALIFIED
        assert any("coverage" in reason for reason in cell.qualification_reasons)
    finally:
        async with factory() as session, session.begin():
            await session.execute(
                delete(JudgeCalibrationRecord).where(
                    JudgeCalibrationRecord.id == plan.calibration_id
                )
            )
        await engine.dispose()


@pytest.mark.integration
def test_phase_g_to_phase_h_migration_preserves_experiment_evidence(
    database_url: str,
) -> None:
    base = make_url(database_url)
    database_name = f"harnesslab_h_upgrade_{uuid4().hex[:12]}"
    admin_url = base.set(database="postgres")
    test_url = base.set(database=database_name)
    admin_dsn = admin_url.render_as_string(hide_password=False).replace("+psycopg", "")
    test_dsn = test_url.render_as_string(hide_password=False).replace("+psycopg", "")
    with psycopg.connect(admin_dsn, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    previous = os.environ.get("DATABASE_URL")
    try:
        os.environ["DATABASE_URL"] = test_url.render_as_string(hide_password=False)
        get_settings.cache_clear()
        config = Config("alembic.ini")
        command.upgrade(config, "20260823_0003")
        with psycopg.connect(test_dsn, autocommit=True) as connection:
            connection.execute(
                "INSERT INTO experiment (id,schema_version,name,plan_digest,plan_json,status) "
                "VALUES ('preserved-phase-g',1,'preserved','sha256:"
                + "1" * 64
                + "','{}','completed')"
            )
        command.upgrade(config, "head")
        with psycopg.connect(test_dsn) as connection:
            row = connection.execute(
                "SELECT id,status,plan_digest FROM experiment WHERE id='preserved-phase-g'"
            ).fetchone()
            revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        assert row == ("preserved-phase-g", "completed", "sha256:" + "1" * 64)
        assert revision == ("20260823_0004",)
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        get_settings.cache_clear()
        with psycopg.connect(admin_dsn, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database_name))
            )
