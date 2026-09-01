from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / "judge_suites/core-calibration-score-v2-draft"
PLAN = ROOT / "release/core-real-judge-v6-methodology-v2-plan.json"


def test_v2_score_rubric_has_all_five_explicit_anchors() -> None:
    rubric = yaml.safe_load((DRAFT / "rubric.yaml").read_text())
    assert set(rubric["anchors"]) == {1, 2, 3, 4, 5}
    assert len(set(rubric["anchors"].values())) == 5


def test_v2_annotation_batch_is_blind_and_has_twelve_cases() -> None:
    batch = yaml.safe_load((DRAFT / "annotation-batch.yaml").read_text())
    assert len(batch["cases"]) == 12
    assert batch["blinding"] == {
        "legacy_gold_visible": False,
        "j1_outputs_visible": False,
        "j3r1_outputs_visible": False,
    }
    forbidden = {"expected", "gold", "legacy_gold", "j1_output", "j3r1_output"}
    for case in batch["cases"]:
        assert forbidden.isdisjoint(case)


def test_v2_protocol_blocks_thresholds_until_human_annotation() -> None:
    protocol = yaml.safe_load((DRAFT / "annotation-protocol.yaml").read_text())
    plan = json.loads(PLAN.read_text())
    assert protocol["annotator_count"] == 3
    assert protocol["qualification_gate"]["minimum_score_cases"] == 12
    assert protocol["qualification_gate"]["required_independent_ratings_per_case"] == 3
    assert protocol["threshold_policy"]["status"] == "UNSET_PENDING_HUMAN_DISAGREEMENT"
    assert plan["threshold_freeze"]["status"] == "BLOCKED_PENDING_HUMAN_ANNOTATIONS"
    assert plan["execution_controls"] == {
        "real_provider_calls": 0,
        "real_judge_calls": 0,
        "real_matrix_calls": 0,
        "formal_matrix_authorization": "NOT_AUTHORIZED",
    }
