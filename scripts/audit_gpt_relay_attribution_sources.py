# Reader-facing Markdown strings intentionally preserve complete sentences and symbols.
# ruff: noqa: E501

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

EXPERIMENT_ID = "core-real-matrix-v6"
DATASET_RELATIVE = "release/core-real-matrix-v6-analysis-dataset.jsonl"
DATASET_MANIFEST_RELATIVE = "release/core-real-matrix-v6-analysis-dataset-manifest.json"
FINAL_JSON_RELATIVE = "release/core-real-matrix-v6-final-analysis.json"
FINAL_MARKDOWN_RELATIVE = "release/core-real-matrix-v6-final-analysis.md"
CONTROL_RELATIVE = "release/core-real-matrix-v6-control.json"
OUTPUT_JSON_RELATIVE = "release/core-real-matrix-v6-gpt-relay-attribution-source-audit.json"
OUTPUT_MARKDOWN_RELATIVE = "release/core-real-matrix-v6-gpt-relay-attribution-source-audit.md"
MATCH_MAP_RELATIVE = "release/core-real-matrix-v6-gpt-relay-match-map.jsonl"
DEFAULT_RELAY_CSV = Path(
    "/home/dev/.config/harnesslab/relay-usage/usage_2026-08-27_to_2026-09-02.csv"
)

DATASET_FREEZE_COMMIT = "728aa22aec0c64204b3151ddf9748a8c6746f78a"
MINIMUM_FINAL_ANALYSIS_COMMIT = "649193d"
EXPECTED_DATASET_SHA256 = "sha256:d07f6c96e3bd7882137355cb8b5d2d5682e3d51bffcedce6292375d4a54bbd1d"
EXPECTED_FINAL_JSON_SHA256 = (
    "sha256:59b4e083c54d2d4a3bb1dfd2ad59129c45db81543f5cc5ae51de18a927590252"
)
EXPECTED_FINAL_MARKDOWN_SHA256 = (
    "sha256:5572bcb71eaa4592efab4301dce483c6a5487c7e8482a3ea5086f293993a0f03"
)

GPT_CELLS = (
    "model-gpt56-relay-responses",
    "harness-codex-gpt56-medium",
    "harness-codex-gpt56-high",
)
CELL_LABELS = {
    "model-gpt56-relay-responses": "Direct GPT-5.6",
    "harness-codex-gpt56-medium": "Codex GPT-5.6 medium",
    "harness-codex-gpt56-high": "Codex GPT-5.6 high",
}
EXPECTED_ROWS_PER_CELL = 90
EXPECTED_GPT_LOGICAL_SLOTS = 270
RELAY_COLUMNS = (
    "Time",
    "API Key Name",
    "Model",
    "Reasoning Effort",
    "Inbound Endpoint",
    "IP Address",
    "Type",
    "Delivery",
    "Billing Mode",
    "Input Tokens",
    "Output Tokens",
    "Cache Read Tokens",
    "Cache Creation Tokens",
    "Rate Multiplier",
    "Billed Cost",
    "Original Cost",
    "First Token (ms)",
    "Duration (ms)",
)
SENSITIVE_RELAY_COLUMNS = {"API Key Name", "IP Address"}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), f"{path} must contain a JSON object")
    return cast(dict[str, Any], value)


def _jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        _require(bool(line), f"blank JSONL line at {line_number}")
        value = json.loads(line)
        _require(isinstance(value, dict), f"JSONL line {line_number} is not an object")
        rows.append(cast(dict[str, Any], value))
    return rows


def _iso(value: object, field: str) -> datetime:
    _require(isinstance(value, str) and bool(value), f"{field} must be a timestamp")
    parsed = datetime.fromisoformat(cast(str, value))
    _require(parsed.tzinfo is not None, f"{field} must include an offset")
    return parsed


def _int(row: dict[str, str], field: str) -> int:
    value = row[field]
    _require(value != "", f"relay {field} must not be blank")
    return int(value)


def _decimal(row: dict[str, str], field: str) -> Decimal:
    value = row[field]
    _require(value != "", f"relay {field} must not be blank")
    return Decimal(value)


