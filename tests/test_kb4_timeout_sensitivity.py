from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from scripts.analyze_kb4_timeout_sensitivity import (
    OUTPUT,
    assess_pair,
    attempt_projection,
    markdown,
    pair_views,
    timeout_fact,
    validate,
)
from scripts.audit_gpt_relay_attribution_sources import GPT_CELLS

from harnesslab.release.badcases import POST_FREEZE_SOURCE_UPDATES

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def artifact() -> dict[str, Any]:
    value: dict[str, Any] = json.loads((ROOT / (OUTPUT + ".json")).read_text())
    return value


def test_frozen_artifact_reconciles_and_reproduces_without_external_evidence(
    artifact: dict[str, Any],
) -> None:
    validate(artifact)
    assert markdown(artifact) == (ROOT / (OUTPUT + ".md")).read_text()
    for reference, digest in artifact["provenance"]["sources_sha256"].items():
        if reference.startswith("evidence:"):
            continue
        historical = POST_FREEZE_SOURCE_UPDATES.get(reference)
        if historical is not None:
            assert digest == historical
        else:
            assert "sha256:" + hashlib.sha256((ROOT / reference).read_bytes()).hexdigest() == digest
    assert artifact["campaign_reconciliation"]["effective"]["capability_results"] == 599
    assert artifact["external_execution"] == {"provider": 0, "harness": 0, "judge": 0, "matrix": 0}


def test_timeout_and_effective_counts_are_separate(artifact: dict[str, Any]) -> None:
    for cell, primary_timeouts, primary_budget, recovery_budget, capability_n in zip(
        GPT_CELLS, (0, 4, 1), (0, 17, 27), (0, 1, 6), (86, 86, 85), strict=True
    ):
        group = artifact["by_cell"][cell]
        assert group["primary"]["timeout_infrastructure"] == primary_timeouts
        assert group["primary"]["execution_budget_capability_failures"] == primary_budget
        assert group["recovery"]["timeout_infrastructure"] == 0
        assert group["recovery"]["execution_budget_capability_failures"] == recovery_budget
        assert group["effective"]["capability_n"] == capability_n
    unresolved = {
        (s["cell_id"], s["task_id"], s["repeat_index"])
        for s in artifact["slots"]
        if s["timeout_affected_unresolved"]
    }
    assert unresolved == {
        (GPT_CELLS[1], "core-java-deduplicate", 4),
        (GPT_CELLS[2], "micro-python-clamp", 2),
    }
    for s in artifact["slots"]:
        if s["timeout_affected_unresolved"]:
            assert s["primary"]["source_outcome"] == "harness_error:timeout"
            assert s["recovery"]["source_outcome"] == "harness_error:protocol_error"
            assert s["effective_outcome"] == "infra_failure"
            assert s["infra_recovery_exhausted"]
    assert sum(s["unobserved_extra_primary_attempts"] for s in artifact["slots"]) == 4
    assert sum(not s["primary"]["manifest_available"] for s in artifact["slots"]) == 1


def test_pair_coverage_does_not_upgrade_comparability(artifact: dict[str, Any]) -> None:
    direct = artifact["pairs"]["gpt56-relay-direct-vs-codex"]["summary"]
    ablation = artifact["pairs"]["codex-gpt56-reasoning-effort"]["summary"]
    assert (
        direct["primary"]["capability_complete"],
        ablation["primary"]["capability_complete"],
    ) == (
        61,
        60,
    )
    assert (
        direct["effective"]["capability_complete"],
        ablation["effective"]["capability_complete"],
    ) == (
        82,
        83,
    )
    assert direct["timeout_affected_unavailable_pairs"] == 1
    assert ablation["timeout_affected_unavailable_pairs"] == 2
    assert direct["other_unavailable_pairs"] == 7
    assert ablation["other_unavailable_pairs"] == 5
    assert direct["effective"]["complete_pair_comparability"] == {
        "COMPARABLE": 0,
        "PARTIALLY_COMPARABLE": 82,
        "NOT_COMPARABLE": 0,
    }
    assert ablation["effective"]["complete_pair_comparability"] == {
        "COMPARABLE": 42,
        "PARTIALLY_COMPARABLE": 0,
        "NOT_COMPARABLE": 41,
    }
    assert not direct["effective"]["formal_eligible"]
    assert not ablation["effective"]["formal_eligible"]
    assert pair_views(list(reversed(artifact["slots"]))) == artifact["pairs"]


