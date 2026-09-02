# Reader-facing Markdown strings intentionally preserve complete sentences and symbols.
# ruff: noqa: E501, RUF001

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

EXPERIMENT_ID = "core-real-matrix-v6"
DATASET_RELATIVE = "release/core-real-matrix-v6-analysis-dataset.jsonl"
MANIFEST_RELATIVE = "release/core-real-matrix-v6-analysis-dataset-manifest.json"
OUTPUT_JSON_RELATIVE = "release/core-real-matrix-v6-final-analysis.json"
OUTPUT_MARKDOWN_RELATIVE = "release/core-real-matrix-v6-final-analysis.md"
DATASET_FREEZE_COMMIT = "728aa22aec0c64204b3151ddf9748a8c6746f78a"
EXPECTED_DATASET_SHA256 = "sha256:d07f6c96e3bd7882137355cb8b5d2d5682e3d51bffcedce6292375d4a54bbd1d"
EXPECTED_USD = Decimal("16.895947520")
EXPECTED_CNY = Decimal("94.307760000")
BOOTSTRAP_SEED = 20260902
BOOTSTRAP_REPLICATES = 50_000
TOTAL_ROWS = 630
ROWS_PER_CELL = 90
TASK_COUNT = 18
REPEAT_COUNT = 5
Z_95 = 1.959963984540054

CELL_ORDER = [
    "model-gpt56-relay-responses",
    "model-qwen38-alibaba-bailian-chat",
    "model-deepseek-v4pro-chat",
    "model-deepseek-v4flash-chat",
    "harness-codex-gpt56-medium",
    "harness-codex-gpt56-high",
    "harness-claude-qwen38-alibaba-bailian",
]
CELL_LABELS = {
    "model-gpt56-relay-responses": "Direct GPT-5.6 Sol",
    "model-qwen38-alibaba-bailian-chat": "Direct Qwen3.8-Max",
    "model-deepseek-v4pro-chat": "Direct DeepSeek V4 Pro",
    "model-deepseek-v4flash-chat": "Direct DeepSeek V4 Flash",
    "harness-codex-gpt56-medium": "Codex + GPT-5.6 medium",
    "harness-codex-gpt56-high": "Codex + GPT-5.6 high",
    "harness-claude-qwen38-alibaba-bailian": "Claude Code + Qwen3.8-Max",
}
DIRECT_CELLS = CELL_ORDER[:4]
COMPARISONS = {
    "gpt_harness_effect": (
        "model-gpt56-relay-responses",
        "harness-codex-gpt56-medium",
    ),
    "reasoning_effort_effect": (
        "harness-codex-gpt56-medium",
        "harness-codex-gpt56-high",
    ),
    "qwen_harness_effect": (
        "model-qwen38-alibaba-bailian-chat",
        "harness-claude-qwen38-alibaba-bailian",
    ),
}
COMPARISON_LABELS = {
    "gpt_harness_effect": "GPT Harness Effect",
    "reasoning_effort_effect": "Reasoning Effort Effect",
    "qwen_harness_effect": "Qwen Harness Effect",
}
CAPABILITY_OUTCOMES = {"capability_pass", "capability_fail"}
FROZEN_OUTCOMES = CAPABILITY_OUTCOMES | {"infra_failure", "cancelled"}
PRIMARY_STATUSES = {"completed", "failed_subject", "failed_infra", "cancelled"}
TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "reasoning_output_tokens",
)


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _finite_number(value: object, field: str) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric or null: {value!r}")
    if not math.isfinite(float(value)):
        raise ValueError(f"{field} must be finite: {value!r}")
    return value


def _clean(value: float | int | None, digits: int = 12) -> float | int | None:
    if value is None or isinstance(value, int):
        return value
    rounded = round(value, digits)
    return 0.0 if rounded == 0 else rounded


def _rate(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else _clean(numerator / denominator)


def _mean(values: Sequence[float | int]) -> float | None:
    return None if not values else _clean(statistics.fmean(values))


def _median(values: Sequence[float | int]) -> float | int | None:
    return None if not values else _clean(statistics.median(values))


def _percentile(values: Sequence[float | int], probability: float) -> float | int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * probability
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return _clean(ordered[lower])
    fraction = index - lower
    return _clean(ordered[lower] + fraction * (ordered[upper] - ordered[lower]))


def _wilson_interval(successes: int, trials: int) -> dict[str, float | None]:
    if trials == 0:
        return {"low": None, "high": None}
    proportion = successes / trials
    denominator = 1 + Z_95**2 / trials
    center = (proportion + Z_95**2 / (2 * trials)) / denominator
    half_width = (
        Z_95
        * math.sqrt(proportion * (1 - proportion) / trials + Z_95**2 / (4 * trials**2))
        / denominator
    )
    return {"low": _clean(center - half_width), "high": _clean(center + half_width)}


def _outcome(row: dict[str, Any]) -> str:
    frozen = row["effective_outcome"]
    return "infra_missing" if frozen == "infra_failure" else frozen


def _load_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), f"{path} must contain a JSON object")
    return cast(dict[str, Any], value)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        _require(bool(line), f"blank JSONL line at {line_number}")
        value = json.loads(line)
        _require(isinstance(value, dict), f"JSONL line {line_number} is not an object")
        rows.append(value)
    return rows


