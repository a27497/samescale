from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

EXPERIMENT_ID = "core-real-matrix-v5"
EXPECTED_EXECUTION_SHA = "1efeaae4e6a0240380042176b245b499cf7774cc"
EXPECTED_SLOT_COUNT = 630
EXPECTED_CELL_COUNT = 7


def _json_default(value: object) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        default=_json_default,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _tree_digest(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    count = 0
    for candidate in sorted(item for item in path.rglob("*") if item.is_file()):
        relative = candidate.relative_to(path).as_posix().encode()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        with candidate.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        count += 1
    return "sha256:" + digest.hexdigest(), count


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _load_ledger(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"ledger line {line_number} is not an object")
        records.append(value)
    if not records:
        raise ValueError("operational ledger is empty")
    for index, record in enumerate(records):
        expected_previous = None if index == 0 else records[index - 1]["checkpoint_digest"]
        if record.get("previous_checkpoint_digest") != expected_previous:
            raise ValueError(f"ledger chain breaks at line {index + 1}")
        if record.get("block_index") != index + 1:
            raise ValueError(f"ledger block index breaks at line {index + 1}")
    return records


def _fetch_all(cursor: psycopg.Cursor[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    cursor.execute(query, {"experiment_id": EXPERIMENT_ID})
    return list(cursor.fetchall())


def _database_evidence(dsn: str, judge_plan_digest: str) -> dict[str, Any]:
    with psycopg.connect(dsn, row_factory=dict_row) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, schema_version, name, plan_digest, status, created_at, started_at,
                   finished_at, plan_json
              FROM experiment
             WHERE id = %(experiment_id)s
            """,
            {"experiment_id": EXPERIMENT_ID},
        )
        experiment = cursor.fetchone()
        if experiment is None:
            raise ValueError(f"authoritative database lacks {EXPERIMENT_ID}")

        logical_slots = _fetch_all(
            cursor,
            """
            SELECT run_id, slot_id, slot_order AS actual_slot_order, cell_id, lane, task_id,
                   task_version, task_digest, repeat_index, paired_slot_identity, status,
                   attempt
              FROM experiment_run
             WHERE experiment_id = %(experiment_id)s
             ORDER BY slot_order
            """,
        )
        attempts = _fetch_all(
            cursor,
            """
            SELECT row_number() OVER (ORDER BY started_at, slot_order) AS launch_order,
                   run_id, slot_id, slot_order AS actual_slot_order, cell_id, task_id,
                   repeat_index, attempt, status, normalized_outcome, source_outcome,
                   started_at, finished_at, duration_ms, artifact_manifest_path,
                   evidence_digest, explicit_cost
              FROM experiment_run
             WHERE experiment_id = %(experiment_id)s AND attempt > 0
             ORDER BY started_at, slot_order
            """,
        )
        per_cell = _fetch_all(
            cursor,
            """
            SELECT cell_id, min(slot_order) AS first_slot_order,
                   max(slot_order) AS last_slot_order, count(*) AS logical_slots,
                   count(*) FILTER (WHERE attempt > 0) AS acquired,
                   count(*) FILTER (WHERE normalized_outcome = 'capability_pass') AS pass,
                   count(*) FILTER (WHERE normalized_outcome = 'capability_fail') AS fail,
                   count(*) FILTER (WHERE normalized_outcome = 'infrastructure_failure') AS infra,
                   min(started_at) AS first_start, max(finished_at) AS last_finish
              FROM experiment_run
             WHERE experiment_id = %(experiment_id)s
             GROUP BY cell_id
             ORDER BY min(slot_order)
            """,
        )
        cursor.execute(
            """
            WITH blocks AS (
                SELECT task_id, repeat_index,
                       count(DISTINCT cell_id) FILTER (WHERE attempt > 0) AS acquired_cells
                  FROM experiment_run
                 WHERE experiment_id = %(experiment_id)s
                 GROUP BY task_id, repeat_index
            )
            SELECT count(*) FILTER (WHERE acquired_cells = 7) AS salvageable,
                   count(*) AS block_count, max(acquired_cells) AS max_acquired_cells
              FROM blocks
            """,
            {"experiment_id": EXPERIMENT_ID},
        )
        salvage = cursor.fetchone()
        assert salvage is not None
        cursor.execute(
            """
            SELECT count(*) AS judge_calibrations,
                   coalesce(sum(evaluation_count), 0) AS judge_evaluations
              FROM (
                    SELECT c.id, count(e.evaluation_id) AS evaluation_count
                      FROM judge_calibration c
                      LEFT JOIN judge_evaluation e ON e.calibration_id = c.id
                     WHERE c.plan_digest = %(judge_plan_digest)s
                     GROUP BY c.id
              ) AS matching
            """,
            {"judge_plan_digest": judge_plan_digest},
        )
        judge = cursor.fetchone()
        assert judge is not None
        cursor.execute(
            """
            SELECT current_database() AS database_name, current_user AS database_user,
                   current_setting('server_version') AS server_version,
                   system_identifier::text AS system_identifier
              FROM pg_control_system()
            """
        )
        db_identity = cursor.fetchone()
        assert db_identity is not None
        cursor.execute("SELECT version_num FROM alembic_version ORDER BY version_num")
        migrations = [row["version_num"] for row in cursor.fetchall()]

    if len(logical_slots) != EXPECTED_SLOT_COUNT:
        raise ValueError(f"expected {EXPECTED_SLOT_COUNT} V5 slots, found {len(logical_slots)}")
    if len(per_cell) != EXPECTED_CELL_COUNT:
        raise ValueError(f"expected {EXPECTED_CELL_COUNT} V5 cells, found {len(per_cell)}")
    if experiment["schema_version"] != 1:
        raise ValueError("V5 incident must bind the schema-v1 production plan")
    return {
        "experiment": experiment,
        "logical_slots": logical_slots,
        "acquired_attempts": attempts,
        "per_cell_counts": per_cell,
        "salvage": salvage,
        "judge": judge,
        "database_identity_digest": _sha256_bytes(
            _canonical_bytes({"database": db_identity, "migrations": migrations})
        ),
        "database_engine": "PostgreSQL",
        "database_migrations": migrations,
    }


def build_incident(repository_root: Path, dsn: str) -> dict[str, Any]:
    ledger_path = repository_root / "artifacts/core-real-matrix-v5/kb3-operational-ledger.jsonl"
    receipt_path = repository_root / "artifacts/core-real-matrix-v5/kb3-prelaunch-receipt.json"
    smoke_path = repository_root / "release/core-real-smoke-plan-v5.json"
    ledger = _load_ledger(ledger_path)
    receipt = _load_json(receipt_path)
    smoke = _load_json(smoke_path)
    if receipt.get("execution_sha") != EXPECTED_EXECUTION_SHA:
        raise ValueError("V5 prelaunch receipt execution SHA is not the frozen base")
    db = _database_evidence(dsn, str(receipt["judge_plan_digest"]))
    experiment = db.pop("experiment")
    plan_json = experiment.pop("plan_json")
    outcomes = Counter(
        str(item["normalized_outcome"])
        for item in db["acquired_attempts"]
        if item["normalized_outcome"] is not None
    )
    artifact_digest, artifact_file_count = _tree_digest(
        repository_root / "artifacts/core-real-matrix-v5"
    )
    runtime_digest, runtime_file_count = _tree_digest(
        repository_root / ".runtime/core-real-matrix-v5"
    )
    final_checkpoint = ledger[-1]
    intended_blocks = {(slot["task_id"], slot["repeat_index"]) for slot in db["logical_slots"]}
    return {
        "schema_version": 1,
        "phase": "K-B3_V5_INCIDENT_CLOSURE",
        "append_only": True,
        "experiment_id": EXPERIMENT_ID,
        "result": "HARD_STOPPED_METHODOLOGY_SCHEDULING_DRIFT",
        "evidence_class": "REAL_DIAGNOSTIC_DESCRIPTIVE_ONLY",
        "formal_kb3_eligibility": "NON_PROMOTABLE",
        "source_of_truth": "AUTHORITATIVE_POSTGRESQL_AND_LOCAL_APPEND_ONLY_EVIDENCE",
        "execution_code_sha": EXPECTED_EXECUTION_SHA,
        "experiment": experiment,
        "experiment_database": {
            "identity_digest": db["database_identity_digest"],
            "engine": db["database_engine"],
            "migrations": db["database_migrations"],
        },
        "control_identities": {
            "prelaunch_receipt_sha256": _sha256_file(receipt_path),
            "semantic_plan_digest": receipt["semantic_plan_digest"],
            "semantic_plan_raw_sha256": receipt["semantic_plan_raw_sha256"],
            "experiment_plan_digest": receipt["experiment_plan_digest"],
            "judge_plan_digest": receipt["judge_plan_digest"],
            "smoke_plan_id": smoke["plan_id"],
            "smoke_release_plan_digest": smoke["release_plan_digest"],
            "matrix_preflight": receipt["matrix_preflight"],
            "judge_preflight": receipt["judge_preflight"],
        },
        "acquisition": {
            "started_at": experiment["started_at"],
            "stopped_at": max(item["finished_at"] for item in db["acquired_attempts"]),
            "logical_slot_count": len(db["logical_slots"]),
            "launched": len(db["acquired_attempts"]),
            "terminal_subject_slots": len(db["acquired_attempts"]),
            "pass": outcomes["capability_pass"],
            "fail": outcomes["capability_fail"],
            "infra": outcomes["infrastructure_failure"],
            "unacquired": sum(item["attempt"] == 0 for item in db["logical_slots"]),
            "active_calls": sum(
                item["status"] in {"claimed", "preparing", "running", "verifying", "scoring"}
                for item in db["logical_slots"]
            ),
            "judge_calls": int(db["judge"]["judge_evaluations"]),
        },
        "scheduling_incident": {
            "intended_policy": "BLOCKED_INTERLEAVED_SCHEDULING",
            "intended_block_key": ["task_id", "repeat_index"],
            "intended_block_count": len(intended_blocks),
            "intended_cells_per_block": EXPECTED_CELL_COUNT,
            "production_schema_version": 1,
            "production_path": ["build_experiment_plan", "enqueue_plan", "run_bounded"],
            "actual_claim_order": "ORDER_BY_SLOT_ORDER",
            "actual_behavior": "CELL_MAJOR_DRAINING",
            "cell_major_ranges": [
                {
                    "cell_id": item["cell_id"],
                    "first_slot_order": item["first_slot_order"],
                    "last_slot_order": item["last_slot_order"],
                }
                for item in db["per_cell_counts"]
            ],
            "methodology_impact": (
                "The attempted acquisition did not apply the frozen task/repeat blocked "
                "interleaving. Provider and temporal order are confounded, so no result from "
                "this attempt is promotable as formal K-B3 evidence."
            ),
        },
        "formal_salvage_audit": {
            "definition": "all seven frozen V5 cells acquired for one task_id/repeat_index block",
            "block_count": int(db["salvage"]["block_count"]),
            "salvageable_blocks": int(db["salvage"]["salvageable"]),
            "max_acquired_cells_in_any_block": int(db["salvage"]["max_acquired_cells"]),
            "result": "NO_FORMAL_SALVAGE" if not db["salvage"]["salvageable"] else "PARTIAL",
        },
        "per_cell_counts": db["per_cell_counts"],
        "logical_slots": db["logical_slots"],
        "chronological_acquired_attempts": db["acquired_attempts"],
        "local_evidence": {
            "ledger_reference": "artifacts/core-real-matrix-v5/kb3-operational-ledger.jsonl",
            "ledger_sha256": _sha256_file(ledger_path),
            "ledger_record_count": len(ledger),
            "ledger_chain_linkage": "VERIFIED",
            "final_checkpoint_digest": final_checkpoint["checkpoint_digest"],
            "artifact_tree_digest": artifact_digest,
            "artifact_file_count": artifact_file_count,
            "runtime_tree_digest": runtime_digest,
            "runtime_file_count": runtime_file_count,
        },
        "cost_and_quota_evidence": {
            "classification": "OPERATOR_LEDGER_ESTIMATE_NOT_BILLING_AUTHORITY",
            "operational_spend_estimate_usd": final_checkpoint["operational_spend_estimate_usd"],
            "projected_completion_spend_usd": final_checkpoint["projected_completion_spend_usd"],
            "qwen_usage_value": final_checkpoint["qwen_usage_value"],
            "qwen_conservative_remaining": final_checkpoint["qwen_conservative_remaining"],
            "paid_fallback_authorized": receipt["paid_fallback_authorized"],
            "v5_operator_planning_limit_not_reusable_for_v6": True,
        },
        "frozen_v5_plan_shape": {
            "schema_version": plan_json["schema_version"],
            "task_count": len(plan_json["tasks"]),
            "cell_count": len(plan_json["cells"]),
            "repeat_count": plan_json["repeat_count"],
            "run_slot_count": len(plan_json["run_slots"]),
        },
        "immutability": {
            "old_database_rows_modified": False,
            "old_manifests_modified": False,
            "old_timestamps_modified": False,
            "old_artifacts_modified": False,
            "freeze_artifact_is_new_append_only_record": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("release/kb3-v5-attempt1-scheduling-incident.json"),
    )
    args = parser.parse_args()
    root = args.repository_root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    if output.exists():
        raise FileExistsError(f"append-only incident artifact already exists: {output}")
    incident = build_incident(root, args.database_url)
    output.write_text(
        json.dumps(incident, default=_json_default, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"FROZEN={output}")
    print(f"DIGEST={_sha256_file(output)}")


if __name__ == "__main__":
    main()