def _safe_evidence_reference(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    parts = path.parts
    if EXPERIMENT_ID in parts:
        index = parts.index(EXPERIMENT_ID)
        return "evidence://" + "/".join(parts[index:])
    return "evidence://" + path.name


def _manifest(
    row: dict[str, Any], recovery: bool = False
) -> tuple[Path | None, dict[str, Any] | None]:
    field = "recovery_manifest_path" if recovery else "artifact_manifest_path"
    raw = row.get(field)
    if not isinstance(raw, str) or not raw:
        return None, None
    path = Path(raw)
    if not path.is_file():
        return path, None
    value = _json_object(path)
    expected = row.get("recovery_manifest_digest" if recovery else "evidence_digest")
    _require(expected == _sha256(path), f"manifest digest mismatch: {path}")
    return path, value


def _read_relay_csv(path: Path) -> tuple[list[dict[str, str]], dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        _require(tuple(reader.fieldnames or ()) == RELAY_COLUMNS, "relay CSV columns mismatch")
        rows = [dict(row) for row in reader]
    _require(bool(rows), "relay CSV is empty")
    for index, row in enumerate(rows, 1):
        _require(set(row) == set(RELAY_COLUMNS), f"relay row {index} has inconsistent columns")
        for field in RELAY_COLUMNS:
            if field == "First Token (ms)" and row[field] == "":
                continue
            _require(row[field] != "", f"relay row {index} has blank {field}")
        _iso(row["Time"], f"relay row {index} Time")
        for field in (
            "Input Tokens",
            "Output Tokens",
            "Cache Read Tokens",
            "Cache Creation Tokens",
            "Duration (ms)",
        ):
            _require(_int(row, field) >= 0, f"relay row {index} has negative {field}")
        if row["First Token (ms)"]:
            _require(_int(row, "First Token (ms)") >= 0, "negative first-token duration")
        for field in ("Rate Multiplier", "Billed Cost", "Original Cost"):
            _require(_decimal(row, field) >= 0, f"relay row {index} has negative {field}")

    row_tuples = [tuple(row[column] for column in RELAY_COLUMNS) for row in rows]
    nulls = {column: sum(row[column] == "" for row in rows) for column in RELAY_COLUMNS}
    times = [_iso(row["Time"], "Time") for row in rows]
    profile = {
        "sha256": _sha256(path),
        "row_count": len(rows),
        "columns": list(RELAY_COLUMNS),
        "min_time": min(times).isoformat(),
        "max_time": max(times).isoformat(),
        "exact_duplicate_row_count": len(rows) - len(set(row_tuples)),
        "null_counts": nulls,
        "model_counts": dict(sorted(Counter(row["Model"] for row in rows).items())),
        "reasoning_effort_counts": dict(
            sorted(Counter(row["Reasoning Effort"] for row in rows).items())
        ),
        "inbound_endpoint_counts": dict(
            sorted(Counter(row["Inbound Endpoint"] for row in rows).items())
        ),
        "type_counts": dict(sorted(Counter(row["Type"] for row in rows).items())),
        "delivery_counts": dict(sorted(Counter(row["Delivery"] for row in rows).items())),
        "billing_mode_counts": dict(sorted(Counter(row["Billing Mode"] for row in rows).items())),
        "sensitive_columns_profiled_but_values_not_emitted": sorted(SENSITIVE_RELAY_COLUMNS),
        "private_source_basename": path.name,
        "private_source_mode": oct(path.stat().st_mode & 0o777),
        "raw_csv_in_repo": False,
    }
    return rows, profile


def _outcome_category(row: dict[str, Any]) -> str:
    effective = row["effective_outcome"]
    if effective == "capability_pass":
        return "capability_pass"
    if effective == "infra_failure":
        return "infra_missing"
    if effective == "cancelled":
        return "cancelled"
    selected_source = (
        row.get("recovery_source_outcome")
        if row.get("effective_source") == "recovery"
        else row.get("primary_source_outcome")
    )
    if selected_source == "harness_error:execution_budget_exhausted":
        return "execution_budget_exhausted"
    if effective == "capability_fail":
        return "other_capability_fail"
    return "other"


def _trace_evidence(path: Path | None) -> dict[str, bool]:
    directory = path.parent if path is not None else None
    return {
        "sanitized_native_event_stream": bool(
            directory and (directory / "native" / "codex.sanitized.jsonl").is_file()
        ),
        "normalized_trace": bool(directory and (directory / "trace" / "normalized.json").is_file()),
        "workspace_artifact": bool(directory and (directory / "workspace").is_dir()),
        "verifier_artifact": bool(directory and (directory / "verifier").is_dir()),
    }


def _attempt_inventory(
    row: dict[str, Any], *, recovery: bool
) -> tuple[dict[str, Any], dict[str, Any] | None, Path | None]:
    path, manifest = _manifest(row, recovery)
    if path is None:
        return (
            {
                "attempted": not recovery,
                "manifest_reference": None,
                "manifest_present": False,
            },
            None,
            None,
        )
    provider_result = manifest.get("provider_result") if manifest else None
    provider_error = manifest.get("provider_error") if manifest else None
    is_direct = row["cell_id"] == GPT_CELLS[0]
    trace = (
        _trace_evidence(path)
        if not is_direct
        else {
            "sanitized_native_event_stream": False,
            "normalized_trace": False,
            "workspace_artifact": False,
            "verifier_artifact": False,
        }
    )
    usage = provider_result.get("usage") if isinstance(provider_result, dict) else None
    profile = manifest.get("profile") if manifest else None
    execution_timeout_seconds = (
        profile.get("execution_timeout_seconds") if isinstance(profile, dict) else None
    )
    request_id_present = False
    if isinstance(provider_result, dict):
        request_id_present = bool(provider_result.get("request_id"))
    elif isinstance(provider_error, dict):
        request_id_present = bool(provider_error.get("request_id"))
    return (
        {
            "attempted": True,
            "manifest_reference": _safe_evidence_reference(str(path)),
            "manifest_present": manifest is not None,
            "call_level_provider_record_present": bool(
                is_direct and manifest and (provider_result or provider_error)
            ),
            "provider_result_present": isinstance(provider_result, dict),
            "provider_error_present": isinstance(provider_error, dict),
            "provider_request_id_present": request_id_present,
            "provider_usage_present": isinstance(usage, dict),
            "provider_request_timestamp_present": False,
            "provider_response_timestamp_present": False,
            "agent_event_stream_present": trace["sanitized_native_event_stream"],
            "normalized_trace_present": trace["normalized_trace"],
            "workspace_artifact_present": trace["workspace_artifact"],
            "verifier_artifact_present": trace["verifier_artifact"],
            "provider_model_call_count_observable": is_direct,
            "execution_timeout_seconds": execution_timeout_seconds,
        },
        manifest,
        path,
    )


def _validate_frozen_inputs(
    root: Path,
    dataset: list[dict[str, Any]],
    dataset_manifest: dict[str, Any],
    control: dict[str, Any],
) -> dict[str, Any]:
    hashes = {
        DATASET_RELATIVE: _sha256(root / DATASET_RELATIVE),
        FINAL_JSON_RELATIVE: _sha256(root / FINAL_JSON_RELATIVE),
        FINAL_MARKDOWN_RELATIVE: _sha256(root / FINAL_MARKDOWN_RELATIVE),
    }
    _require(hashes[DATASET_RELATIVE] == EXPECTED_DATASET_SHA256, "frozen dataset changed")
    _require(hashes[FINAL_JSON_RELATIVE] == EXPECTED_FINAL_JSON_SHA256, "final JSON changed")
    _require(
        hashes[FINAL_MARKDOWN_RELATIVE] == EXPECTED_FINAL_MARKDOWN_SHA256,
        "final Markdown changed",
    )
    _require(
        dataset_manifest.get("dataset_sha256") == EXPECTED_DATASET_SHA256,
        "dataset manifest SHA mismatch",
    )
    _require(len(dataset) == dataset_manifest.get("row_count") == 630, "dataset row mismatch")
    gpt_rows = [row for row in dataset if row.get("cell_id") in GPT_CELLS]
    counts = Counter(cast(str, row["cell_id"]) for row in gpt_rows)
    _require(len(gpt_rows) == EXPECTED_GPT_LOGICAL_SLOTS, "GPT logical slot count mismatch")
    _require(
        all(counts[cell] == EXPECTED_ROWS_PER_CELL for cell in GPT_CELLS),
        "GPT rows/cell mismatch",
    )
    cell_controls = {
        item["cell_id"]: item
        for item in cast(list[dict[str, Any]], control["cells"])
        if item.get("cell_id") in GPT_CELLS
    }
    _require(set(cell_controls) == set(GPT_CELLS), "missing GPT control cell")
    _require(
        all(item.get("request_timeout_seconds") == 180 for item in cell_controls.values()),
        "unexpected GPT request timeout",
    )
    return {
        "hashes": hashes,
        "dataset_rows": len(dataset),
        "gpt_logical_slots": len(gpt_rows),
        "gpt_slots_by_cell": dict(sorted(counts.items())),
        "gpt_control_request_timeout_seconds": {
            cell: cell_controls[cell]["request_timeout_seconds"] for cell in GPT_CELLS
        },
    }


def _relay_total_input(row: dict[str, str]) -> int:
    return sum(
        _int(row, field) for field in ("Input Tokens", "Cache Read Tokens", "Cache Creation Tokens")
    )


def _direct_candidates(
    slot: dict[str, Any], manifest: dict[str, Any] | None, relay: list[dict[str, str]]
) -> list[int]:
    if manifest is None or not isinstance(manifest.get("provider_result"), dict):
        return []
    result = cast(dict[str, Any], manifest["provider_result"])
    usage = result.get("usage")
    if not isinstance(usage, dict):
        return []
    start = _iso(slot["primary_started_at"], "primary_started_at")
    finish = _iso(slot["primary_finished_at"], "primary_finished_at")
    candidates: list[int] = []
    for data_index, row in enumerate(relay, 1):
        if (
            row["Model"] == result.get("observed_model")
            and row["Reasoning Effort"].lower() == str(slot["reasoning_effort"]).lower()
            and row["Inbound Endpoint"] == "/v1/responses"
            and _relay_total_input(row) == usage.get("input_tokens")
            and _int(row, "Output Tokens") == usage.get("output_tokens")
            and start <= _iso(row["Time"], "Time") <= finish
        ):
            candidates.append(data_index)
    return candidates


def _delivery_count(delivery: str, expected: str) -> int:
    return int(delivery == expected)


def _match_record(
    slot: dict[str, Any], manifest: dict[str, Any], row: dict[str, str], data_index: int
) -> dict[str, Any]:
    result = cast(dict[str, Any], manifest["provider_result"])
    usage = cast(dict[str, Any], result["usage"])
    first_token = None if row["First Token (ms)"] == "" else _int(row, "First Token (ms)")
    duration = _int(row, "Duration (ms)")
    input_tokens = _int(row, "Input Tokens")
    output_tokens = _int(row, "Output Tokens")
    cache_read_tokens = _int(row, "Cache Read Tokens")
    cache_creation_tokens = _int(row, "Cache Creation Tokens")
    billed_cost = str(_decimal(row, "Billed Cost"))
    original_cost = str(_decimal(row, "Original Cost"))
    client_disconnected = _delivery_count(row["Delivery"], "Client disconnected")
    tool_call_delivery = _delivery_count(row["Delivery"], "Tool call")
    text_flushed = _delivery_count(row["Delivery"], "Text flushed")
    return {
        "slot_id": slot["slot_id"],
        "slot_order": slot["slot_order"],
        "run_id": slot["run_id"],
        "cell_id": slot["cell_id"],
        "task_id": slot["task_id"],
        "repeat_index": slot["repeat_index"],
        "attempt_kind": "primary",
        "relay_csv_data_row_index": data_index,
        "relay_csv_file_line_number": data_index + 1,
        "match_class": "DETERMINISTIC_COMPOSITE",
        "matching_evidence": {
            "candidate_count_under_complete_rule": 1,
            "model": row["Model"],
            "reasoning_effort": row["Reasoning Effort"],
            "endpoint": row["Inbound Endpoint"],
            "relay_time_inside_primary_logical_window": True,
            "normalized_total_input_tokens": usage["input_tokens"],
            "output_tokens": usage["output_tokens"],
            "duration_not_used_for_matching": True,
        },
        "logical_slot_relay_exposure": {
            "complete_for_logical_slot": slot["primary_attempt_count"] == 1
            and not slot.get("recovery_attempted"),
            "relay_call_count": 1,
            "relay_sum_duration_ms": duration,
            "relay_median_duration_ms": duration,
            "relay_max_duration_ms": duration,
            "relay_sum_first_token_ms": first_token,
            "relay_median_first_token_ms": first_token,
            "relay_max_first_token_ms": first_token,
            "relay_input_tokens": input_tokens,
            "relay_output_tokens": output_tokens,
            "relay_cache_read_tokens": cache_read_tokens,
            "relay_cache_creation_tokens": cache_creation_tokens,
            "relay_billed_cost": billed_cost,
            "relay_original_cost": original_cost,
            "relay_client_disconnected_count": client_disconnected,
            "relay_tool_call_delivery_count": tool_call_delivery,
            "relay_text_flushed_count": text_flushed,
        },
        "relay": {
            "time": row["Time"],
            "model": row["Model"],
            "reasoning_effort": row["Reasoning Effort"],
            "inbound_endpoint": row["Inbound Endpoint"],
            "type": row["Type"],
            "delivery": row["Delivery"],
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_tokens": cache_read_tokens,
            "cache_creation_tokens": cache_creation_tokens,
            "normalized_total_input_tokens": _relay_total_input(row),
            "first_token_ms": first_token,
            "duration_ms": duration,
            "billed_cost": billed_cost,
            "original_cost": original_cost,
            "client_disconnected_count": client_disconnected,
            "tool_call_delivery_count": tool_call_delivery,
            "text_flushed_count": text_flushed,
        },
    }


def _percentile(values: list[int], probability: float) -> float | int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * probability
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def _distribution(values: list[int]) -> dict[str, Any]:
    return {
        "n": len(values),
        "min": min(values) if values else None,
        "p25": _percentile(values, 0.25),
        "median": statistics.median(values) if values else None,
        "p75": _percentile(values, 0.75),
        "p90": _percentile(values, 0.90),
        "max": max(values) if values else None,
    }


def _build_audit(
    root: Path,
    relay_csv: Path,
    dataset: list[dict[str, Any]],
    dataset_manifest: dict[str, Any],
    control: dict[str, Any],
    relay: list[dict[str, str]],
    relay_profile: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    validation = _validate_frozen_inputs(root, dataset, dataset_manifest, control)
    slots = sorted(
        (row for row in dataset if row["cell_id"] in GPT_CELLS),
        key=lambda row: (cast(int, row["slot_order"]), cast(str, row["cell_id"])),
    )

    primary_manifests: dict[str, dict[str, Any] | None] = {}
    slot_inventory: list[dict[str, Any]] = []
    evidence_counts: dict[str, Counter[str]] = {cell: Counter() for cell in GPT_CELLS}
    direct_known_call_records = 0
    direct_observed_call_records_per_slot: list[int] = []
    for slot in slots:
        cell = cast(str, slot["cell_id"])
        primary_inventory, primary_manifest, primary_path = _attempt_inventory(slot, recovery=False)
        recovery_inventory, _, _ = _attempt_inventory(slot, recovery=True)
        primary_manifests[cast(str, slot["slot_id"])] = primary_manifest
        evidence_counts[cell]["logical_slots"] += 1
        evidence_counts[cell]["primary_manifest_present"] += int(
            primary_inventory["manifest_present"]
        )
        evidence_counts[cell]["recovery_attempted"] += int(bool(slot.get("recovery_attempted")))
        evidence_counts[cell]["recovery_manifest_present"] += int(
            recovery_inventory.get("manifest_present", False)
        )
        evidence_counts[cell]["slots_with_call_level_harness_evidence"] += int(
            primary_inventory.get("call_level_provider_record_present", False)
        )
        evidence_counts[cell]["slots_with_agent_event_stream"] += int(
            primary_inventory.get("agent_event_stream_present", False)
        )
        if cell != GPT_CELLS[0]:
            _require(
                primary_inventory.get("execution_timeout_seconds") in {180, None},
                "unexpected primary Codex execution timeout",
            )
            _require(
                recovery_inventory.get("execution_timeout_seconds") in {180, None},
                "unexpected recovery Codex execution timeout",
            )
            evidence_counts[cell]["primary_manifests_with_180_second_timeout"] += int(
                primary_inventory.get("execution_timeout_seconds") == 180
            )
            evidence_counts[cell]["recovery_manifests_with_180_second_timeout"] += int(
                recovery_inventory.get("execution_timeout_seconds") == 180
            )
        if cell == GPT_CELLS[0]:
            observed = int(primary_inventory.get("call_level_provider_record_present", False))
            if slot.get("recovery_attempted"):
                observed += int(recovery_inventory.get("call_level_provider_record_present", False))
            direct_known_call_records += observed
            direct_observed_call_records_per_slot.append(observed)

        selected_path = (
            Path(cast(str, slot["recovery_manifest_path"]))
            if slot.get("effective_source") == "recovery" and slot.get("recovery_manifest_path")
            else primary_path
        )
        selected_trace = _trace_evidence(selected_path) if cell != GPT_CELLS[0] else None
        slot_inventory.append(
            {
                "slot_id": slot["slot_id"],
                "slot_order": slot["slot_order"],
                "run_id": slot["run_id"],
                "cell_id": cell,
                "task_id": slot["task_id"],
                "repeat_index": slot["repeat_index"],
                "primary_status": slot["primary_status"],
                "effective_outcome": slot["effective_outcome"],
                "effective_source": slot["effective_source"],
                "source_outcome": (
                    slot.get("recovery_source_outcome")
                    if slot.get("effective_source") == "recovery"
                    else slot.get("primary_source_outcome")
                ),
                "primary_attempt_count": slot["primary_attempt_count"],
                "primary_started_at": slot["primary_started_at"],
                "primary_finished_at": slot["primary_finished_at"],
                "primary_duration_ms": slot["primary_duration_ms"],
                "primary_usage": {
                    "input_tokens": slot.get("primary_input_tokens"),
                    "output_tokens": slot.get("primary_output_tokens"),
                    "cached_input_tokens": slot.get("primary_cached_input_tokens"),
                    "cache_write_input_tokens": slot.get("primary_cache_write_input_tokens"),
                    "reasoning_output_tokens": slot.get("primary_reasoning_output_tokens"),
                },
                "primary_evidence": primary_inventory,
                "recovery": {
                    "attempted": bool(slot.get("recovery_attempted")),
                    "run_id": slot.get("recovery_run_id"),
                    "outcome": slot.get("recovery_normalized_outcome"),
                    "source_outcome": slot.get("recovery_source_outcome"),
                    "started_at": None,
                    "finished_at": None,
                    "timestamps_status": "NOT_AVAILABLE",
                    "duration_ms": slot.get("recovery_duration_ms"),
                    "usage": {
                        "input_tokens": slot.get("recovery_input_tokens"),
                        "output_tokens": slot.get("recovery_output_tokens"),
                        "cached_input_tokens": slot.get("recovery_cached_input_tokens"),
                        "cache_write_input_tokens": slot.get("recovery_cache_write_input_tokens"),
                        "reasoning_output_tokens": slot.get("recovery_reasoning_output_tokens"),
                    },
                    "evidence": recovery_inventory,
                },
                "selected_failure_trace": selected_trace,
            }
        )

    proposed: dict[str, tuple[int, dict[str, Any]]] = {}
    row_claims: defaultdict[int, list[str]] = defaultdict(list)
    direct_candidate_count_distribution: Counter[int] = Counter()
    for slot in slots:
        if slot["cell_id"] != GPT_CELLS[0]:
            continue
        manifest = primary_manifests[cast(str, slot["slot_id"])]
        candidates = _direct_candidates(slot, manifest, relay)
        if manifest is not None and isinstance(manifest.get("provider_result"), dict):
            direct_candidate_count_distribution[len(candidates)] += 1
        if len(candidates) == 1 and manifest is not None:
            slot_id = cast(str, slot["slot_id"])
            proposed[slot_id] = (candidates[0], manifest)
            row_claims[candidates[0]].append(slot_id)
    conflicting_rows = {index for index, claims in row_claims.items() if len(claims) != 1}

    match_map: list[dict[str, Any]] = []
    matched_by_slot: dict[str, dict[str, Any]] = {}
    slot_by_id = {cast(str, slot["slot_id"]): slot for slot in slots}
    for slot_id, (data_index, manifest) in proposed.items():
        if data_index in conflicting_rows:
            continue
        record = _match_record(slot_by_id[slot_id], manifest, relay[data_index - 1], data_index)
        match_map.append(record)
        matched_by_slot[slot_id] = record
    match_map.sort(
        key=lambda item: (
            cast(int, item["slot_order"]),
            cast(int, item["relay_csv_data_row_index"]),
        )
    )

    all_windows = [
        (
            cast(str, slot["slot_id"]),
            cast(str, slot["cell_id"]),
            str(slot["reasoning_effort"]).lower(),
            _iso(slot["primary_started_at"], "primary_started_at"),
            _iso(slot["primary_finished_at"], "primary_finished_at"),
        )
        for slot in slots
    ]
    relay_window_multiplicity: Counter[int] = Counter()
    cell_candidate_incidences: Counter[str] = Counter()
    window_candidate_rows: set[int] = set()
    for data_index, relay_row in enumerate(relay, 1):
        time = _iso(relay_row["Time"], "Time")
        effort = relay_row["Reasoning Effort"].lower()
        window_candidates = [
            window
            for window in all_windows
            if window[2] == effort and window[3] <= time <= window[4]
        ]
        if window_candidates:
            window_candidate_rows.add(data_index)
            relay_window_multiplicity[len(window_candidates)] += 1
            for _, cell, _, _, _ in window_candidates:
                cell_candidate_incidences[cell] += 1
    matched_row_indices = {cast(int, row["relay_csv_data_row_index"]) for row in match_map}
    ambiguous_window_rows = window_candidate_rows - matched_row_indices

    coverage: dict[str, Any] = {}
    outcome_coverage: dict[str, dict[str, dict[str, int]]] = {}
    for cell in GPT_CELLS:
        cell_slots = [slot for slot in slots if slot["cell_id"] == cell]
        full = 0
        partial = 0
        unmatched = 0
        outcome_rows: dict[str, dict[str, int]] = defaultdict(
            lambda: {
                "logical_slots": 0,
                "slots_fully_matched": 0,
                "slots_partially_matched": 0,
                "slots_unmatched": 0,
            }
        )
        for slot in cell_slots:
            slot_id = cast(str, slot["slot_id"])
            category = _outcome_category(slot)
            outcome_rows[category]["logical_slots"] += 1
            if (
                slot_id in matched_by_slot
                and slot["primary_attempt_count"] == 1
                and not slot.get("recovery_attempted")
            ):
                full += 1
                outcome_rows[category]["slots_fully_matched"] += 1
            elif slot_id in matched_by_slot:
                partial += 1
                outcome_rows[category]["slots_partially_matched"] += 1
            else:
                unmatched += 1
                outcome_rows[category]["slots_unmatched"] += 1
        counter = evidence_counts[cell]
        if cell == GPT_CELLS[0]:
            calls_expected: int | None = direct_known_call_records
            calls_expected_status = "LOWER_BOUND_FROM_AUTHORITATIVE_MANIFEST_RECORDS"
            calls_unmatched: int | None = direct_known_call_records - len(match_map)
        else:
            calls_expected = None
            calls_expected_status = "NOT_VERIFIED"
            calls_unmatched = None
        coverage[cell] = {
            "logical_slots": len(cell_slots),
            "slots_with_call_level_harness_evidence": counter[
                "slots_with_call_level_harness_evidence"
            ],
            "slots_with_agent_event_stream_but_not_provider_call_events": counter[
                "slots_with_agent_event_stream"
            ],
            "relay_calls_expected": calls_expected,
            "relay_calls_expected_status": calls_expected_status,
            "relay_calls_exact_id_matched": 0,
            "relay_calls_composite_matched": len(match_map) if cell == GPT_CELLS[0] else 0,
            "relay_calls_ambiguous": None,
            "relay_calls_ambiguous_status": "NOT_VERIFIED_PROVIDER_CALL_UNIVERSE",
            "known_harness_call_records_unmatched": calls_unmatched,
            "primary_window_relay_candidate_incidences": cell_candidate_incidences[cell],
            "slots_fully_matched": full,
            "slots_partially_matched": partial,
            "slots_unmatched": unmatched,
        }
        outcome_coverage[cell] = dict(sorted(outcome_rows.items()))

    trace_summary: dict[str, Any] = {}
    for cell in GPT_CELLS[1:]:
        selected = [item for item in slot_inventory if item["cell_id"] == cell]
        failures = [item for item in selected if item["effective_outcome"] == "capability_fail"]
        trace_summary[cell] = {
            "logical_slots": len(selected),
            "selected_attempts_with_sanitized_native_event_stream": sum(
                bool(item["selected_failure_trace"]["sanitized_native_event_stream"])
                for item in selected
            ),
            "capability_failures": len(failures),
            "capability_failures_with_sanitized_native_event_stream": sum(
                bool(item["selected_failure_trace"]["sanitized_native_event_stream"])
                for item in failures
            ),
            "capability_failures_with_verifier_artifact": sum(
                bool(item["selected_failure_trace"]["verifier_artifact"]) for item in failures
            ),
        }

    by_pair = {(row["block_key"], row["cell_id"]): row for row in slots}
    discordance: dict[str, Any] = {}
    for name, left, right in (
        ("direct_pass_to_codex_medium_fail", GPT_CELLS[0], GPT_CELLS[1]),
        ("direct_pass_to_codex_high_fail", GPT_CELLS[0], GPT_CELLS[2]),
        ("codex_medium_pass_to_high_fail", GPT_CELLS[1], GPT_CELLS[2]),
    ):
        targets = [
            by_pair[(block, right)]
            for block in sorted({row["block_key"] for row in slots})
            if (block, left) in by_pair
            and (block, right) in by_pair
            and by_pair[(block, left)]["effective_outcome"] == "capability_pass"
            and by_pair[(block, right)]["effective_outcome"] == "capability_fail"
        ]
        traces = 0
        for target in targets:
            selected_manifest = (
                Path(cast(str, target["recovery_manifest_path"]))
                if target.get("effective_source") == "recovery"
                else Path(cast(str, target["artifact_manifest_path"]))
            )
            traces += int(_trace_evidence(selected_manifest)["sanitized_native_event_stream"])
        discordance[name] = {
            "pairs": len(targets),
            "failing_side_with_sanitized_trace": traces,
        }

    audit = {
        "metadata": {
            "schema_version": 1,
            "experiment_id": EXPERIMENT_ID,
            "audit_scope": "GPT/Codex relay attribution source audit only",
            "data_sources": [
                DATASET_RELATIVE,
                DATASET_MANIFEST_RELATIVE,
                FINAL_JSON_RELATIVE,
                FINAL_MARKDOWN_RELATIVE,
                CONTROL_RELATIVE,
                "private relay CSV identified by basename and SHA256",
                "frozen evidence manifests/traces referenced by the dataset",
                "repository source code at the audited HEAD",
            ],
            "dataset_freeze_commit": DATASET_FREEZE_COMMIT,
            "minimum_final_analysis_commit": MINIMUM_FINAL_ANALYSIS_COMMIT,
            "deterministic_output": True,
            "new_experiment_calls": 0,
            "new_recovery_calls": 0,
            "new_judge_calls": 0,
            "experiment_database_access": "NOT_ACCESSED",
            "frozen_primary_analysis_modified": False,
            "frozen_input_validation": validation,
        },
        "relay_csv": relay_profile,
        "execution_budget_semantics": {
            "taxonomy_value": "harness_error:execution_budget_exhausted",
            "budget_type": "outer Codex process wall-clock execution timeout",
            "exhausted_resource": "elapsed monotonic wall-clock time while the attached Codex process, stdin write, stdout/stderr reads, and process wait run under asyncio.timeout",
            "wall_clock_sensitive": True,
            "model_call_count_sensitive": False,
            "tool_call_sensitive": False,
            "token_sensitive": False,
            "indirect_elapsed_time_contributors": [
                "relay/model response latency",
                "tool execution",
                "sandbox/filesystem work",
                "process and orchestration time",
            ],
            "configured_limit": {
                "value": 180,
                "unit": "seconds",
                "scope": "each configured GPT-related Codex execution plan",
                "source": CONTROL_RELATIVE,
            },
            "classification_rule": "A timed-out Codex capture is classified as execution_budget_exhausted only when it is not cancelled/malformed/profile-violating, has no terminal event, includes thread.started and turn.started, contains none of the disqualifying error/retry/MCP/web event types, has no command infrastructure failure, and includes at least one successful command.",
            "technically_possible_latency_mechanism": "Relay waiting occurs inside the 180-second outer process timeout and can consume part of that wall-clock budget. The source audit does not establish that relay latency caused any observed exhaustion; no such causal claim is made.",
            "evidence": [
                {
                    "source_file": "src/harnesslab/harness_lane/models.py",
                    "function_or_class": "HarnessFailureCategory / CAPABILITY_HARNESS_FAILURES",
                    "lines": "18-35",
                    "rule": "defines execution_budget_exhausted and treats it as a capability harness failure",
                },
                {
                    "source_file": "src/harnesslab/harness_lane/trace.py",
                    "function_or_class": "_clean_execution_budget_exhaustion / collect_codex_jsonl",
                    "lines": "256-298, 349-365",
                    "rule": "strict trace predicate converts a timed_out capture to execution_budget_exhausted; other timeouts remain timeout",
                },
                {
                    "source_file": "src/harnesslab/harness_lane/docker_backend.py",
                    "function_or_class": "DockerCodexBackend._run_attached",
                    "lines": "402-433",
                    "rule": "asyncio.timeout(plan.timeout_seconds) covers stdin plus process I/O/wait; TimeoutError kills the process; duration is monotonic wall time",
                },
                {
                    "source_file": "src/harnesslab/harness_lane/adapter.py",
                    "function_or_class": "CodexHarnessAdapter.prepare",
                    "lines": "151-170",
                    "rule": "copies profile.execution_timeout_seconds into plan.timeout_seconds",
                },
                {
                    "source_file": CONTROL_RELATIVE,
                    "function_or_class": "cells[*].request_timeout_seconds",
                    "lines": "structured JSON control entries",
                    "rule": "all three audited GPT cells configure 180 seconds",
                },
                {
                    "source_file": "frozen Codex primary/recovery manifest profile objects referenced by the dataset",
                    "function_or_class": "profile.execution_timeout_seconds",
                    "lines": "structured evidence field",
                    "rule": "all 217 available Codex primary/recovery manifests record 180 seconds",
                },
            ],
        },
        "harness_evidence_inventory": {
            "summary_by_cell": {
                cell: dict(sorted(evidence_counts[cell].items())) for cell in GPT_CELLS
            },
            "slot_count": len(slot_inventory),
            "slots": slot_inventory,
        },
        "join_key_inventory": {
            "relay_identity_fields": [],
            "relay_missing_identity_fields": [
                "slot_id",
                "run_id",
                "task_id",
                "HarnessLab request id",
                "provider response/request id",
            ],
            "direct_harness_fields": [
                "provider request/response id (not present in relay CSV)",
                "observed/requested model",
                "reasoning effort",
                "Responses endpoint identity",
                "per-call input/output usage on successful results",
                "client-observed latency",
                "logical primary run window",
            ],
            "codex_harness_fields": [
                "outer run/thread identity",
                "outer run duration and 180-second timeout",
                "sanitized agent events without timestamps",
                "aggregate usage when terminal usage exists",
            ],
            "codex_missing_call_fields": [
                "provider call request/response id",
                "provider call start/end timestamp",
                "per-provider-call usage",
                "provider call count",
            ],
            "recovery_missing_fields": ["request timestamp", "response timestamp"],
            "exact_identity_join_available": False,
        },
        "match_methodology": {
            "hierarchy_applied": [
                "EXACT_ID",
                "DETERMINISTIC_COMPOSITE",
                "AMBIGUOUS_WINDOW",
                "UNMATCHED",
            ],
            "exact_id_result": "No common immutable identity column exists; zero exact-ID matches.",
            "deterministic_composite_rule": [
                "attempt is a Direct GPT primary manifest with provider_result and per-call usage",
                "relay Model equals observed model",
                "relay Reasoning Effort equals frozen slot effort",
                "relay Inbound Endpoint equals /v1/responses",
                "relay Time is inside the inclusive frozen primary_started_at/primary_finished_at logical window",
                "relay Input Tokens + Cache Read Tokens + Cache Creation Tokens equals Harness provider_result.usage.input_tokens",
                "relay Output Tokens equals Harness provider_result.usage.output_tokens",
                "exactly one relay row satisfies every predicate",
                "the relay row is not claimed by any other proposed match",
            ],
            "duration_used_for_matching": False,
            "nearest_timestamp_used": False,
            "manual_tie_breaking_used": False,
            "recovery_matching": "UNMATCHED because recovery timestamps are absent; global token uniqueness alone was not accepted without Formal Matrix time isolation.",
            "codex_matching": "UNMATCHED because agent traces do not expose provider-call identities, timestamps, counts, or per-call usage.",
            "direct_success_candidate_count_distribution": dict(
                sorted(direct_candidate_count_distribution.items())
            ),
            "simultaneous_incompatible_row_assignments": len(conflicting_rows),
            "primary_window_isolation": {
                "earliest_relevant_primary_started_at": min(
                    window[3] for window in all_windows
                ).isoformat(),
                "latest_relevant_primary_finished_at": max(
                    window[4] for window in all_windows
                ).isoformat(),
                "relay_rows_inside_at_least_one_primary_window": len(window_candidate_rows),
                "relay_rows_outside_all_primary_windows": len(relay) - len(window_candidate_rows),
                "window_candidate_slot_multiplicity": dict(
                    sorted(relay_window_multiplicity.items())
                ),
                "cell_candidate_incidences_overlap_allowed": dict(
                    sorted(cell_candidate_incidences.items())
                ),
                "unassigned_ambiguous_window_candidate_rows": len(ambiguous_window_rows),
                "warning": "A row inside one logical slot window is not thereby a call match; unrelated relay traffic is present and recovery windows are unavailable.",
            },
        },
        "match_coverage": {
            "direct_gpt": coverage[GPT_CELLS[0]],
            "codex_medium": coverage[GPT_CELLS[1]],
            "codex_high": coverage[GPT_CELLS[2]],
            "exact_id_matched_calls": 0,
            "deterministic_composite_matched_calls": len(match_map),
            "ambiguous_calls": None,
            "ambiguous_calls_status": "NOT_VERIFIED; 1,156 unassigned relay rows are ambiguous primary-window candidates, not proven Harness calls",
            "known_direct_call_records_unmatched": direct_known_call_records - len(match_map),
            "unmatched_call_total_status": "NOT_VERIFIED because Codex provider-call counts and one unobserved Direct primary attempt are unavailable",
        },
        "outcome_coverage": outcome_coverage,
        "model_call_structure": {
            "direct_gpt": {
                "one_provider_request_per_recorded_runner_attempt": True,
                "source_evidence": [
                    "src/harnesslab/model_lane/providers.py:226-317 performs one HTTP POST in _HTTPProviderAdapter.invoke",
                    "src/harnesslab/model_lane/models.py:291-319 constrains GenerationSettings and ProviderResult attempt_count to 1",
                ],
                "authoritative_primary_and_recovery_call_records": direct_known_call_records,
                "unobserved_extra_primary_attempts": sum(
                    max(0, cast(int, slot["primary_attempt_count"]) - 1)
                    for slot in slots
                    if slot["cell_id"] == GPT_CELLS[0]
                ),
                "provider_model_call_count_per_logical_slot_status": "LOWER_BOUND_ONLY",
                "observed_authoritative_call_records_per_slot": _distribution(
                    direct_observed_call_records_per_slot
                ),
            },
            "codex_medium": {
                "provider_model_call_count_per_logical_slot_status": "NOT_VERIFIED",
                "reason": "one outer Codex turn can include an unknown number of Responses calls; sanitized events are agent/tool events, not provider-call events",
                "source_evidence": "src/harnesslab/harness_lane/models.py:181-235 defines sanitized/normalized event fields and has no timestamp or provider request/response ID",
                "distribution": None,
            },
            "codex_high": {
                "provider_model_call_count_per_logical_slot_status": "NOT_VERIFIED",
                "reason": "one outer Codex turn can include an unknown number of Responses calls; sanitized events are agent/tool events, not provider-call events",
                "source_evidence": "src/harnesslab/harness_lane/models.py:181-235 defines sanitized/normalized event fields and has no timestamp or provider request/response ID",
                "distribution": None,
            },
        },
        "relay_exposure_fields": {
            "available_for_deterministic_matches": [
                "duration_ms",
                "first_token_ms",
                "input/output/cache tokens",
                "billed/original cost",
                "delivery/type",
            ],
            "match_map_rows": len(match_map),
            "slot_totals_complete_for_direct_slots": coverage[GPT_CELLS[0]]["slots_fully_matched"],
            "non_relay_elapsed_residual_calculated": False,
            "reason": "No broadly complete Codex mapping exists; this source audit does not perform the later sensitivity analysis.",
            "billing_note": "Relay billing is retained as a distinct operational source and does not overwrite frozen HarnessLab cost accounting.",
        },
        "failure_trace_availability": {
            "decision": "PARTIAL",
            "by_cell": trace_summary,
            "discordant_pair_source_counts_only_no_classification": discordance,
            "supported_or_partially_supported_categories": {
                "execution_budget_exhausted": "YES: typed capture/trace rule and timeout evidence are available",
                "incorrect_code_change": "PARTIAL: workspace changes and verifier artifacts exist for terminal attempts",
                "incomplete_patch": "PARTIAL: changed paths/workspace/terminal output can be inspected",
                "test_failure": "PARTIAL: command and verifier public evidence may expose failures",
                "tool_use_failure": "PARTIAL: sanitized command/tool events are present",
                "excessive_exploration": "PARTIAL: event sequence is visible but provider-call timing/count is absent",
                "wrong_file_modification": "PARTIAL: changed paths and workspace artifacts are present",
                "verifier_failure": "PARTIAL: verifier artifacts exist for terminal verified attempts",
                "planning_strategy_failure": "NO deterministic internal-reasoning evidence; only public behavior can be assessed",
                "context_loss_dilution": "NO direct context-state evidence",
                "other_semantic_failure": "PARTIAL",
            },
            "conclusion": "Frozen evidence is sufficient for a later bounded, evidence-based semantic audit of many failures, but not for uniformly distinguishing latent planning/context causes. Do not claim exhaustive causal classification.",
        },
        "attribution_decision": {
            "value": "GO_PARTIAL_ATTRIBUTION",
            "basis": "A deterministic, collision-free subset of 73 Direct GPT primary calls exists, including 72 fully matched logical slots. Codex calls and recoveries cannot be deterministically mapped.",
            "selection_bias_warning": "The matchable subset is concentrated in Direct GPT successful-result manifests. Zero Codex slots are fully matched, so it cannot support population-level GPT/Codex relay-latency attribution.",
            "permitted_next_use": "Subset/sensitivity analysis explicitly limited to deterministically matched calls, plus separate bounded aggregate analysis; no forced Codex slot join.",
        },
        "terminology": {
            "recommended": "Observed end-to-end latency under frozen route/configuration",
            "prohibited": ["pure model latency", "pure Harness latency"],
            "confounding_disclosure": "GPT latency is route/configuration-confounded because GPT-5.6 used a third-party relay.",
        },
        "limitations": [
            "The relay CSV has no HarnessLab, provider-response, request, run, slot, or task identity column.",
            "The CSV contains traffic outside the Formal Matrix; a logical run window is isolation evidence, not identity evidence.",
            "Recovery attempts have no frozen request timestamps, so they were not joined even when a token tuple might be globally unique.",
            "Codex sanitized traces omit provider-call timestamps, immutable provider IDs, per-call usage, and provider-call counts.",
            "One Direct primary extra attempt is reserved in the frozen dataset but lacks an authoritative manifest in the selected slot evidence.",
            "Relay and client latency definitions differ; duration was not used as a join key and no residual overhead metric was calculated.",
            "Ambiguous-window counts are relay candidate rows, not confirmed Harness calls.",
            "The frozen 630-row outcomes and final statistical analysis remain unchanged.",
        ],
        "validation": {
            "frozen_dataset_sha_unchanged": True,
            "final_analysis_files_unchanged": True,
            "experiment_db_unchanged": "NOT_ACCESSED",
            "new_subject_calls": 0,
            "new_recovery_calls": 0,
            "new_judge_calls": 0,
            "raw_relay_csv_outside_repo": not relay_csv.resolve().is_relative_to(root.resolve()),
            "raw_relay_csv_mode": relay_profile["private_source_mode"],
            "match_map_contains_sensitive_relay_columns": False,
            "relay_row_assigned_to_incompatible_calls": len(conflicting_rows),
            "ambiguous_row_labeled_exact": 0,
            "match_order_stable": True,
        },
    }
    return audit, match_map


def _markdown(audit: dict[str, Any]) -> str:
    relay = cast(dict[str, Any], audit["relay_csv"])
    coverage = cast(dict[str, Any], audit["match_coverage"])
    direct = cast(dict[str, Any], coverage["direct_gpt"])
    medium = cast(dict[str, Any], coverage["codex_medium"])
    high = cast(dict[str, Any], coverage["codex_high"])
    window = cast(dict[str, Any], audit["match_methodology"])["primary_window_isolation"]
    budget = cast(dict[str, Any], audit["execution_budget_semantics"])
    failure = cast(dict[str, Any], audit["failure_trace_availability"])
    decision = cast(dict[str, Any], audit["attribution_decision"])
    return f"""# HarnessLab GPT/Codex Relay Attribution Source Audit

## Decision

**{decision["value"]}**

There is a deterministic, collision-free subset of **{coverage["deterministic_composite_matched_calls"]} Direct GPT primary calls**, covering **{direct["slots_fully_matched"]} fully matched Direct GPT slots** plus **{direct["slots_partially_matched"]} partially matched slot**. There are no exact-ID matches. Codex medium/high provider calls and all recovery calls lack the frozen call-level time/identity evidence required for deterministic relay assignment, so no Codex slot is matched.

This is not broad enough for population-level GPT/Codex relay-latency attribution. A later analysis may use the deterministic subset only as an explicitly selected subset/sensitivity analysis. It must not force a Codex or recovery join.

## Frozen-source safeguards

- Frozen dataset SHA256: `{audit["metadata"]["frozen_input_validation"]["hashes"][DATASET_RELATIVE]}` (unchanged)
- Final analysis JSON/Markdown: unchanged at their preregistered hashes
- Frozen dataset rows: {audit["metadata"]["frozen_input_validation"]["dataset_rows"]}; GPT logical slots audited: {audit["metadata"]["frozen_input_validation"]["gpt_logical_slots"]}
- New subject/provider calls: 0; new recoveries: 0; new Judge calls: 0
- Experiment DB: not accessed
- Raw relay CSV: private path outside the repository, mode `{relay["private_source_mode"]}`; not committed

## Relay CSV validation

| Check | Result |
|---|---:|
| SHA256 | `{relay["sha256"]}` |
| Rows | {relay["row_count"]} |
| Columns | {len(relay["columns"])} |
| Exact duplicate rows | {relay["exact_duplicate_row_count"]} |
| Min time | `{relay["min_time"]}` |
| Max time | `{relay["max_time"]}` |
| Model | `gpt-5.6-sol` ({relay["model_counts"]["gpt-5.6-sol"]}) |
| Endpoint | `/v1/responses` ({relay["inbound_endpoint_counts"]["/v1/responses"]}) |
| Medium / High | {relay["reasoning_effort_counts"]["Medium"]} / {relay["reasoning_effort_counts"]["High"]} |

API-key and IP values were profiled for completeness but are intentionally not emitted.

## What `execution_budget_exhausted` means

`harness_error:execution_budget_exhausted` is a **wall-clock outer Codex process timeout**, configured to **{budget["configured_limit"]["value"]} seconds** for the audited GPT Codex cells. All 217 available primary/recovery Codex manifests independently record that same limit. It is not a token, cost, model-call-count, tool-call-count, turn-count, or step-count limit.

The backend wraps prompt input plus process stdout/stderr and process wait in `asyncio.timeout(plan.timeout_seconds)`, kills the process on timeout, and measures elapsed time with a monotonic clock. The trace classifier emits `execution_budget_exhausted` only for a clean-progress timeout: started thread/turn, at least one successful command, no terminal, no malformed/profile-violation/disqualifying error/retry/tool events, and no command infrastructure failure. Otherwise the typed result remains a generic timeout.

Relay waiting can technically consume this 180-second outer budget, so wall-clock sensitivity is **YES**. This audit does **not** establish that relay latency caused any observed exhaustion.

Source anchors:

- `src/harnesslab/harness_lane/models.py:18-35` — taxonomy and capability classification
- `src/harnesslab/harness_lane/trace.py:256-298,349-365` — strict exhaustion predicate and timeout mapping
- `src/harnesslab/harness_lane/docker_backend.py:402-433` — enforced wall-clock timeout and monotonic duration
- `src/harnesslab/harness_lane/adapter.py:151-170` — profile timeout copied into the execution plan
- `release/core-real-matrix-v6-control.json` — 180-second configuration for all three audited GPT cells
- frozen Codex manifests — `profile.execution_timeout_seconds=180` in all 217 available primary/recovery manifests

## Join audit

Level A fails: the relay CSV contains no request/response/relay correlation ID, while Direct GPT manifests do contain provider response IDs. No common immutable ID exists.

Level B succeeds only for a Direct GPT primary-success subset. A match requires all of:

1. exact model, reasoning effort, and `/v1/responses` endpoint;
2. relay `Time` inside the frozen logical primary window;
3. relay `Input Tokens + Cache Read Tokens + Cache Creation Tokens` exactly equal Harness provider `input_tokens`;
4. relay output tokens exactly equal Harness provider output tokens;
5. exactly one relay row satisfies the full rule; and
6. that relay row is not assigned to any other call.

Duration, nearest-time selection, token-nearest selection, and manual tie-breaking are not used. The rule yields {coverage["deterministic_composite_matched_calls"]} matches and zero incompatible row assignments.

Level C is retained only as candidate evidence. The primary windows span `{window["earliest_relevant_primary_started_at"]}` through `{window["latest_relevant_primary_finished_at"]}`. Of {relay["row_count"]} relay rows, {window["relay_rows_inside_at_least_one_primary_window"]} fall inside at least one matching-effort GPT primary window; after deterministic assignments, **{window["unassigned_ambiguous_window_candidate_rows"]} rows remain ambiguous window candidates**. They are not confirmed Harness calls. Recovery windows are unavailable.

## Coverage by cell

| Cell | Logical slots | Call-level Harness evidence | Composite calls | Fully matched slots | Partially matched | Unmatched slots | Known unmatched call records |
|---|---:|---:|---:|---:|---:|---:|---:|
| Direct GPT | {direct["logical_slots"]} | {direct["slots_with_call_level_harness_evidence"]} | {direct["relay_calls_composite_matched"]} | {direct["slots_fully_matched"]} | {direct["slots_partially_matched"]} | {direct["slots_unmatched"]} | {direct["known_harness_call_records_unmatched"]} |
| Codex medium | {medium["logical_slots"]} | {medium["slots_with_call_level_harness_evidence"]} | 0 | {medium["slots_fully_matched"]} | {medium["slots_partially_matched"]} | {medium["slots_unmatched"]} | NOT_VERIFIED |
| Codex high | {high["logical_slots"]} | {high["slots_with_call_level_harness_evidence"]} | 0 | {high["slots_fully_matched"]} | {high["slots_partially_matched"]} | {high["slots_unmatched"]} | NOT_VERIFIED |

The 31 known unmatched records are Direct GPT authoritative primary/recovery manifests. A total unmatched provider-call count is **NOT_VERIFIED** because Codex call counts and one unobserved Direct primary attempt are unavailable. Likewise, the 1,156 ambiguous items are relay rows, not a proven count of ambiguous Harness calls.

For every deterministic match, the secret-free match map preserves the relay CSV data-row/file-line identity, match class and predicates, call metrics, and the requested slot-level count/sum/median/max exposure fields. Seventy-two entries are complete one-call logical-slot totals; the remaining entry is explicitly marked incomplete because that slot also has unmatched attempt/recovery evidence.

Coverage is materially selection-biased by execution structure: Direct GPT has a matched successful-result subset; Codex has zero matched slots. This rules out full attribution. Within Direct GPT, all three frozen capability-fail slots are fully matched, 69 of 83 passes are fully matched, one pass is partial, and all four infra outcomes are unmatched; those Direct-only rates do not repair the missing Codex population.

## Provider-call structure

- Direct GPT: each recorded runner attempt performs one provider request (`src/harnesslab/model_lane/providers.py:226-317`; `src/harnesslab/model_lane/models.py:291-319`). There are {audit["model_call_structure"]["direct_gpt"]["authoritative_primary_and_recovery_call_records"]} authoritative primary/recovery call records, but the logical-slot distribution is a lower bound because one extra primary attempt is not represented by the selected manifest. The observed record-count distribution is min={audit["model_call_structure"]["direct_gpt"]["observed_authoritative_call_records_per_slot"]["min"]}, p25={audit["model_call_structure"]["direct_gpt"]["observed_authoritative_call_records_per_slot"]["p25"]}, median={audit["model_call_structure"]["direct_gpt"]["observed_authoritative_call_records_per_slot"]["median"]}, p75={audit["model_call_structure"]["direct_gpt"]["observed_authoritative_call_records_per_slot"]["p75"]}, p90={audit["model_call_structure"]["direct_gpt"]["observed_authoritative_call_records_per_slot"]["p90"]}, max={audit["model_call_structure"]["direct_gpt"]["observed_authoritative_call_records_per_slot"]["max"]}.
- Codex medium/high: provider-call count per logical slot is **NOT_VERIFIED**. The frozen streams expose one outer agent run and agent/tool events, not immutable Responses-call events; the event schemas at `src/harnesslab/harness_lane/models.py:181-235` contain no timestamp or provider request/response ID. No median, p25, p75, p90, min, or max is reported.

No `non_relay_elapsed_residual_ms` is calculated in this source audit because Codex call coverage is absent and the later sensitivity analysis is out of scope.

## Failure-attribution source availability

Overall availability is **{failure["decision"]}**. All selected Codex capability-failure attempts have sanitized native and normalized traces. The frozen evidence can directly support the typed execution-budget category and can often support bounded review of commands, changed paths, public messages, workspace state, and verifier outputs. It does not expose private reasoning or provider-call timing/count, so planning/strategy and context-loss/dilution cannot be uniformly or causally distinguished.

This task does not classify any discordant pair. It only confirms that later semantic attribution is feasible for a bounded subset and must retain `PARTIAL` limitations.

## Scientific interpretation

The frozen primary analysis remains valid as **observed end-to-end configuration performance**. GPT latency is route/configuration-confounded because GPT-5.6 used a third-party relay. Use **“Observed end-to-end latency under frozen route/configuration.”** Do not call it pure model latency or pure Harness latency.
"""


def _write_outputs(
    root: Path, audit: dict[str, Any], match_map: list[dict[str, Any]]
) -> tuple[Path, Path, Path]:
    json_path = root / OUTPUT_JSON_RELATIVE
    markdown_path = root / OUTPUT_MARKDOWN_RELATIVE
    map_path = root / MATCH_MAP_RELATIVE
    json_path.write_text(
        json.dumps(audit, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_markdown(audit), encoding="utf-8")
    map_path.write_text(
        "".join(
            json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"
            for row in match_map
        ),
        encoding="utf-8",
    )
    return json_path, markdown_path, map_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--relay-csv", type=Path, default=DEFAULT_RELAY_CSV)
    args = parser.parse_args()
    root = args.repo_root.resolve()
    relay_csv = args.relay_csv.resolve()
    _require(relay_csv.is_file(), f"relay CSV missing: {relay_csv}")
    _require(not relay_csv.is_relative_to(root), "raw relay CSV must remain outside the repo")

    dataset = _jsonl(root / DATASET_RELATIVE)
    dataset_manifest = _json_object(root / DATASET_MANIFEST_RELATIVE)
    control = _json_object(root / CONTROL_RELATIVE)
    relay, relay_profile = _read_relay_csv(relay_csv)
    audit, match_map = _build_audit(
        root, relay_csv, dataset, dataset_manifest, control, relay, relay_profile
    )
    json_path, markdown_path, map_path = _write_outputs(root, audit, match_map)
    print(
        json.dumps(
            {
                "audit_json": str(json_path),
                "audit_markdown": str(markdown_path),
                "match_map": str(map_path),
                "match_map_rows": len(match_map),
                "attribution_decision": audit["attribution_decision"]["value"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
