from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from scripts.analyze_kb4_discordant_pairs import (
    FROZEN_INPUTS,
    OUTPUT,
    candidates_for,
    classify_failure,
    discordance_kind,
    markdown,
    trace_projection,
    validate,
)
from scripts.analyze_kb4_timeout_sensitivity import OUTPUT as TIMEOUT_OUTPUT
from scripts.analyze_kb4_timeout_sensitivity import PAIR_DEFINITIONS

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def artifact() -> dict[str, Any]:
    value: dict[str, Any] = json.loads((ROOT / (OUTPUT + ".json")).read_text())
    return value


def test_artifact_schema_and_markdown_are_reproducible(artifact: dict[str, Any]) -> None:
    validate(artifact)
    assert markdown(artifact) == (ROOT / (OUTPUT + ".md")).read_text()
    assert artifact["status"] == "READY_FOR_BADCASE_FREEZE"
    assert artifact["external_execution"] == {"provider": 0, "harness": 0, "judge": 0, "matrix": 0}
    assert not artifact["new_external_execution_required"]
    assert not artifact["canonical_badcases_modified"]


def test_source_hashes_and_accepted_inputs_are_unchanged(artifact: dict[str, Any]) -> None:
    from scripts.analyze_formal_matrix_final import _sha256_file

    for reference, entry in artifact["provenance"]["sources"].items():
        if not reference.startswith("evidence:"):
            assert _sha256_file(ROOT / reference) == entry["sha256"]
    for reference, digest in FROZEN_INPUTS.items():
        assert _sha256_file(ROOT / reference) == digest


def test_discordances_recomputed_independently_from_frozen_dataset(
    artifact: dict[str, Any],
) -> None:
    rows = [
        json.loads(line)
        for line in (ROOT / "release/core-real-matrix-v6-analysis-dataset.jsonl")
        .read_text()
        .splitlines()
    ]
    index = {(r["cell_id"], r["task_id"], r["repeat_index"]): r for r in rows}
    capability = {"capability_pass", "capability_fail"}
    for name, left, right, _ in PAIR_DEFINITIONS:
        expected = set()
        for (cell, task, repeat), a in index.items():
            if cell != left:
                continue
            b = index[right, task, repeat]
            if (
                a["effective_outcome"] in capability
                and b["effective_outcome"] in capability
                and a["effective_outcome"] != b["effective_outcome"]
            ):
                expected.add((a["slot_id"], b["slot_id"], task, repeat))
        actual = {
            (p["left_slot_id"], p["right_slot_id"], p["task_id"], p["repeat_index"])
            for p in artifact["comparisons"][name]["discordant_pairs"]
        }
        assert actual == expected


def test_every_frozen_pair_and_attempt_view_is_retained(artifact: dict[str, Any]) -> None:
    frozen = json.loads((ROOT / (TIMEOUT_OUTPUT + ".json")).read_text())
    slots = {s["slot_id"]: s for s in frozen["slots"]}
    for name, p in frozen["pairs"].items():
        ledger = artifact["comparisons"][name]
        records = ledger["discordant_pairs"] + ledger["concordant_pairs"] + ledger["excluded_pairs"]
        by_id = {r["paired_slot_identity"]: r for r in records}
        assert len(by_id) == 90
        for original in p["records"]:
            found = by_id[original["paired_slot_identity"]]
            for key, value in original.items():
                assert found[key] == value
    for key, member in artifact["members"].items():
        for field in ("primary", "recovery", "effective_source", "effective_outcome"):
            assert member[field] == slots[key][field]