def _validate_dataset(
    rows: list[dict[str, Any]], manifest: dict[str, Any], dataset_sha256: str
) -> dict[str, Any]:
    _require(dataset_sha256 == EXPECTED_DATASET_SHA256, "dataset SHA256 mismatch")
    _require(manifest.get("dataset_sha256") == dataset_sha256, "manifest dataset SHA mismatch")
    _require(manifest.get("experiment_id") == EXPERIMENT_ID, "manifest experiment mismatch")
    _require(len(rows) == TOTAL_ROWS == manifest.get("row_count"), "row count mismatch")
    _require(set(row["cell_id"] for row in rows) == set(CELL_ORDER), "cell set mismatch")
    cell_counts = Counter(row["cell_id"] for row in rows)
    _require(all(cell_counts[cell] == ROWS_PER_CELL for cell in CELL_ORDER), "rows/cell mismatch")
    _require(len({row["slot_id"] for row in rows}) == TOTAL_ROWS, "slot_id is not unique")
    _require(
        [row["slot_order"] for row in rows] == list(range(TOTAL_ROWS)),
        "slot_order is not exactly 0..629",
    )
    tasks = sorted({row["task_id"] for row in rows})
    repeats = sorted({row["repeat_index"] for row in rows})
    _require(len(tasks) == TASK_COUNT == manifest.get("task_count"), "task count mismatch")
    _require(repeats == list(range(REPEAT_COUNT)), "repeat indexes mismatch")
    pair_keys = {(row["task_id"], row["repeat_index"]) for row in rows}
    _require(len(pair_keys) == ROWS_PER_CELL, "task/repeat pair count mismatch")
    _require(
        len({(row["cell_id"], row["task_id"], row["repeat_index"]) for row in rows}) == TOTAL_ROWS,
        "cell/task/repeat grain is not unique",
    )
    for cell in CELL_ORDER:
        cell_rows = [row for row in rows if row["cell_id"] == cell]
        _require(
            {(row["task_id"], row["repeat_index"]) for row in cell_rows} == pair_keys,
            f"paired coverage mismatch for {cell}",
        )
    paired_identities: dict[tuple[str, int], set[str]] = defaultdict(set)
    for row in rows:
        paired_identities[(row["task_id"], row["repeat_index"])].add(row["paired_slot_identity"])
    _require(
        all(len(values) == 1 for values in paired_identities.values()),
        "paired_slot_identity is inconsistent within task/repeat",
    )
    frozen_outcomes = Counter(row["effective_outcome"] for row in rows)
    _require(set(frozen_outcomes) == FROZEN_OUTCOMES, "unexpected effective_outcome domain")
    _require(
        all(row["primary_status"] in PRIMARY_STATUSES for row in rows),
        "unexpected primary_status domain",
    )
    for row in rows:
        _require(row["experiment_id"] == EXPERIMENT_ID, "row experiment mismatch")
        attempted = row["recovery_attempted"]
        _require(isinstance(attempted, bool), "recovery_attempted must be boolean")
        _require(
            attempted == (row["primary_status"] == "failed_infra"),
            f"recovery/primary status mismatch for {row['slot_id']}",
        )
        if attempted:
            _require(row["effective_source"] == "recovery", "recovery source mismatch")
            _require(
                row["effective_outcome"] == row["recovery_normalized_outcome"],
                "recovery/effective outcome mismatch",
            )
        else:
            _require(row["effective_source"] == "primary", "primary source mismatch")
            _require(
                row["effective_outcome"] == row["primary_normalized_outcome"],
                "primary/effective outcome mismatch",
            )
        _require(
            row["infra_recovery_exhausted"]
            == (row["recovery_normalized_outcome"] == "infra_failure"),
            "infra recovery exhaustion mismatch",
        )
        for prefix in ("primary", "recovery"):
            _finite_number(row.get(f"{prefix}_duration_ms"), f"{prefix}_duration_ms")
            for field in TOKEN_FIELDS:
                _finite_number(row.get(f"{prefix}_{field}"), f"{prefix}_{field}")

    primary = Counter(row["primary_status"] for row in rows)
    recovery = Counter(
        row["recovery_normalized_outcome"] for row in rows if row["recovery_attempted"]
    )
    expected_primary = {
        "completed": manifest["primary_completed"],
        "failed_subject": manifest["primary_failed_subject"],
        "failed_infra": manifest["primary_failed_infra"],
        "cancelled": manifest["primary_cancelled"],
    }
    _require(dict(primary) == expected_primary, "primary totals do not reconcile")
    expected_recovery = {
        "capability_pass": manifest["recovery_capability_pass"],
        "capability_fail": manifest["recovery_capability_fail"],
        "infra_failure": manifest["recovery_infra_exhausted"],
    }
    _require(dict(recovery) == expected_recovery, "recovery totals do not reconcile")
    _require(sum(recovery.values()) == manifest["recovery_total"], "recovery total mismatch")
    _require(
        frozen_outcomes["capability_pass"] + frozen_outcomes["capability_fail"]
        == manifest["effective_capability_results"],
        "effective capability total mismatch",
    )
    _require(
        frozen_outcomes["infra_failure"] == manifest["infra_missing_after_recovery"],
        "final infra total mismatch",
    )
    _require(frozen_outcomes["cancelled"] == manifest["cancelled"] == 2, "cancelled mismatch")

    usd_total = sum(
        (Decimal(row["estimated_usd"]) for row in rows if row["estimated_usd"] is not None),
        Decimal(0),
    )
    cny_total = sum(
        (Decimal(row["estimated_cny"]) for row in rows if row["estimated_cny"] is not None),
        Decimal(0),
    )
    _require(usd_total == EXPECTED_USD, "USD cost does not reconcile")
    _require(cny_total == EXPECTED_CNY, "CNY cost does not reconcile")
    _require(Decimal(manifest["conservative_usd"]) == usd_total, "manifest USD mismatch")
    _require(Decimal(manifest["conservative_cny"]) == cny_total, "manifest CNY mismatch")

    return {
        "status": "PASS",
        "dataset_sha256": dataset_sha256,
        "dataset_sha_matches_manifest": True,
        "row_count": len(rows),
        "unique_slots": len({row["slot_id"] for row in rows}),
        "cell_count": len(cell_counts),
        "rows_per_cell": {cell: cell_counts[cell] for cell in CELL_ORDER},
        "task_count": len(tasks),
        "repeat_count": len(repeats),
        "paired_task_repeat_identities": len(pair_keys),
        "primary_totals_reconciled": True,
        "recovery_totals_reconciled": True,
        "effective_totals_reconciled": True,
        "cost_usd_reconciled": True,
        "cost_cny_reconciled": True,
        "frozen_effective_outcomes": dict(sorted(frozen_outcomes.items())),
        "analysis_outcome_mapping": {"infra_failure": "infra_missing"},
    }