def test_pair_join_rejects_duplicate_repeat_and_identity_drift(artifact: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="duplicate cell/task/repeat"):
        pair_views([*artifact["slots"], artifact["slots"][0]])
    slots = copy.deepcopy(artifact["slots"])
    slots[0]["repeat_index"] = 99
    with pytest.raises(ValueError, match="unmatched keys"):
        pair_views(slots)
    slots = copy.deepcopy(artifact["slots"])
    slots[0]["paired_slot_identity"] = "unrelated"
    with pytest.raises(ValueError, match="pair drift"):
        pair_views(slots)


@pytest.mark.parametrize(
    ("manifest", "source", "expected"),
    [
        (None, "control_identity_mismatch", "NOT_VERIFIED"),
        ({"timed_out": True}, "harness_error:protocol_error", "OBSERVED"),
        ({"provider_failure": "timeout"}, "provider_error", "OBSERVED"),
        ({"provider_error": {"category": "timeout"}}, "provider_error", "OBSERVED"),
        ({"timed_out": True}, "harness_error:execution_budget_exhausted", "OBSERVED"),
        (
            {"duration_ms": 180001, "provider_failure": "http_error"},
            "provider_error",
            "NOT_OBSERVED",
        ),
        ({"timed_out": False}, "harness_error:protocol_error", "NOT_OBSERVED"),
    ],
)
def test_timeout_is_observed_not_inferred_from_duration(
    manifest: dict[str, Any] | None,
    source: str,
    expected: str,
) -> None:
    assert timeout_fact(manifest, source) == expected


def test_projection_preserves_timeout_phase_and_never_converts_budget_failure() -> None:
    row = {
        "cell_id": GPT_CELLS[0],
        "primary_source_outcome": "provider_error",
        "primary_normalized_outcome": "infra_failure",
        "primary_duration_ms": None,
    }
    raw = {
        "provider_failure": "timeout",
        "generation_settings": {"request_timeout_seconds": 180},
        "provider_error": {
            "latency_ms": 180100,
            "timeout_phase": "read",
            "read_timeout_stage": "waiting_for_response_headers",
        },
    }
    projected = attempt_projection(row, "primary", raw)
    assert projected["timeout_infrastructure"]
    assert projected["timeout_phase"] == "read"
    assert projected["read_timeout_stage"] == "waiting_for_response_headers"
    assert projected["duration_ms"] == 180100
    assert projected["boundary_delta_ms"] == 100
    row.update(
        cell_id=GPT_CELLS[1],
        primary_source_outcome="harness_error:execution_budget_exhausted",
        primary_normalized_outcome="capability_fail",
    )
    projected = attempt_projection(row, "primary", {"timed_out": True})
    assert projected["execution_budget_capability_failure"]
    assert not projected["timeout_infrastructure"]
    assert projected["duration_ms"] is None
    assert projected["boundary_delta_ms"] is None


def test_capability_recovery_and_changed_denominator_fail_validation(
    artifact: dict[str, Any],
) -> None:
    changed = copy.deepcopy(artifact)
    changed["by_cell"][GPT_CELLS[0]]["effective"]["capability_n"] = 90
    with pytest.raises(ValueError, match="cell calculation drift"):
        validate(changed)
    changed = copy.deepcopy(artifact)
    changed["slots"][0]["effective_outcome"] = "capability_fail"
    with pytest.raises(ValueError, match=r"cell calculation drift|effective drift"):
        validate(changed)


def test_route_drift_and_missing_evidence_remain_not_comparable(artifact: dict[str, Any]) -> None:
    slots = artifact["slots"]
    pair = next(
        r
        for r in artifact["pairs"]["codex-gpt56-reasoning-effort"]["records"]
        if r["effective"]["formal_comparable"]
    )
    members = []
    for side in ("left", "right"):
        slot = next(s for s in slots if s["slot_id"] == pair[f"{side}_slot_id"])
        members.append(copy.deepcopy(slot[slot["effective_source"]]))
    assert assess_pair(members[0], members[1], "CONTROLLED_ABLATION")["status"] == "COMPARABLE"
    members[1]["comparison_facts"]["provider_route"] = "different-route"
    assert assess_pair(members[0], members[1], "CONTROLLED_ABLATION")["status"] == "NOT_COMPARABLE"
    members[1]["comparison_facts"] = None
    assert not assess_pair(members[0], members[1], "CONTROLLED_ABLATION")["eligible"]