def test_comparison_counts_and_directions_remain_separate(artifact: dict[str, Any]) -> None:
    direct = artifact["summaries"]["gpt56-relay-direct-vs-codex"]
    ablation = artifact["summaries"]["codex-gpt56-reasoning-effort"]
    assert (
        direct["effective_complete_pairs"],
        direct["discordant_pairs"],
        direct["concordant_pairs"],
    ) == (82, 18, 64)
    assert direct["direction"] == {"LEFT_PASS_RIGHT_FAIL": 17, "LEFT_FAIL_RIGHT_PASS": 1}
    assert direct["failure_taxonomy"] == {"Timeout": 16, "Test Failure": 2}
    assert (
        ablation["effective_complete_pairs"],
        ablation["discordant_pairs"],
        ablation["concordant_pairs"],
    ) == (83, 34, 49)
    assert ablation["direction"] == {"LEFT_PASS_RIGHT_FAIL": 25, "LEFT_FAIL_RIGHT_PASS": 9}
    assert ablation["failure_taxonomy"] == {"Timeout": 32, "Test Failure": 1, "No Modification": 1}
    assert direct["by_comparability"]["PARTIALLY_COMPARABLE"]["discordant_pairs"] == 18
    assert ablation["by_comparability"]["COMPARABLE"]["direction"] == {"LEFT_PASS_RIGHT_FAIL": 2}
    assert ablation["by_comparability"]["NOT_COMPARABLE"]["direction"] == {
        "LEFT_PASS_RIGHT_FAIL": 23,
        "LEFT_FAIL_RIGHT_PASS": 9,
    }
    assert (direct["excluded_missing_pairs"], ablation["excluded_missing_pairs"]) == (8, 7)
    assert (
        direct["timeout_affected_missing_pairs"],
        ablation["timeout_affected_missing_pairs"],
    ) == (1, 2)
    assert not direct["formal_eligible"] and not ablation["formal_eligible"]
    assert artifact["reconciliation"]["unique_inspected_slots"] == 95
    assert artifact["reconciliation"]["unique_failed_slots"] == 44


@pytest.mark.parametrize("missing", ["infra_failure", "cancelled"])
def test_missing_pairs_are_never_capability_discordances(missing: str) -> None:
    for a, b in [(missing, "capability_pass"), ("capability_fail", missing)]:
        assert (
            discordance_kind({"effective": {"left_outcome": a, "right_outcome": b}})
            == "MISSING_CAPABILITY"
        )


def test_verifier_precedence_and_budget_failure_scope(artifact: dict[str, Any]) -> None:
    for member in artifact["members"].values():
        if member["source_outcome"] == "harness_error:execution_budget_exhausted":
            assert classify_failure(member) == "Timeout"
            assert member["effective_outcome"] == "capability_fail"
            assert member["failure_scope"] == "CAPABILITY"
            assert member["verifier"]["status"] == "NOT_RUN"
        elif (
            member["source_outcome"] == "verified_fail"
            and member["task_id"] == "core-python-deduplicate"
        ):
            assert classify_failure(member) == "Test Failure"
            assert member["verifier"]["failed_checks"] == ["empty-key-rejected"]
            assert member["verifier"]["report"]["score"] == 0.8
            assert member["verifier"]["stdout_independently_digest_verified"]
    high = next(
        m
        for m in artifact["members"].values()
        if m["cell_id"] == "harness-codex-gpt56-high"
        and m["task_id"] == "core-python-deduplicate"
        and m["repeat_index"] == 2
    )
    assert high["trace"]["failed_command_events"] == [7]
    assert (
        classify_failure(high) == "Test Failure"
    )  # Ancillary git exit 128 is not the root category.


def test_candidates_exclude_incomplete_bundles_and_do_not_freeze_three(
    artifact: dict[str, Any],
) -> None:
    candidates = artifact["badcase_candidates"]
    assert len(candidates) == 4
    assert [c["rank"] for c in candidates] == [1, 2, 3, None]
    assert sum(c["eligible_for_final_freeze_review"] for c in candidates) == 3
    assert not any(c["selected_as_final_badcase"] for c in candidates)
    assert len({(c["failure_class"], tuple(c["verifier_failure_checks"])) for c in candidates}) == 2
    held = candidates[-1]
    assert held["cell_id"] == "harness-codex-gpt56-medium"
    assert held["repeat_index"] == 4
    assert held["suitability"] == "HOLD_INTEGRITY_MISMATCH"
    m = artifact["members"][held["slot_id"]]
    assert m["workspace"]["missing_manifest_inventory_paths"] == [
        "__pycache__/events.cpython-312.pyc"
    ]
    assert m["workspace"]["binding"]["status"] == "INTEGRITY_MISMATCH"
    assert m["verifier"]["binding"]["status"] == "INTEGRITY_MISMATCH"
    assert m["verifier"]["stdout_independently_digest_verified"]
    assert all(d["file_binding_verified"] for d in m["workspace"]["source_diffs"])
    reordered = dict(reversed(list(artifact["members"].items())))
    assert candidates_for(artifact["comparisons"], reordered) == candidates