def _cell_summary(cell_rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(_outcome(row) for row in cell_rows)
    evaluable = counts["capability_pass"] + counts["capability_fail"]
    slots = len(cell_rows)
    return {
        "logical_slots": slots,
        "capability_pass": counts["capability_pass"],
        "capability_fail": counts["capability_fail"],
        "capability_evaluable": evaluable,
        "infra_missing": counts["infra_missing"],
        "cancelled": counts["cancelled"],
        "capability_pass_rate": _rate(counts["capability_pass"], evaluable),
        "capability_pass_rate_wilson_95": _wilson_interval(counts["capability_pass"], evaluable),
        "operational_pass_rate": _rate(counts["capability_pass"], slots),
        "operational_pass_rate_wilson_95": _wilson_interval(counts["capability_pass"], slots),
        "infra_missing_rate": _rate(counts["infra_missing"], slots),
        "cancelled_rate": _rate(counts["cancelled"], slots),
    }


def _cluster_bootstrap(
    task_values: dict[str, float | None], all_tasks: list[str]
) -> dict[str, Any]:
    _require(
        any(value is not None for value in task_values.values()), "no task values to bootstrap"
    )
    rng = random.Random(BOOTSTRAP_SEED)
    estimates: list[float] = []
    skipped = 0
    for _ in range(BOOTSTRAP_REPLICATES):
        sampled = [task_values[rng.choice(all_tasks)] for _ in all_tasks]
        available = [value for value in sampled if value is not None]
        if not available:
            skipped += 1
            continue
        estimates.append(statistics.fmean(available))
    _require(bool(estimates), "all bootstrap replicates lacked evaluable tasks")
    return {
        "low": _percentile(estimates, 0.025),
        "high": _percentile(estimates, 0.975),
        "seed": BOOTSTRAP_SEED,
        "replicates_requested": BOOTSTRAP_REPLICATES,
        "replicates_used": len(estimates),
        "replicates_skipped_no_evaluable_tasks": skipped,
        "method": "task_cluster_percentile",
        "task_weighting": "equal_task",
    }


def _mcnemar_exact_p(improvements: int, regressions: int) -> float:
    discordant = improvements + regressions
    if discordant == 0:
        return 1.0
    smaller = min(improvements, regressions)
    tail = sum(math.comb(discordant, k) for k in range(smaller + 1)) / (2**discordant)
    return _clean(min(1.0, 2 * tail))  # type: ignore[return-value]


def _paired_comparison(
    rows_by_cell_key: dict[str, dict[tuple[str, int], dict[str, Any]]],
    baseline_cell: str,
    variant_cell: str,
    all_tasks: list[str],
) -> dict[str, Any]:
    baseline_rows = rows_by_cell_key[baseline_cell]
    variant_rows = rows_by_cell_key[variant_cell]
    keys = sorted(baseline_rows)
    _require(keys == sorted(variant_rows), "paired comparison key mismatch")
    _require(len(keys) == ROWS_PER_CELL, "paired comparison does not have 90 possible pairs")

    complete: list[tuple[dict[str, Any], dict[str, Any]]] = []
    excluded_baseline_infra = 0
    excluded_variant_infra = 0
    excluded_cancelled = 0
    task_deltas: dict[str, list[int]] = defaultdict(list)
    task_baseline: dict[str, list[int]] = defaultdict(list)
    task_variant: dict[str, list[int]] = defaultdict(list)
    improvements = regressions = both_pass = both_fail = 0
    for key in keys:
        baseline = baseline_rows[key]
        variant = variant_rows[key]
        baseline_outcome = _outcome(baseline)
        variant_outcome = _outcome(variant)
        excluded_baseline_infra += baseline_outcome == "infra_missing"
        excluded_variant_infra += variant_outcome == "infra_missing"
        excluded_cancelled += "cancelled" in {baseline_outcome, variant_outcome}
        if (
            baseline_outcome not in CAPABILITY_OUTCOMES
            or variant_outcome not in CAPABILITY_OUTCOMES
        ):
            continue
        complete.append((baseline, variant))
        baseline_pass = int(baseline_outcome == "capability_pass")
        variant_pass = int(variant_outcome == "capability_pass")
        task_id = key[0]
        task_baseline[task_id].append(baseline_pass)
        task_variant[task_id].append(variant_pass)
        task_deltas[task_id].append(variant_pass - baseline_pass)
        improvements += baseline_pass == 0 and variant_pass == 1
        regressions += baseline_pass == 1 and variant_pass == 0
        both_pass += baseline_pass == 1 and variant_pass == 1
        both_fail += baseline_pass == 0 and variant_pass == 0

    task_table: list[dict[str, Any]] = []
    capability_task_means: dict[str, float | None] = {}
    for task in all_tasks:
        deltas = task_deltas.get(task, [])
        capability_task_means[task] = None if not deltas else statistics.fmean(deltas)
        task_table.append(
            {
                "task_id": task,
                "available_capability_complete_repeats": len(deltas),
                "baseline_capability_pass_fraction": _mean(task_baseline.get(task, [])),
                "variant_capability_pass_fraction": _mean(task_variant.get(task, [])),
                "delta": _mean(deltas),
            }
        )
    available_task_deltas = [value for value in capability_task_means.values() if value is not None]
    primary_delta = _mean(available_task_deltas)
    pair_weighted_delta = _mean(
        [
            int(_outcome(variant) == "capability_pass")
            - int(_outcome(baseline) == "capability_pass")
            for baseline, variant in complete
        ]
    )
    complete_n = len(complete)
    baseline_passes = sum(_outcome(pair[0]) == "capability_pass" for pair in complete)
    variant_passes = sum(_outcome(pair[1]) == "capability_pass" for pair in complete)

    operational_task_deltas: dict[str, float | None] = {}
    baseline_operational = []
    variant_operational = []
    for task in all_tasks:
        task_keys = [key for key in keys if key[0] == task]
        deltas = []
        for key in task_keys:
            baseline_pass = int(_outcome(baseline_rows[key]) == "capability_pass")
            variant_pass = int(_outcome(variant_rows[key]) == "capability_pass")
            baseline_operational.append(baseline_pass)
            variant_operational.append(variant_pass)
            deltas.append(variant_pass - baseline_pass)
        operational_task_deltas[task] = statistics.fmean(deltas)
    operational_delta = _mean(
        [value for value in operational_task_deltas.values() if value is not None]
    )

    baseline_latency: list[float | int] = []
    variant_latency: list[float | int] = []
    latency_deltas: list[float | int] = []
    for key in keys:
        baseline_duration = baseline_rows[key].get("primary_duration_ms")
        variant_duration = variant_rows[key].get("primary_duration_ms")
        if baseline_duration is not None and variant_duration is not None:
            baseline_latency.append(baseline_duration)
            variant_latency.append(variant_duration)
            latency_deltas.append(variant_duration - baseline_duration)

    baseline_cost = _cell_cost([baseline_rows[key] for key in keys])
    variant_cost = _cell_cost([variant_rows[key] for key in keys])
    _require(
        baseline_cost["native_currency"] == variant_cost["native_currency"],
        "paired cost currency mismatch",
    )
    baseline_mean_cost = baseline_cost["mean_estimated_cost_per_logical_slot"]
    variant_mean_cost = variant_cost["mean_estimated_cost_per_logical_slot"]
    _require(
        isinstance(baseline_mean_cost, (float, int))
        and isinstance(variant_mean_cost, (float, int)),
        "paired mean cost missing",
    )
    cost_delta = _clean(variant_mean_cost - baseline_mean_cost)
    cost_multiplier = (
        None if baseline_mean_cost == 0 else _clean(variant_mean_cost / baseline_mean_cost)
    )
    cap_operational_gap = (
        None
        if primary_delta is None or operational_delta is None
        else _clean(primary_delta - operational_delta)
    )
    material = bool(
        cap_operational_gap is not None
        and (
            abs(cap_operational_gap) >= 0.05 or (primary_delta or 0) * (operational_delta or 0) < 0
        )
    )
    return {
        "baseline_cell": baseline_cell,
        "variant_cell": variant_cell,
        "capability": {
            "total_possible_pairs": len(keys),
            "complete_pairs": complete_n,
            "tasks_with_pairs": len(available_task_deltas),
            "baseline_pass_rate": _rate(baseline_passes, complete_n),
            "variant_pass_rate": _rate(variant_passes, complete_n),
            "delta": primary_delta,
            "delta_estimand": "equal-task mean of within-task paired deltas",
            "complete_pair_row_weighted_delta": pair_weighted_delta,
            "cluster_bootstrap_ci": _cluster_bootstrap(capability_task_means, all_tasks),
            "discordant_baseline_fail_variant_pass": improvements,
            "discordant_baseline_pass_variant_fail": regressions,
            "both_pass": both_pass,
            "both_fail": both_fail,
            "mcnemar_exact_p": _mcnemar_exact_p(improvements, regressions),
        },
        "operational": {
            "pair_count": len(keys),
            "baseline_pass_rate": _mean(baseline_operational),
            "variant_pass_rate": _mean(variant_operational),
            "delta": operational_delta,
            "delta_estimand": "equal-task mean of within-task paired operational deltas",
            "cluster_bootstrap_ci": _cluster_bootstrap(operational_task_deltas, all_tasks),
        },
        "missingness": {
            "baseline_final_infra_rate": _rate(
                sum(_outcome(row) == "infra_missing" for row in baseline_rows.values()),
                len(keys),
            ),
            "variant_final_infra_rate": _rate(
                sum(_outcome(row) == "infra_missing" for row in variant_rows.values()),
                len(keys),
            ),
            "capability_complete_pair_coverage": _rate(complete_n, len(keys)),
            "excluded_due_to_baseline_infra": excluded_baseline_infra,
            "excluded_due_to_variant_infra": excluded_variant_infra,
            "excluded_due_to_cancelled": excluded_cancelled,
            "exclusion_reason_counts_are_overlapping": True,
            "capability_minus_operational_delta": cap_operational_gap,
            "material_difference_rule": "absolute gap >= 0.05 or opposite signs",
            "infrastructure_reliability_changes_practical_conclusion": material,
        },
        "task_heterogeneity": {
            "tasks": task_table,
            "tasks_favoring_variant": sum(
                row["delta"] is not None and row["delta"] > 0 for row in task_table
            ),
            "tasks_favoring_baseline": sum(
                row["delta"] is not None and row["delta"] < 0 for row in task_table
            ),
            "tasks_tied": sum(row["delta"] == 0 for row in task_table),
            "tasks_without_capability_pairs": sum(row["delta"] is None for row in task_table),
        },
        "latency": {
            "paired_latency_n": len(latency_deltas),
            "paired_latency_coverage": _rate(len(latency_deltas), len(keys)),
            "baseline_primary_median_ms": _median(baseline_latency),
            "variant_primary_median_ms": _median(variant_latency),
            "median_variant_minus_baseline_ms": _median(latency_deltas),
            "coverage_materially_incomplete": len(latency_deltas) < len(keys),
        },
        "cost_and_efficiency": {
            "accounting_basis": "HarnessLab conservative estimated accounting",
            "currency": baseline_cost["native_currency"],
            "baseline_mean_cost_per_logical_slot": baseline_mean_cost,
            "variant_mean_cost_per_logical_slot": variant_mean_cost,
            "cost_delta_per_logical_slot": cost_delta,
            "cost_multiplier": cost_multiplier,
            "incremental_operational_pass_rate_delta": operational_delta,
            "incremental_mean_cost_per_slot": cost_delta,
        },
    }


def _repeat_variability(cell_rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_task: dict[str, list[int]] = defaultdict(list)
    for row in cell_rows:
        outcome = _outcome(row)
        if outcome in CAPABILITY_OUTCOMES:
            by_task[row["task_id"]].append(int(outcome == "capability_pass"))
    variances: list[float] = []
    task_fractions: list[float] = []
    mixed = 0
    eligible = 0
    for values in by_task.values():
        task_fractions.append(statistics.fmean(values))
        if len(values) >= 2:
            eligible += 1
            variances.append(statistics.variance(values))
            mixed += len(set(values)) > 1
    return {
        "tasks_with_2plus_evaluable_repeats": eligible,
        "tasks_with_mixed_pass_fail": mixed,
        "mean_within_task_repeat_variance": _mean(variances),
        "median_task_pass_fraction": _median(task_fractions),
        "mixed_task_rate": _rate(mixed, eligible),
    }


def _latency_stats(cell_rows: list[dict[str, Any]]) -> dict[str, Any]:
    primary = [
        row["primary_duration_ms"] for row in cell_rows if row["primary_duration_ms"] is not None
    ]
    recovery = [
        row["recovery_duration_ms"] for row in cell_rows if row["recovery_duration_ms"] is not None
    ]
    return {
        "latency_observed_n": len(primary),
        "latency_coverage": _rate(len(primary), len(cell_rows)),
        "median_ms": _median(primary),
        "p25_ms": _percentile(primary, 0.25),
        "p75_ms": _percentile(primary, 0.75),
        "p90_ms": _percentile(primary, 0.90),
        "mean_ms": _mean(primary),
        "recovery_latency_observed_n": len(recovery),
        "recovery_latency_coverage_of_attempts": _rate(
            len(recovery), sum(row["recovery_attempted"] for row in cell_rows)
        ),
        "recovery_median_ms": _median(recovery),
        "recovery_p90_ms": _percentile(recovery, 0.90),
    }


def _usage_stats(cell_rows: list[dict[str, Any]], prefix: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        f"{prefix}_usage_observed_n": sum(
            bool(row[f"{prefix}_usage_observed"]) for row in cell_rows
        ),
    }
    denominator = (
        len(cell_rows)
        if prefix == "primary"
        else sum(row["recovery_attempted"] for row in cell_rows)
    )
    result[f"{prefix}_usage_coverage"] = _rate(result[f"{prefix}_usage_observed_n"], denominator)
    for field in TOKEN_FIELDS:
        values = [
            row[f"{prefix}_{field}"] for row in cell_rows if row[f"{prefix}_{field}"] is not None
        ]
        result[f"{field}_observed_n"] = len(values)
        result[f"median_{field}"] = _median(values)
        result[f"mean_{field}"] = _mean(values)
        result[f"total_{field}"] = None if not values else sum(values)
    return result


def _decimal_to_number(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def _cell_cost(cell_rows: list[dict[str, Any]]) -> dict[str, Any]:
    usd_values = [
        Decimal(row["estimated_usd"]) for row in cell_rows if row["estimated_usd"] is not None
    ]
    cny_values = [
        Decimal(row["estimated_cny"]) for row in cell_rows if row["estimated_cny"] is not None
    ]
    _require(not (usd_values and cny_values), "cell contains mixed cost currencies")
    native_currency = "USD" if usd_values else "CNY"
    values = usd_values or cny_values
    _require(len(values) == len(cell_rows), "missing frozen estimated cost")
    total = sum(values, Decimal(0))
    evaluable = sum(_outcome(row) in CAPABILITY_OUTCOMES for row in cell_rows)
    passes = sum(_outcome(row) == "capability_pass" for row in cell_rows)
    return {
        "accounting_basis": "HarnessLab conservative estimated accounting",
        "native_currency": native_currency,
        "total_estimated_usd": _decimal_to_number(total if native_currency == "USD" else None),
        "total_estimated_cny": _decimal_to_number(total if native_currency == "CNY" else None),
        "mean_estimated_cost_per_logical_slot": _decimal_to_number(total / len(cell_rows)),
        "mean_estimated_cost_per_capability_evaluable_result": _decimal_to_number(
            None if evaluable == 0 else total / evaluable
        ),
        "estimated_cost_per_capability_pass": _decimal_to_number(
            None if passes == 0 else total / passes
        ),
        "operational_passes": passes,
        "cost_per_operational_pass": _decimal_to_number(None if passes == 0 else total / passes),
    }


def _infra_recovery(cell_rows: list[dict[str, Any]]) -> dict[str, Any]:
    primary = Counter(row["primary_status"] for row in cell_rows)
    recovery = Counter(
        row["recovery_normalized_outcome"] for row in cell_rows if row["recovery_attempted"]
    )
    attempted = sum(row["recovery_attempted"] for row in cell_rows)
    resolved = recovery["capability_pass"] + recovery["capability_fail"]
    final_infra = sum(_outcome(row) == "infra_missing" for row in cell_rows)
    return {
        "primary_completed": primary["completed"],
        "primary_failed_subject": primary["failed_subject"],
        "primary_failed_infra": primary["failed_infra"],
        "primary_cancelled": primary["cancelled"],
        "primary_infra_rate": _rate(primary["failed_infra"], len(cell_rows)),
        "recovery_attempted": attempted,
        "recovery_capability_pass": recovery["capability_pass"],
        "recovery_capability_fail": recovery["capability_fail"],
        "recovery_infra_exhausted": recovery["infra_failure"],
        "recovery_resolution_rate": _rate(resolved, attempted),
        "final_infra_missing": final_infra,
        "final_infra_missing_rate": _rate(final_infra, len(cell_rows)),
    }


def _pct(value: float | int | None, digits: int = 1) -> str:
    return "NA" if value is None else f"{100 * value:.{digits}f}%"


def _num(value: float | int | None, digits: int = 1) -> str:
    return "NA" if value is None else f"{value:,.{digits}f}"


def _money(value: float | int | None) -> str:
    return "NA" if value is None else f"{value:.9f}"


def _interval(interval: dict[str, Any]) -> str:
    return f"[{_pct(interval['low'])}, {_pct(interval['high'])}]"


def _markdown_table(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(str(value) for value in row) + " |" for row in rows)
    return lines


def _render_markdown(analysis: dict[str, Any]) -> str:
    cells = analysis["cell_summaries"]
    comparisons = analysis["paired_comparisons"]
    lines = [
        "# Formal Matrix Final Statistical Analysis",
        "",
        "This is a deterministic statistical readout of the frozen 630-row analysis dataset. "
        "It does not rerun, recover, or rejudge experiment evidence.",
        "",
        "## Dataset integrity",
        "",
        f"- Validation: **{analysis['dataset_validation']['status']}**",
        f"- Dataset SHA256: `{analysis['dataset_validation']['dataset_sha256']}`",
        f"- Grain: {TOTAL_ROWS} unique logical slots; {TASK_COUNT} tasks × {REPEAT_COUNT} repeats × {len(CELL_ORDER)} cells; {ROWS_PER_CELL} rows/cell.",
        "- Frozen `effective_outcome=infra_failure` is reported as `infra_missing`; it is never counted as capability failure.",
        "- Capability pass rate conditions on capability-evaluable results. Operational pass rate retains all 90 logical slots per cell.",
        "- Primary, recovery, effective-outcome, and exact native-currency cost totals reconcile to the manifest.",
        "",
        "## Cell-level results",
        "",
    ]
    lines.extend(
        _markdown_table(
            [
                "Cell",
                "Pass",
                "Fail",
                "Evaluable",
                "Infra",
                "Cancelled",
                "Capability pass rate (95% Wilson CI)",
                "Operational pass rate",
            ],
            (
                (
                    CELL_LABELS[cell],
                    summary["capability_pass"],
                    summary["capability_fail"],
                    summary["capability_evaluable"],
                    summary["infra_missing"],
                    summary["cancelled"],
                    f"{_pct(summary['capability_pass_rate'])} {_interval(summary['capability_pass_rate_wilson_95'])}",
                    _pct(summary["operational_pass_rate"]),
                )
                for cell, summary in cells.items()
            ),
        )
    )
    for key in COMPARISONS:
        comparison = comparisons[key]
        capability = comparison["capability"]
        operational = comparison["operational"]
        missingness = comparison["missingness"]
        heterogeneity = comparison["task_heterogeneity"]
        latency = comparison["latency"]
        lines.extend(
            [
                "",
                f"## {COMPARISON_LABELS[key]}",
                "",
                f"Baseline: `{comparison['baseline_cell']}`  ",
                f"Variant: `{comparison['variant_cell']}`",
                "",
                "**CAPABILITY EFFECT** (both members capability-evaluable; equal task weighting):",
                "",
                f"- Complete pairs: {capability['complete_pairs']}/90 ({_pct(missingness['capability_complete_pair_coverage'])}); tasks with pairs: {capability['tasks_with_pairs']}/18.",
                f"- Baseline/variant pass rates on complete pairs: {_pct(capability['baseline_pass_rate'])} / {_pct(capability['variant_pass_rate'])}.",
                f"- Paired capability delta: {_pct(capability['delta'])}; 95% task-cluster bootstrap CI {_interval(capability['cluster_bootstrap_ci'])}.",
                f"- Discordant pairs (fail→pass / pass→fail): {capability['discordant_baseline_fail_variant_pass']} / {capability['discordant_baseline_pass_variant_fail']}; both pass/fail: {capability['both_pass']} / {capability['both_fail']}; exact McNemar p={capability['mcnemar_exact_p']:.6g} (secondary evidence).",
                "",
                "**OPERATIONAL EFFECT** (all 90 pairs; infra/cancelled are non-pass):",
                "",
                f"- Baseline/variant operational pass rates: {_pct(operational['baseline_pass_rate'])} / {_pct(operational['variant_pass_rate'])}.",
                f"- Paired operational delta: {_pct(operational['delta'])}; 95% task-cluster bootstrap CI {_interval(operational['cluster_bootstrap_ci'])}.",
                "",
                f"Missingness: baseline/variant final infra rates {_pct(missingness['baseline_final_infra_rate'])} / {_pct(missingness['variant_final_infra_rate'])}; exclusion flags baseline infra={missingness['excluded_due_to_baseline_infra']}, variant infra={missingness['excluded_due_to_variant_infra']}, cancelled={missingness['excluded_due_to_cancelled']} (overlapping counts).",
                f"Task heterogeneity: {heterogeneity['tasks_favoring_variant']} favor variant, {heterogeneity['tasks_favoring_baseline']} favor baseline, {heterogeneity['tasks_tied']} tied, {heterogeneity['tasks_without_capability_pairs']} without capability-complete pairs.",
                f"Paired primary latency: n={latency['paired_latency_n']}/90; median variant−baseline={_num(latency['median_variant_minus_baseline_ms'], 0)} ms.",
            ]
        )
        if missingness["infrastructure_reliability_changes_practical_conclusion"]:
            lines.append(
                "- **Infrastructure reliability changes the practical conclusion** under the prespecified materiality rule."
            )

    lines.extend(["", "## Direct route/model comparison", ""])
    lines.append(
        "> Direct-model comparisons are model/provider-route comparisons. Model identity and provider/route are confounded, so they must not be presented as clean causal model effects."
    )
    lines.append("")
    lines.extend(
        _markdown_table(
            [
                "Route/model combination",
                "Capability pass rate",
                "95% Wilson CI",
                "Operational pass rate",
                "Final infra rate",
            ],
            (
                (
                    CELL_LABELS[cell],
                    _pct(cells[cell]["capability_pass_rate"]),
                    _interval(cells[cell]["capability_pass_rate_wilson_95"]),
                    _pct(cells[cell]["operational_pass_rate"]),
                    _pct(cells[cell]["infra_missing_rate"]),
                )
                for cell in DIRECT_CELLS
            ),
        )
    )

    lines.extend(["", "## Repeat stability", ""])
    lines.extend(
        _markdown_table(
            [
                "Cell",
                "Tasks ≥2 evaluable",
                "Mixed tasks",
                "Mixed-task rate",
                "Mean within-task sample variance",
                "Median task pass fraction",
            ],
            (
                (
                    CELL_LABELS[cell],
                    stats["tasks_with_2plus_evaluable_repeats"],
                    stats["tasks_with_mixed_pass_fail"],
                    _pct(stats["mixed_task_rate"]),
                    _num(stats["mean_within_task_repeat_variance"], 3),
                    _pct(stats["median_task_pass_fraction"]),
                )
                for cell, stats in analysis["repeat_variability"].items()
            ),
        )
    )
    lines.extend(
        [
            "",
            "Only capability-evaluable repeats enter these stability metrics. Individual task results have at most five repeats and should not be overinterpreted.",
            "",
            "## Infrastructure and recovery",
            "",
        ]
    )
    lines.extend(
        _markdown_table(
            [
                "Cell",
                "Primary infra",
                "Primary infra rate",
                "Recovery attempted",
                "Recovered evaluable",
                "Recovery resolution rate",
                "Final infra",
            ],
            (
                (
                    CELL_LABELS[cell],
                    stats["primary_failed_infra"],
                    _pct(stats["primary_infra_rate"]),
                    stats["recovery_attempted"],
                    stats["recovery_capability_pass"] + stats["recovery_capability_fail"],
                    _pct(stats["recovery_resolution_rate"]),
                    stats["final_infra_missing"],
                )
                for cell, stats in analysis["infra_and_recovery"].items()
            ),
        )
    )
    lines.extend(
        [
            "",
            "A recovered `capability_fail` is an infrastructure resolution because it produced evaluable capability evidence; it is not a capability success.",
            "",
            "## Latency",
            "",
        ]
    )
    lines.extend(
        _markdown_table(
            [
                "Cell",
                "Primary n",
                "Median ms",
                "P25 ms",
                "P75 ms",
                "P90 ms",
                "Mean ms",
                "Recovery n",
                "Recovery median ms",
                "Recovery P90 ms",
            ],
            (
                (
                    CELL_LABELS[cell],
                    stats["latency_observed_n"],
                    _num(stats["median_ms"], 0),
                    _num(stats["p25_ms"], 0),
                    _num(stats["p75_ms"], 0),
                    _num(stats["p90_ms"], 0),
                    _num(stats["mean_ms"], 0),
                    stats["recovery_latency_observed_n"],
                    _num(stats["recovery_median_ms"], 0),
                    _num(stats["recovery_p90_ms"], 0),
                )
                for cell, stats in analysis["latency"].items()
            ),
        )
    )
    lines.extend(
        [
            "",
            "Missing latency is not zero-filled. Recovery latency is separate; no total effective latency is fabricated.",
            "",
            "## Usage",
            "",
            "### Primary usage",
            "",
        ]
    )
    lines.extend(
        _markdown_table(
            [
                "Cell",
                "Observed n",
                "Median input",
                "Median output",
                "Mean input",
                "Mean output",
                "Total input",
                "Total output",
            ],
            (
                (
                    CELL_LABELS[cell],
                    stats["primary"]["primary_usage_observed_n"],
                    _num(stats["primary"]["median_input_tokens"], 0),
                    _num(stats["primary"]["median_output_tokens"], 0),
                    _num(stats["primary"]["mean_input_tokens"], 1),
                    _num(stats["primary"]["mean_output_tokens"], 1),
                    _num(stats["primary"]["total_input_tokens"], 0),
                    _num(stats["primary"]["total_output_tokens"], 0),
                )
                for cell, stats in analysis["usage"].items()
            ),
        )
    )
    lines.extend(["", "### Recovery usage", ""])
    lines.extend(
        _markdown_table(
            ["Cell", "Observed n", "Median input", "Median output", "Total input", "Total output"],
            (
                (
                    CELL_LABELS[cell],
                    stats["recovery"]["recovery_usage_observed_n"],
                    _num(stats["recovery"]["median_input_tokens"], 0),
                    _num(stats["recovery"]["median_output_tokens"], 0),
                    _num(stats["recovery"]["total_input_tokens"], 0),
                    _num(stats["recovery"]["total_output_tokens"], 0),
                )
                for cell, stats in analysis["usage"].items()
            ),
        )
    )
    lines.extend(
        [
            "",
            "Missing usage is not added as zero. Cached-token semantics may differ between Harness and Direct routes; comparisons of cached, cache-write, and reasoning tokens are descriptive.",
            "",
            "## Cost and efficiency",
            "",
            "All figures use **HarnessLab conservative estimated accounting**, not invoice or billing truth. No USD↔CNY conversion is performed.",
            "",
        ]
    )
    lines.extend(
        _markdown_table(
            [
                "Cell",
                "Currency",
                "Total",
                "Mean/slot",
                "Mean/evaluable",
                "Cost/capability pass",
                "Cost/operational pass",
            ],
            (
                (
                    CELL_LABELS[cell],
                    stats["native_currency"],
                    _money(
                        stats["total_estimated_usd"]
                        if stats["native_currency"] == "USD"
                        else stats["total_estimated_cny"]
                    ),
                    _money(stats["mean_estimated_cost_per_logical_slot"]),
                    _money(stats["mean_estimated_cost_per_capability_evaluable_result"]),
                    _money(stats["estimated_cost_per_capability_pass"]),
                    _money(stats["cost_per_operational_pass"]),
                )
                for cell, stats in analysis["cost"]["by_cell"].items()
            ),
        )
    )
    lines.extend(
        [
            "",
            f"Manifest-reconciled totals: USD {_money(analysis['cost']['totals']['total_estimated_usd'])}; CNY {_money(analysis['cost']['totals']['total_estimated_cny'])}.",
            "",
            "Paired cost deltas per logical slot:",
            "",
        ]
    )
    lines.extend(
        _markdown_table(
            [
                "Comparison",
                "Currency",
                "Baseline mean/slot",
                "Variant mean/slot",
                "Delta/slot",
                "Multiplier",
                "Operational pass-rate delta",
            ],
            (
                (
                    COMPARISON_LABELS[key],
                    comparison["cost_and_efficiency"]["currency"],
                    _money(
                        comparison["cost_and_efficiency"]["baseline_mean_cost_per_logical_slot"]
                    ),
                    _money(comparison["cost_and_efficiency"]["variant_mean_cost_per_logical_slot"]),
                    _money(comparison["cost_and_efficiency"]["cost_delta_per_logical_slot"]),
                    _num(comparison["cost_and_efficiency"]["cost_multiplier"], 3) + "×",
                    _pct(comparison["operational"]["delta"]),
                )
                for key, comparison in comparisons.items()
            ),
        )
    )
    lines.extend(["", "## Cancelled rows", ""])
    lines.append(
        "The two frozen cancellations are excluded from capability estimands and retained as non-passes in operational estimands. They were not rerun."
    )
    lines.append("")
    lines.extend(
        _markdown_table(
            ["Cell", "Task", "Repeat", "Slot ID"],
            (
                (row["cell_id"], row["task_id"], row["repeat_index"], f"`{row['slot_id']}`")
                for row in analysis["cancelled_rows"]
            ),
        )
    )
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "- Capability comparisons condition on both paired rows being evaluable and can therefore differ from operational comparisons that retain infrastructure failures and cancellations.",
            "- Task-cluster bootstrap intervals resample the 18 task clusters with replacement and use equal task weighting; they do not treat 90 rows as independent IID observations.",
            "- Exact McNemar p-values are secondary evidence and are not the sole significance criterion.",
            "- Direct-route comparisons confound model identity with provider/route and are descriptive, not clean causal model effects.",
            "- Each task has five repeats at most; task-level heterogeneity is descriptive and individual tasks should not be overinterpreted.",
            "- Primary and recovery latency/usage coverage is incomplete in some cells; missing values are not zero-filled.",
            "- Harness and Direct cached-token semantics may differ. Frozen conservative cost estimates are not billing truth.",
            "",
            "## Mechanical conclusions",
            "",
        ]
    )
    for key, comparison in comparisons.items():
        capability = comparison["capability"]
        operational = comparison["operational"]
        lines.append(
            f"- {COMPARISON_LABELS[key]}: observed capability delta {_pct(capability['delta'])} (95% task-cluster bootstrap CI {_interval(capability['cluster_bootstrap_ci'])}); operational delta {_pct(operational['delta'])} (95% task-cluster bootstrap CI {_interval(operational['cluster_bootstrap_ci'])})."
        )
    lines.append("")
    return "\n".join(lines)


def _build_analysis(
    rows: list[dict[str, Any]], manifest: dict[str, Any], validation: dict[str, Any]
) -> dict[str, Any]:
    rows_by_cell = {cell: [row for row in rows if row["cell_id"] == cell] for cell in CELL_ORDER}
    rows_by_cell_key = {
        cell: {(row["task_id"], row["repeat_index"]): row for row in cell_rows}
        for cell, cell_rows in rows_by_cell.items()
    }
    all_tasks = sorted({row["task_id"] for row in rows})
    cell_summaries = {cell: _cell_summary(rows_by_cell[cell]) for cell in CELL_ORDER}
    paired = {
        key: _paired_comparison(rows_by_cell_key, baseline, variant, all_tasks)
        for key, (baseline, variant) in COMPARISONS.items()
    }
    for key, comparison in paired.items():
        _require(comparison["capability"]["complete_pairs"] <= ROWS_PER_CELL, f"{key} pairs > 90")
        _require(
            comparison["operational"]["pair_count"] == ROWS_PER_CELL,
            f"{key} operational pairs != 90",
        )
        _require(
            comparison["capability"]["cluster_bootstrap_ci"]["seed"] == BOOTSTRAP_SEED,
            f"{key} capability bootstrap seed mismatch",
        )
        _require(
            comparison["operational"]["cluster_bootstrap_ci"]["seed"] == BOOTSTRAP_SEED,
            f"{key} operational bootstrap seed mismatch",
        )
    costs = {cell: _cell_cost(rows_by_cell[cell]) for cell in CELL_ORDER}
    return {
        "metadata": {
            "experiment_id": EXPERIMENT_ID,
            "dataset": DATASET_RELATIVE,
            "manifest": MANIFEST_RELATIVE,
            "dataset_freeze_commit": DATASET_FREEZE_COMMIT,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "bootstrap_replicates": BOOTSTRAP_REPLICATES,
            "bootstrap_method": "task_cluster_percentile",
            "capability_effect_task_weighting": "equal_task",
            "deterministic": True,
        },
        "dataset_validation": validation,
        "cell_summaries": cell_summaries,
        "paired_comparisons": paired,
        "direct_route_comparison": {
            "limitation": "Direct-model comparisons are model/provider-route comparisons. Model identity and provider/route are confounded, so they must not be presented as clean causal model effects.",
            "cells": {cell: cell_summaries[cell] for cell in DIRECT_CELLS},
        },
        "repeat_variability": {
            cell: _repeat_variability(rows_by_cell[cell]) for cell in CELL_ORDER
        },
        "latency": {cell: _latency_stats(rows_by_cell[cell]) for cell in CELL_ORDER},
        "usage": {
            cell: {
                "primary": _usage_stats(rows_by_cell[cell], "primary"),
                "recovery": _usage_stats(rows_by_cell[cell], "recovery"),
            }
            for cell in CELL_ORDER
        },
        "cost": {
            "accounting_basis": "HarnessLab conservative estimated accounting",
            "not_billing_truth": True,
            "currency_conversion_performed": False,
            "by_cell": costs,
            "totals": {
                "total_estimated_usd": _decimal_to_number(EXPECTED_USD),
                "total_estimated_cny": _decimal_to_number(EXPECTED_CNY),
                "manifest_total_estimated_usd": float(Decimal(manifest["conservative_usd"])),
                "manifest_total_estimated_cny": float(Decimal(manifest["conservative_cny"])),
                "reconciled": True,
            },
        },
        "infra_and_recovery": {cell: _infra_recovery(rows_by_cell[cell]) for cell in CELL_ORDER},
        "cancelled_rows": [
            {
                "cell_id": row["cell_id"],
                "task_id": row["task_id"],
                "repeat_index": row["repeat_index"],
                "slot_id": row["slot_id"],
                "effective_outcome": row["effective_outcome"],
                "capability_estimand_treatment": "excluded",
                "operational_estimand_treatment": "non_pass",
            }
            for row in rows
            if row["effective_outcome"] == "cancelled"
        ],
        "limitations": [
            "Capability and operational estimands use different denominators and must not be conflated.",
            "Capability paired effects exclude pairs unless both rows are capability-evaluable.",
            "Task-cluster percentile bootstrap resamples 18 tasks and uses equal task weighting.",
            "Exact McNemar tests are secondary evidence, not the sole significance rule.",
            "Direct model/provider-route comparisons are confounded and descriptive rather than clean causal model effects.",
            "Individual task estimates have at most five repeats and should not be overinterpreted.",
            "Missing latency and usage values are not zero-filled; recovery is reported separately.",
            "Harness and Direct cached-token semantics may differ.",
            "Frozen conservative cost estimates are HarnessLab accounting, not billing truth; currencies are not converted.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze the frozen Formal Matrix dataset deterministically."
    )
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--dataset", type=Path, default=Path(DATASET_RELATIVE))
    parser.add_argument("--manifest", type=Path, default=Path(MANIFEST_RELATIVE))
    parser.add_argument("--output-json", type=Path, default=Path(OUTPUT_JSON_RELATIVE))
    parser.add_argument("--output-markdown", type=Path, default=Path(OUTPUT_MARKDOWN_RELATIVE))
    args = parser.parse_args()

    root = args.repository_root.resolve()
    dataset_path = args.dataset if args.dataset.is_absolute() else root / args.dataset
    manifest_path = args.manifest if args.manifest.is_absolute() else root / args.manifest
    output_json = args.output_json if args.output_json.is_absolute() else root / args.output_json
    output_markdown = (
        args.output_markdown if args.output_markdown.is_absolute() else root / args.output_markdown
    )

    rows = _load_jsonl(dataset_path)
    manifest = _load_json_object(manifest_path)
    dataset_sha256 = _sha256_file(dataset_path)
    validation = _validate_dataset(rows, manifest, dataset_sha256)
    analysis = _build_analysis(rows, manifest, validation)
    _require(len(analysis["cancelled_rows"]) == 2, "cancelled row detail mismatch")

    json_text = json.dumps(analysis, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    markdown_text = _render_markdown(analysis)
    output_json.write_text(json_text, encoding="utf-8")
    output_markdown.write_text(markdown_text, encoding="utf-8")
    print("VALIDATION=PASS")
    print(f"DATASET_SHA256={dataset_sha256}")
    print(f"ANALYSIS_JSON={output_json}")
    print(f"ANALYSIS_MARKDOWN={output_markdown}")


if __name__ == "__main__":
    main()
