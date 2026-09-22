"""Read-only product projection of one digest-bound, historical comparison.

The curated sources are portable distribution files. No database, external evidence
root, model runtime, new statistic, or reconstruction of a past session is involved.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Final, Literal, cast

from pydantic import JsonValue

from harnesslab.analyst.models import StrictModel

REPORT = "release/kb4-final-attribution-report.json"
ANALYSIS = "release/core-real-matrix-v6-final-analysis.json"
CONTROL = "release/core-real-matrix-v6-control.json"
MANIFEST = "release/core-real-matrix-v6-analysis-dataset-manifest.json"
BADCASES = "release/badcases.json"
INSTRUCTION = "tasks/core-python-deduplicate/1.0.2/instruction.md"
PROBE = "tasks/core-python-deduplicate/1.0.2/verifier/subject_execution.py"
SOURCE_HASHES = {
    REPORT: "c896dd5b57899638577560046b316da03320a2ed5fec41f56807f05280815f04",
    ANALYSIS: "59b4e083c54d2d4a3bb1dfd2ad59129c45db81543f5cc5ae51de18a927590252",
    CONTROL: "9061656741e62d6683cb231a7d26c05d26c934f00f4c76a4dae3a8a2e4851e50",
    MANIFEST: "dad4043c059f0fdaf0b4985f091f16894671364c410e50a741e43cab1bc0f443",
    BADCASES: "8f2ac7d3ecc745ef0f9ba19204e9ec0ea0947b0c7388c4eee260205b34996082",
    INSTRUCTION: "4f64515977a9ee15c1c1ef9ce110fbc34ab71f41e6c9f0835dae46657f1cf3df",
    PROBE: "26e69bf429b428f9cce0f95dfe133bc8e3ac2b86749db8d30685649ae04c455c",
}
CELL_IDS = ("model-gpt56-relay-responses", "harness-codex-gpt56-medium")
COMPARISON_ID: Final = "gpt56-relay-direct-vs-codex"


class ComparisonSource(StrictModel):
    id: str
    path: str
    sha256: str
    pointer: str
    data: JsonValue


class ComparisonCell(StrictModel):
    cell_id: str
    requested_model: str
    provider: str
    harness: str
    reasoning_effort: str
    planned: int
    passed: int
    failed: int
    denominator: int
    infra_missing: int
    cancelled: int
    primary_passed: int
    recovery_attempts: int
    recovered_passes: int
    test_failures: int
    budget_failures: int
    output_failures: int
    primary_latency_ms: float | None
    latency_observations: int
    estimated_cost_usd: float | None
    explicit_cost_usd: None = None


class ComparisonFailure(StrictModel):
    case_id: str
    task_id: str
    task_version: str
    run_id: str
    cell_id: str
    input_expression: str
    verifier: dict[str, JsonValue]
    source_diffs: tuple[str, ...]
    root_cause: None = None
    trace_status: str
    both_member_bundles_verified: bool


class ComparisonExample(StrictModel):
    kind: Literal["historical_comparison"] = "historical_comparison"
    case_id: Literal["gpt56-relay-direct-vs-codex"] = COMPARISON_ID
    experiment_id: str
    recorded_at: str
    plan_digest: str
    dataset_digest: str
    task_count: int
    repeat_count: int
    request_timeout_seconds: int
    output_tokens_per_request: int
    plan_timeout_seconds: int
    cells: tuple[ComparisonCell, ComparisonCell]
    comparison: dict[str, JsonValue]
    failure: ComparisonFailure
    sources: tuple[ComparisonSource, ...]
    read_only: Literal[True] = True


def comparison_example(root: Path) -> ComparisonExample:
    # Resolve a single trusted root supplied by the distribution resolver. Missing or
    # changed files fail closed; no fallback to a different example or source tree.
    documents: dict[str, Any] = {}
    for name, digest in SOURCE_HASHES.items():
        raw = (root / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("Comparison source digest mismatch")
        documents[name] = json.loads(raw) if name.endswith(".json") else raw.decode("utf-8")

    report = documents[REPORT]
    analysis = documents[ANALYSIS]
    control = documents[CONTROL]
    manifest = documents[MANIFEST]
    badcase = documents[BADCASES]["slots"][2]
    frozen = badcase["frozen_evidence"]
    comparison = report["comparisons"][COMPARISON_ID]
    if (
        report["provenance"]["dataset_sha256"] != manifest["dataset_sha256"]
        or report["provenance"]["plan_digest"] != control["plan_digest"]
        or comparison["causal_interpretation_permitted"]
        or comparison["comparability"]["formal_eligible"]
        or badcase["root_cause"] is not None
        or badcase["cell_identity"] != f"cell:{CELL_IDS[0]}"
    ):
        raise ValueError("Comparison scope or authority mismatch")

    sources: list[ComparisonSource] = []

    def source(source_id: str, path: str, pointer: str = "") -> None:
        value = documents[path]
        for token in pointer.split("/")[1:]:
            value = value[int(token)] if isinstance(value, list) else value[token]
        sources.append(
            ComparisonSource(
                id=source_id,
                path=path,
                sha256=f"sha256:{SOURCE_HASHES[path]}",
                pointer=pointer,
                data=cast(JsonValue, value),
            )
        )

    cells = []
    configs = []
    for index, cell_id in enumerate(CELL_IDS):
        position, config = next(
            (i, cell) for i, cell in enumerate(control["cells"]) if cell["cell_id"] == cell_id
        )
        configs.append(config)
        data = report["core_results"][cell_id]
        counts = data["outcomes"]
        primary = data["attempts"]["primary"]
        recovery = data["attempts"]["recovery"]
        categories = [primary["source_outcomes"], recovery["source_outcomes"]]
        timing = analysis["latency"][cell_id]
        costs = analysis["cost"]["by_cell"][cell_id]
        tests = sum(c.get("verified_fail", 0) for c in categories)
        budgets = sum(c.get("harness_error:execution_budget_exhausted", 0) for c in categories)
        outputs = sum(c.get("subject_output_error", 0) for c in categories)
        if (
            counts != analysis["cell_summaries"][cell_id]
            or counts["capability_fail"] != tests + budgets + outputs
            or counts["logical_slots"]
            != counts["capability_evaluable"] + counts["infra_missing"] + counts["cancelled"]
        ):
            raise ValueError("Comparison denominators do not reconcile")
        cells.append(
            ComparisonCell(
                cell_id=cell_id,
                requested_model=config["requested_model"],
                provider=config["provider_id"],
                harness=config["harness_id"],
                reasoning_effort=config["reasoning_effort"],
                planned=counts["logical_slots"],
                passed=counts["capability_pass"],
                failed=counts["capability_fail"],
                denominator=counts["capability_evaluable"],
                infra_missing=counts["infra_missing"],
                cancelled=counts["cancelled"],
                primary_passed=primary["outcomes"]["capability_pass"],
                recovery_attempts=recovery["attempts"],
                recovered_passes=recovery["outcomes"]["capability_pass"],
                test_failures=tests,
                budget_failures=budgets,
                output_failures=outputs,
                primary_latency_ms=timing["median_ms"],
                latency_observations=timing["latency_observed_n"],
                estimated_cost_usd=costs["total_estimated_usd"],
            )
        )
        source(f"config-{index}", CONTROL, f"/cells/{position}")
        source(f"result-{index}", REPORT, f"/core_results/{cell_id}")
        source(f"timing-{index}", ANALYSIS, f"/latency/{cell_id}")
        source(f"cost-{index}", ANALYSIS, f"/cost/by_cell/{cell_id}")

    input_expression = 'record_success("", "x")'
    if (
        input_expression not in documents[PROBE]
        or configs[0]["requested_model"] != configs[1]["requested_model"]
    ):
        raise ValueError("Comparison input or requested model mismatch")
    source("scope", MANIFEST)
    source("comparison", REPORT, f"/comparisons/{COMPARISON_ID}")
    source("budget", REPORT, "/timeout_sensitivity/execution_scopes")
    source("failure", BADCASES, "/slots/2")
    source("instruction", INSTRUCTION)
    source("probe", PROBE)
    return ComparisonExample(
        experiment_id=report["provenance"]["experiment_id"],
        recorded_at=report["provenance"]["as_of"],
        plan_digest=control["plan_digest"],
        dataset_digest=manifest["dataset_sha256"],
        task_count=manifest["task_count"],
        repeat_count=manifest["repeat_count"],
        request_timeout_seconds=configs[0]["request_timeout_seconds"],
        output_tokens_per_request=configs[0]["max_output_tokens"],
        plan_timeout_seconds=report["timeout_sensitivity"]["execution_scopes"]["max_wall_time"][
            "value"
        ],
        cells=(cells[0], cells[1]),
        comparison=comparison,
        failure=ComparisonFailure(
            case_id=badcase["slot_id"],
            task_id="core-python-deduplicate",
            task_version="1.0.2",
            run_id=badcase["run_identity"],
            cell_id=CELL_IDS[0],
            input_expression=input_expression,
            verifier=frozen["verifier_report"],
            source_diffs=tuple(frozen["source_diffs"]),
            trace_status=frozen["trace_status"],
            both_member_bundles_verified=frozen["comparisons"][0]["both_member_bundles_verified"],
        ),
        sources=tuple(sources),
    )