def test_integrity_limits_do_not_rewrite_comparability(artifact: dict[str, Any]) -> None:
    assert artifact["reconciliation"]["workspace_digest_mismatches"] == 17
    assert artifact["reconciliation"]["verifier_tree_digest_mismatches"] == 9
    pairs = artifact["comparisons"]["codex-gpt56-reasoning-effort"]["discordant_pairs"]
    comparable = [p for p in pairs if p["comparability"]["status"] == "COMPARABLE"]
    assert {(p["task_id"], p["repeat_index"]) for p in comparable} == {
        ("core-java-settings-merge", 0),
        ("core-python-deduplicate", 2),
    }
    assert all(p["frozen_comparable_pair_level_evidence"] for p in comparable)
    assert all(not p["both_member_bundles_verified"] for p in comparable)
    assert all(not p["controlled_attribution_claimed"] for p in pairs)


def test_trace_projection_does_not_copy_private_text_or_claim_subcommand_success() -> None:
    trace = {
        "schema_version": 1,
        "events": [
            {
                "ordinal": 1,
                "type": "REASONING_PRESENT",
                "native_event_type": "item.completed",
                "text": "PRIVATE_REASONING_MARKER",
                "public_output": "DO_NOT_COPY_OUTPUT",
            },
            {
                "ordinal": 2,
                "type": "COMMAND_EXECUTION",
                "native_event_type": "item.completed",
                "command": "python -c 'assert False'; echo done",
                "status": "completed",
                "exit_code": 0,
            },
            {
                "ordinal": 3,
                "type": "COMMAND_EXECUTION",
                "native_event_type": "item.completed",
                "command": "ledger.record_success('', 'x')",
                "status": "completed",
                "exit_code": 0,
            },
        ],
    }
    value = trace_projection(trace)
    encoded = json.dumps(value)
    assert "PRIVATE_REASONING_MARKER" not in encoded
    assert "DO_NOT_COPY_OUTPUT" not in encoded
    assert "assert False" not in encoded
    assert value["events"][1]["exit_code"] == 0
    assert value["events"][2]["empty_key_acceptance_assertion_lines"] == []
    assert "Shell exit zero cannot prove" in value["command_detail_policy"]


def test_false_discordance_comparability_upgrade_and_causal_claim_fail(
    artifact: dict[str, Any],
) -> None:
    name = "gpt56-relay-direct-vs-codex"
    changed = copy.deepcopy(artifact)
    changed["comparisons"][name]["discordant_pairs"][0]["controlled_attribution_claimed"] = True
    with pytest.raises(ValueError, match="unsupported controlled attribution"):
        validate(changed)
    changed = copy.deepcopy(artifact)
    changed["comparisons"][name]["discordant_pairs"][0]["comparability"]["status"] = "COMPARABLE"
    with pytest.raises(ValueError, match=r"summary drift|comparability upgraded"):
        validate(changed)
    changed = copy.deepcopy(artifact)
    changed["comparisons"][name]["discordant_pairs"][0]["repeat_index"] = 99
    with pytest.raises(ValueError, match="pair member identity drift"):
        validate(changed)
    changed = copy.deepcopy(artifact)
    changed["badcase_candidates"][-1]["eligible_for_final_freeze_review"] = True
    with pytest.raises(ValueError, match="candidate drift"):
        validate(changed)
