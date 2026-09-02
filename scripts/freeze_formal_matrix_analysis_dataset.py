from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

EXPERIMENT_ID = "core-real-matrix-v6"
SOURCE_CHECKPOINT = "release/core-real-matrix-v6-checkpoint-630.json"
SOURCE_CHECKPOINT_COMMIT = "0ecaa2090c4dd9e40ddac8f418cb5f37669d70a6"
EXPECTED_PLAN_DIGEST = "sha256:c18afc7b003a379f3456b23649e6d161da55e4fb5a34b4702dffbff35fb3604a"
EXPECTED_COUNTS = {
    "row_count": 630,
    "cell_count": 7,
    "task_count": 18,
    "repeat_count": 5,
    "rows_per_cell": 90,
    "primary_completed": 363,
    "primary_failed_subject": 186,
    "primary_failed_infra": 79,
    "primary_cancelled": 2,
    "recovery_total": 79,
    "recovery_capability_pass": 40,
    "recovery_capability_fail": 10,
    "recovery_infra_exhausted": 29,
    "effective_capability_results": 599,
    "infra_missing_after_recovery": 29,
    "cancelled": 2,
}
EXPECTED_CONSERVATIVE_USD = Decimal("16.895947520")
EXPECTED_CONSERVATIVE_CNY = Decimal("94.307760000")
USD_RESERVE = Decimal("0.10")
CNY_RESERVE = Decimal("0.85")
MILLION = Decimal(1_000_000)
MONEY_QUANTUM = Decimal("0.000000001")

CELL_LABELS: dict[str, dict[str, str | None]] = {
    "model-gpt56-relay-responses": {
        "subject_type": "direct",
        "harness": None,
        "model_label": "GPT-5.6 Sol",
    },
    "model-qwen38-alibaba-bailian-chat": {
        "subject_type": "direct",
        "harness": None,
        "model_label": "Qwen3.8-Max",
    },
    "model-deepseek-v4pro-chat": {
        "subject_type": "direct",
        "harness": None,
        "model_label": "DeepSeek V4 Pro",
    },
    "harness-codex-gpt56-medium": {
        "subject_type": "harness",
        "harness": "Codex",
        "model_label": "GPT-5.6 Sol",
    },
    "harness-codex-gpt56-high": {
        "subject_type": "harness",
        "harness": "Codex",
        "model_label": "GPT-5.6 Sol",
    },
    "harness-claude-qwen38-alibaba-bailian": {
        "subject_type": "harness",
        "harness": "Claude Code",
        "model_label": "Qwen3.8-Max",
    },
    "model-deepseek-v4flash-chat": {
        "subject_type": "direct",
        "harness": None,
        "model_label": "DeepSeek V4 Flash",
    },
}


def _json_default(value: object) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def _canonical_line(value: object) -> str:
    return json.dumps(
        value,
        default=_json_default,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _money(value: Decimal) -> str:
    return str(value.quantize(MONEY_QUANTUM))


def _as_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"token or duration value is not numeric: {value!r}")
    integer = int(value)
    if integer != value or integer < 0:
        raise ValueError(f"token or duration value is not a non-negative integer: {value!r}")
    return integer


def _manifest_usage(manifest: dict[str, Any] | None) -> dict[str, Any] | None:
    if manifest is None:
        return None
    usage = manifest.get("usage")
    if isinstance(usage, dict):
        return usage
    provider_result = manifest.get("provider_result")
    provider_usage = provider_result.get("usage") if isinstance(provider_result, dict) else None
    if isinstance(provider_usage, dict):
        return provider_usage
    return None


def _usage_fields(usage: dict[str, Any] | None) -> dict[str, int | None]:
    if usage is None:
        return {
            "input_tokens": None,
            "output_tokens": None,
            "cached_input_tokens": None,
            "cache_write_input_tokens": None,
            "reasoning_output_tokens": None,
        }
    reasoning = usage.get("reasoning_output_tokens")
    if reasoning is None:
        reasoning = usage.get("reasoning_tokens")
    return {
        "input_tokens": _as_int(usage.get("input_tokens")),
        "output_tokens": _as_int(usage.get("output_tokens")),
        "cached_input_tokens": _as_int(usage.get("cached_input_tokens")),
        "cache_write_input_tokens": _as_int(usage.get("cache_write_input_tokens")),
        "reasoning_output_tokens": _as_int(reasoning),
    }


def _currency(cell_id: str) -> str:
    if cell_id in {
        "model-qwen38-alibaba-bailian-chat",
        "harness-claude-qwen38-alibaba-bailian",
    }:
        return "cny"
    return "usd"


def _observed_cost(cell_id: str, usage: dict[str, int | None] | None) -> Decimal | None:
    if usage is None:
        return None
    input_tokens = Decimal(usage.get("input_tokens") or 0)
    output_tokens = Decimal(usage.get("output_tokens") or 0)
    cached_input_tokens = Decimal(usage.get("cached_input_tokens") or 0)
    cache_write_input_tokens = Decimal(usage.get("cache_write_input_tokens") or 0)
    if cell_id in {
        "model-qwen38-alibaba-bailian-chat",
        "harness-claude-qwen38-alibaba-bailian",
    }:
        return (
            (input_tokens + cached_input_tokens + cache_write_input_tokens) * Decimal(12)
            + output_tokens * Decimal(36)
        ) / MILLION
    if cell_id == "model-deepseek-v4pro-chat":
        return (input_tokens * Decimal("1.32") + output_tokens * Decimal("3.96")) / MILLION
    if cell_id == "model-deepseek-v4flash-chat":
        return (input_tokens * Decimal("0.44") + output_tokens * Decimal("1.32")) / MILLION
    if cell_id in {
        "model-gpt56-relay-responses",
        "harness-codex-gpt56-medium",
        "harness-codex-gpt56-high",
    }:
        # Historical checkpoint accounting charged the DB/sidecar input and output fields.
        # Cached-input fields are retained in the dataset but were not a separate additive charge.
        return (input_tokens * Decimal("0.30") + output_tokens * Decimal("1.80")) / MILLION
    raise ValueError(f"unknown cell for accounting: {cell_id}")


def _fetch_database(dsn: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    selected_columns = """
        run_id, experiment_id, slot_id, slot_order, cell_id, lane, task_id,
        task_version, task_digest, repeat_index, paired_slot_identity, status,
        attempt, artifact_manifest_path, evidence_digest, normalized_outcome,
        source_outcome, failure_detail, duration_ms, input_tokens, output_tokens,
        tool_calls, steps, explicit_cost, started_at, finished_at, slot_json
    """
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        experiment = connection.execute(
            """
            SELECT id, schema_version, name, plan_digest, status, plan_json
              FROM experiment
             WHERE id = %s
            """,
            (EXPERIMENT_ID,),
        ).fetchone()
        if experiment is None:
            raise ValueError(f"authoritative database lacks {EXPERIMENT_ID}")
        runs = list(
            connection.execute(
                f"""
                SELECT {selected_columns}
                  FROM experiment_run
                 WHERE experiment_id = %s
                 ORDER BY slot_order
                """,
                (EXPERIMENT_ID,),
            ).fetchall()
        )
    return experiment, runs


def _load_primary_manifest(run: dict[str, Any], evidence_root: Path) -> dict[str, Any] | None:
    path_value = run["artifact_manifest_path"]
    digest_value = run["evidence_digest"]
    if path_value is None:
        if digest_value is not None:
            raise ValueError(f"{run['slot_id']} has an evidence digest without a manifest path")
        return None
    path = Path(path_value).resolve()
    if not path.is_relative_to(evidence_root):
        raise ValueError(f"primary manifest escapes the evidence root: {path}")
    if not path.is_file():
        raise ValueError(f"primary manifest is absent: {path}")
    actual_digest = _sha256_file(path)
    if actual_digest != digest_value:
        raise ValueError(
            f"primary manifest digest mismatch for {run['slot_id']}: "
            f"{digest_value} != {actual_digest}"
        )
    return _load_object(path)


def _load_recovery_sidecars(evidence_root: Path) -> dict[str, tuple[Path, dict[str, Any]]]:
    recovery_root = evidence_root / "recovery"
    sidecars: dict[str, tuple[Path, dict[str, Any]]] = {}
    for path in sorted(recovery_root.glob("*.json")):
        sidecar = _load_object(path)
        slot_id = sidecar.get("slot_id")
        if not isinstance(slot_id, str):
            raise ValueError(f"recovery sidecar lacks slot_id: {path}")
        expected_name = slot_id.removeprefix("sha256:") + ".json"
        if path.name != expected_name:
            raise ValueError(f"recovery sidecar filename does not match slot_id: {path}")
        if slot_id in sidecars:
            raise ValueError(f"duplicate recovery sidecar for {slot_id}")
        sidecars[slot_id] = (path.resolve(), sidecar)
    return sidecars


def _schedule_index(control: dict[str, Any]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for block in control.get("schedule_blocks", []):
        if not isinstance(block, dict):
            raise ValueError("control schedule block is not an object")
        block_key = f"{block.get('task_id')}|{block.get('repeat_index')}"
        block_identity = block.get("block_identity")
        if not isinstance(block_identity, str):
            raise ValueError("control schedule block lacks block_identity")
        for slot_id in block.get("slot_ids", []):
            if not isinstance(slot_id, str) or slot_id in result:
                raise ValueError(f"invalid or duplicate scheduled slot: {slot_id!r}")
            result[slot_id] = {
                "schedule_block_identity": block_identity,
                "block_key": block_key,
            }
    return result


def _recovery_duration(manifest: dict[str, Any]) -> int | None:
    duration = manifest.get("duration_ms")
    if duration is None:
        provider_result = manifest.get("provider_result")
        if isinstance(provider_result, dict):
            duration = provider_result.get("latency_ms")
    return _as_int(duration)


def _build_rows(
    runs: list[dict[str, Any]],
    sidecars: dict[str, tuple[Path, dict[str, Any]]],
    schedule: dict[str, dict[str, str]],
    evidence_root: Path,
    control_cells: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run in runs:
        slot_id = str(run["slot_id"])
        cell_id = str(run["cell_id"])
        if cell_id not in CELL_LABELS or cell_id not in control_cells:
            raise ValueError(f"unknown cell_id: {cell_id}")
        if slot_id not in schedule:
            raise ValueError(f"logical slot is absent from the frozen schedule: {slot_id}")
        primary_manifest = _load_primary_manifest(run, evidence_root)
        primary_manifest_usage = _usage_fields(_manifest_usage(primary_manifest))
        primary_usage_observed = run["input_tokens"] is not None or run["output_tokens"] is not None
        primary_usage = (
            {
                "input_tokens": _as_int(run["input_tokens"]),
                "output_tokens": _as_int(run["output_tokens"]),
                "cached_input_tokens": primary_manifest_usage["cached_input_tokens"],
                "cache_write_input_tokens": primary_manifest_usage["cache_write_input_tokens"],
                "reasoning_output_tokens": primary_manifest_usage["reasoning_output_tokens"],
            }
            if primary_usage_observed
            else None
        )

        recovery_path: Path | None = None
        recovery: dict[str, Any] | None = None
        recovery_manifest: dict[str, Any] | None = None
        recovery_manifest_path: Path | None = None
        if slot_id in sidecars:
            recovery_path, recovery = sidecars[slot_id]
            manifest_path_value = recovery.get("manifest_path")
            if not isinstance(manifest_path_value, str):
                raise ValueError(f"recovery sidecar lacks manifest_path: {recovery_path}")
            recovery_manifest_path = Path(manifest_path_value).resolve()
            if not recovery_manifest_path.is_relative_to(evidence_root):
                raise ValueError(
                    f"recovery manifest escapes the evidence root: {recovery_manifest_path}"
                )
            if not recovery_manifest_path.is_file():
                raise ValueError(f"recovery manifest is absent: {recovery_manifest_path}")
            actual_digest = _sha256_file(recovery_manifest_path)
            if actual_digest != recovery.get("manifest_digest"):
                raise ValueError(f"recovery manifest digest mismatch: {recovery_manifest_path}")
            recovery_manifest = _load_object(recovery_manifest_path)
            if recovery.get("cell_id") != cell_id:
                raise ValueError(f"recovery cell mismatch for {slot_id}")

        status = str(run["status"])
        if status == "failed_infra":
            if recovery is None:
                raise ValueError(f"failed_infra slot lacks final recovery sidecar: {slot_id}")
            effective_outcome = recovery.get("normalized_outcome")
            effective_source = "recovery"
        elif recovery is not None:
            raise ValueError(f"non-infra primary slot has a recovery sidecar: {slot_id}")
        elif status == "cancelled":
            effective_outcome = "cancelled"
            effective_source = "primary"
        elif status in {"completed", "failed_subject"}:
            effective_outcome = run["normalized_outcome"]
            effective_source = "primary"
        else:
            raise ValueError(f"nonterminal or unknown primary status for {slot_id}: {status}")

        recovery_usage_raw = recovery.get("usage") if recovery is not None else None
        if recovery_usage_raw is not None and not isinstance(recovery_usage_raw, dict):
            raise ValueError(f"recovery usage is not an object for {slot_id}")
        recovery_usage = _usage_fields(recovery_usage_raw)
        recovery_usage_observed = recovery_usage_raw is not None

        currency = _currency(cell_id)
        reserve_unit = CNY_RESERVE if currency == "cny" else USD_RESERVE
        reserve_reasons: list[str] = []
        reserve = Decimal(0)
        if not primary_usage_observed:
            reserve += reserve_unit
            reserve_reasons.append("primary_missing_usage")
        extra_attempts = max(int(run["attempt"]) - 1, 0)
        if extra_attempts:
            reserve += reserve_unit * extra_attempts
            reserve_reasons.append(f"primary_unobserved_extra_attempts:{extra_attempts}")
        if recovery is not None and not recovery_usage_observed:
            reserve += reserve_unit
            reserve_reasons.append("recovery_missing_usage")

        primary_cost = _observed_cost(cell_id, primary_usage)
        recovery_cost = _observed_cost(
            cell_id,
            recovery_usage if recovery_usage_observed else None,
        )
        observed_parts = [item for item in (primary_cost, recovery_cost) if item is not None]
        observed_cost = sum(observed_parts, Decimal(0)) if observed_parts else None
        estimated_cost = (observed_cost or Decimal(0)) + reserve

        slot_json = run["slot_json"]
        if not isinstance(slot_json, dict) or not isinstance(slot_json.get("task"), dict):
            raise ValueError(f"slot_json is malformed for {slot_id}")
        task_json = slot_json["task"]
        control_cell = control_cells[cell_id]
        labels = CELL_LABELS[cell_id]
        row: dict[str, Any] = {
            "experiment_id": run["experiment_id"],
            "slot_id": slot_id,
            "slot_order": run["slot_order"],
            "run_id": run["run_id"],
            "cell_id": cell_id,
            "lane": run["lane"],
            "task_id": run["task_id"],
            "task_version": run["task_version"],
            "task_digest": run["task_digest"],
            "repeat_index": run["repeat_index"],
            "paired_slot_identity": run["paired_slot_identity"],
            **schedule[slot_id],
            "primary_status": status,
            "primary_normalized_outcome": run["normalized_outcome"],
            "primary_source_outcome": run["source_outcome"],
            "primary_attempt_count": run["attempt"],
            "primary_failure_detail": run["failure_detail"],
            "primary_started_at": run["started_at"],
            "primary_finished_at": run["finished_at"],
            "primary_duration_ms": run["duration_ms"],
            "effective_outcome": effective_outcome,
            "effective_source": effective_source,
            "infra_recovery_exhausted": bool(
                recovery is not None and recovery.get("normalized_outcome") == "infra_failure"
            ),
            "recovery_attempted": recovery is not None,
            "recovery_sidecar_path": str(recovery_path) if recovery_path else None,
            "recovery_attempt_identity": (
                recovery.get("recovery_attempt_identity") if recovery else None
            ),
            "recovery_run_id": recovery.get("recovery_run_id") if recovery else None,
            "recovery_normalized_outcome": (
                recovery.get("normalized_outcome") if recovery else None
            ),
            "recovery_source_outcome": recovery.get("source_outcome") if recovery else None,
            "recovery_manifest_path": (
                str(recovery_manifest_path) if recovery_manifest_path else None
            ),
            "recovery_manifest_digest": recovery.get("manifest_digest") if recovery else None,
            "recovery_duration_ms": (
                _recovery_duration(recovery_manifest) if recovery_manifest else None
            ),
            "primary_input_tokens": _as_int(run["input_tokens"]),
            "primary_output_tokens": _as_int(run["output_tokens"]),
            "primary_tool_calls": _as_int(run["tool_calls"]),
            "primary_steps": _as_int(run["steps"]),
            "primary_explicit_cost": run["explicit_cost"],
            "primary_cached_input_tokens": primary_manifest_usage["cached_input_tokens"],
            "primary_cache_write_input_tokens": primary_manifest_usage["cache_write_input_tokens"],
            "primary_reasoning_output_tokens": primary_manifest_usage["reasoning_output_tokens"],
            "primary_usage_observed": primary_usage_observed,
            "recovery_input_tokens": recovery_usage["input_tokens"],
            "recovery_output_tokens": recovery_usage["output_tokens"],
            "recovery_cached_input_tokens": recovery_usage["cached_input_tokens"],
            "recovery_cache_write_input_tokens": recovery_usage["cache_write_input_tokens"],
            "recovery_reasoning_output_tokens": recovery_usage["reasoning_output_tokens"],
            "recovery_usage_observed": recovery_usage_observed,
            "estimated_usd": _money(estimated_cost) if currency == "usd" else None,
            "estimated_cny": _money(estimated_cost) if currency == "cny" else None,
            "observed_usage_cost_usd": (
                _money(observed_cost) if currency == "usd" and observed_cost is not None else None
            ),
            "observed_usage_cost_cny": (
                _money(observed_cost) if currency == "cny" and observed_cost is not None else None
            ),
            "conservative_reserve_usd": _money(reserve) if currency == "usd" else None,
            "conservative_reserve_cny": _money(reserve) if currency == "cny" else None,
            "reserve_applied": bool(reserve),
            "conservative_reserve_reasons": reserve_reasons,
            "artifact_manifest_path": run["artifact_manifest_path"],
            "evidence_digest": run["evidence_digest"],
            "task_package_path": task_json.get("package_path"),
            "verifier_identity": task_json.get("verifier_identity"),
            "subject_type": labels["subject_type"],
            "harness": labels["harness"],
            "model_label": labels["model_label"],
            "reasoning_effort": slot_json.get("reasoning_effort"),
            "route_label": control_cell.get("provider_id"),
        }
        rows.append(row)
    return rows


def _validate_rows(rows: list[dict[str, Any]], expected_schedule: set[str]) -> dict[str, Any]:
    if len(rows) != EXPECTED_COUNTS["row_count"]:
        raise ValueError(f"expected 630 dataset rows, found {len(rows)}")
    slot_ids = [str(row.get("slot_id")) for row in rows]
    if len(set(slot_ids)) != EXPECTED_COUNTS["row_count"]:
        raise ValueError("dataset does not contain 630 unique slot_id values")
    if set(slot_ids) != expected_schedule:
        raise ValueError("dataset logical slots do not exactly match the frozen schedule")
    slot_orders = [row.get("slot_order") for row in rows]
    if slot_orders != list(range(EXPECTED_COUNTS["row_count"])):
        raise ValueError("dataset is not in contiguous stable slot_order")

    cells = Counter(str(row["cell_id"]) for row in rows)
    if set(cells) != set(CELL_LABELS) or set(cells.values()) != {EXPECTED_COUNTS["rows_per_cell"]}:
        raise ValueError(f"cell balance mismatch: {dict(cells)}")
    tasks = {str(row["task_id"]) for row in rows}
    repeats = {int(row["repeat_index"]) for row in rows}
    if len(tasks) != EXPECTED_COUNTS["task_count"] or repeats != set(range(5)):
        raise ValueError(f"task/repeat design mismatch: tasks={len(tasks)}, repeats={repeats}")
    logical = Counter(
        (str(row["cell_id"]), str(row["task_id"]), int(row["repeat_index"])) for row in rows
    )
    if len(logical) != 630 or set(logical.values()) != {1}:
        raise ValueError("dataset contains duplicate logical cell/task/repeat slots")

    primary = Counter(str(row["primary_status"]) for row in rows)
    expected_primary = {
        "completed": EXPECTED_COUNTS["primary_completed"],
        "failed_subject": EXPECTED_COUNTS["primary_failed_subject"],
        "failed_infra": EXPECTED_COUNTS["primary_failed_infra"],
        "cancelled": EXPECTED_COUNTS["primary_cancelled"],
    }
    if primary != expected_primary:
        raise ValueError(f"primary aggregate mismatch: {dict(primary)}")

    recovery_rows = [row for row in rows if row["recovery_attempted"]]
    recovery = Counter(str(row["recovery_normalized_outcome"]) for row in recovery_rows)
    expected_recovery = {
        "capability_pass": EXPECTED_COUNTS["recovery_capability_pass"],
        "capability_fail": EXPECTED_COUNTS["recovery_capability_fail"],
        "infra_failure": EXPECTED_COUNTS["recovery_infra_exhausted"],
    }
    if len(recovery_rows) != EXPECTED_COUNTS["recovery_total"] or recovery != expected_recovery:
        raise ValueError(
            f"recovery aggregate mismatch: total={len(recovery_rows)}, {dict(recovery)}"
        )
    recovery_paths = [row["recovery_sidecar_path"] for row in recovery_rows]
    if len(set(recovery_paths)) != len(recovery_paths):
        raise ValueError("duplicate recovery sidecar path in dataset")
    for field in (
        "recovery_attempt_identity",
        "recovery_run_id",
        "recovery_manifest_path",
        "recovery_manifest_digest",
    ):
        values = [row[field] for row in recovery_rows]
        if len(set(values)) != len(values):
            raise ValueError(f"duplicate {field} in dataset")

    effective = Counter(str(row["effective_outcome"]) for row in rows)
    capability_results = effective["capability_pass"] + effective["capability_fail"]
    if (
        capability_results != EXPECTED_COUNTS["effective_capability_results"]
        or effective["infra_failure"] != EXPECTED_COUNTS["infra_missing_after_recovery"]
        or effective["cancelled"] != EXPECTED_COUNTS["cancelled"]
        or sum(effective.values()) != 630
    ):
        raise ValueError(f"effective aggregate mismatch: {dict(effective)}")

    total_usd = sum(
        (Decimal(str(row["estimated_usd"])) for row in rows if row["estimated_usd"]),
        Decimal(0),
    )
    total_cny = sum(
        (Decimal(str(row["estimated_cny"])) for row in rows if row["estimated_cny"]),
        Decimal(0),
    )
    if total_usd != EXPECTED_CONSERVATIVE_USD or total_cny != EXPECTED_CONSERVATIVE_CNY:
        raise ValueError(
            "conservative accounting mismatch: "
            f"USD {total_usd} != {EXPECTED_CONSERVATIVE_USD}; "
            f"CNY {total_cny} != {EXPECTED_CONSERVATIVE_CNY}"
        )
    return {
        "rows": len(rows),
        "unique_slots": len(set(slot_ids)),
        "cells": len(cells),
        "rows_per_cell": next(iter(cells.values())),
        "tasks": len(tasks),
        "repeats": len(repeats),
        "primary": dict(primary),
        "recovery": dict(recovery),
        "effective": dict(effective),
        "conservative_usd": _money(total_usd),
        "conservative_cny": _money(total_cny),
    }


def _build_manifest(
    checkpoint: dict[str, Any], dataset_path: str, dataset_bytes: bytes
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "experiment_id": EXPERIMENT_ID,
        "source_checkpoint": SOURCE_CHECKPOINT,
        "source_checkpoint_commit": SOURCE_CHECKPOINT_COMMIT,
        "source_checkpoint_recorded_at": checkpoint.get("recorded_at"),
        "plan_digest": EXPECTED_PLAN_DIGEST,
        "dataset_path": dataset_path,
        "dataset_sha256": _sha256_bytes(dataset_bytes),
        **EXPECTED_COUNTS,
        "pending_recovery": 0,
        "conservative_usd": _money(EXPECTED_CONSERVATIVE_USD),
        "conservative_cny": _money(EXPECTED_CONSERVATIVE_CNY),
        "budget_fail_stop_enabled": False,
        "budget_control_changed_by_explicit_operator_authorization": True,
        "effective_after_checkpoint_terminal": 440,
        "subject_scientific_design_unchanged": True,
        "dataset_order": "slot_order ascending",
        "dataset_encoding": "UTF-8 JSON Lines; canonical sorted keys; newline terminated",
        "accounting_methodology": {
            "observed_usage": "frozen primary DB fields and recovery sidecar fields",
            "missing_usage_reserve_per_call": {
                "usd": _money(USD_RESERVE),
                "cny": _money(CNY_RESERVE),
            },
            "unobserved_extra_primary_attempts": (
                "primary_attempt_count minus one, reserved in the route currency"
            ),
            "alibaba_bailian_cny_per_million": {
                "input": "12",
                "cached_input": "12",
                "cache_write_input": "12",
                "output": "36",
            },
            "deepseek_peak_usd_per_million": {
                "deepseek-v4-pro": {"input": "1.32", "output": "3.96"},
                "deepseek-v4-flash": {"input": "0.44", "output": "1.32"},
            },
            "gpt_relay_effective_usd_per_million": {
                "input": "0.30",
                "output": "1.80",
                "basis": "frozen base rates multiplied by observed maximum multiplier 0.06",
            },
        },
        "accounting_disclosure": (
            "Conservative cost is HarnessLab accounting, not necessarily actual provider billing. "
            "The exact aggregate conservative accounting and its row decomposition are "
            "authoritative for this frozen dataset."
        ),
    }


def _validate_sources(
    checkpoint: dict[str, Any], control: dict[str, Any], experiment: dict[str, Any]
) -> None:
    if checkpoint.get("experiment_id") != EXPERIMENT_ID:
        raise ValueError("checkpoint experiment identity mismatch")
    logical = checkpoint.get("logical_slots")
    if not isinstance(logical, dict) or (
        logical.get("terminal"),
        logical.get("queued"),
        logical.get("active"),
    ) != (630, 0, 0):
        raise ValueError(f"checkpoint is not the final 630/0/0 durable state: {logical}")
    if control.get("experiment_id") != EXPERIMENT_ID:
        raise ValueError("control experiment identity mismatch")
    if control.get("plan_digest") != EXPECTED_PLAN_DIGEST:
        raise ValueError("control plan digest changed")
    if experiment.get("plan_digest") != EXPECTED_PLAN_DIGEST:
        raise ValueError("database plan digest changed")
    scientific = checkpoint.get("scientific_controls")
    if not isinstance(scientific, dict) or scientific.get("plan_digest") != EXPECTED_PLAN_DIGEST:
        raise ValueError("checkpoint plan digest changed")


def _dataset_bytes(rows: list[dict[str, Any]]) -> bytes:
    return ("\n".join(_canonical_line(row) for row in rows) + "\n").encode()


def _validate_existing(root: Path, dataset_path: Path, manifest_path: Path) -> None:
    manifest = _load_object(manifest_path)
    control = _load_object(root / "release/core-real-matrix-v6-control.json")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        dataset_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"dataset line {line_number} is not an object")
        rows.append(value)
    schedule = set(_schedule_index(control))
    summary = _validate_rows(rows, schedule)
    if manifest.get("dataset_sha256") != _sha256_file(dataset_path):
        raise ValueError("manifest dataset_sha256 does not match dataset bytes")
    if manifest.get("dataset_path") != dataset_path.relative_to(root).as_posix():
        raise ValueError("manifest dataset_path mismatch")
    required_manifest_values: dict[str, Any] = {
        "schema_version": 1,
        "experiment_id": EXPERIMENT_ID,
        "source_checkpoint": SOURCE_CHECKPOINT,
        "source_checkpoint_commit": SOURCE_CHECKPOINT_COMMIT,
        "plan_digest": EXPECTED_PLAN_DIGEST,
        "pending_recovery": 0,
        "budget_fail_stop_enabled": False,
        "budget_control_changed_by_explicit_operator_authorization": True,
        "effective_after_checkpoint_terminal": 440,
        "subject_scientific_design_unchanged": True,
    }
    for key, expected in required_manifest_values.items():
        if manifest.get(key) != expected:
            raise ValueError(f"manifest {key} mismatch: {manifest.get(key)!r} != {expected!r}")
    for key, expected in EXPECTED_COUNTS.items():
        if manifest.get(key) != expected:
            raise ValueError(f"manifest {key} mismatch: {manifest.get(key)} != {expected}")
    if manifest.get("conservative_usd") != _money(EXPECTED_CONSERVATIVE_USD):
        raise ValueError("manifest conservative_usd mismatch")
    if manifest.get("conservative_cny") != _money(EXPECTED_CONSERVATIVE_CNY):
        raise ValueError("manifest conservative_cny mismatch")
    print("VALIDATION=PASS")
    print(_canonical_line(summary))
    print(f"DATASET_SHA256={_sha256_file(dataset_path)}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Freeze the completed Formal Matrix into a deterministic analysis dataset."
    )
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument(
        "--evidence-root",
        type=Path,
        default=Path("/home/dev/harnesslab-evidence/core-real-matrix-v6"),
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("release/core-real-matrix-v6-analysis-dataset.jsonl"),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("release/core-real-matrix-v6-analysis-dataset-manifest.json"),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--validate-existing", action="store_true")
    args = parser.parse_args()

    root = args.repository_root.resolve()
    evidence_root = args.evidence_root.resolve()
    dataset_path = args.dataset if args.dataset.is_absolute() else root / args.dataset
    manifest_path = args.manifest if args.manifest.is_absolute() else root / args.manifest
    if args.validate_existing:
        _validate_existing(root, dataset_path, manifest_path)
        return
    if not args.database_url:
        raise RuntimeError("DATABASE_URL is required for extraction")

    checkpoint = _load_object(root / SOURCE_CHECKPOINT)
    control = _load_object(root / "release/core-real-matrix-v6-control.json")
    experiment, runs = _fetch_database(str(args.database_url).replace("+psycopg", ""))
    _validate_sources(checkpoint, control, experiment)
    schedule = _schedule_index(control)
    control_cells = {
        str(cell["cell_id"]): cell
        for cell in control.get("cells", [])
        if isinstance(cell, dict) and "cell_id" in cell
    }
    sidecars = _load_recovery_sidecars(evidence_root)
    rows = _build_rows(runs, sidecars, schedule, evidence_root, control_cells)
    summary = _validate_rows(rows, set(schedule))
    dataset_bytes = _dataset_bytes(rows)
    dataset_relative = dataset_path.relative_to(root).as_posix()
    manifest = _build_manifest(checkpoint, dataset_relative, dataset_bytes)
    if args.dry_run:
        print("DRY_RUN=PASS")
        print(_canonical_line(summary))
        print(f"DATASET_SHA256={_sha256_bytes(dataset_bytes)}")
        return

    dataset_path.write_bytes(dataset_bytes)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"DATASET={dataset_path}")
    print(f"MANIFEST={manifest_path}")
    print("VALIDATION=PASS")
    print(_canonical_line(summary))
    print(f"DATASET_SHA256={_sha256_bytes(dataset_bytes)}")


if __name__ == "__main__":
    main()
