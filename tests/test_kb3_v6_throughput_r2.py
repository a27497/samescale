from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from harnesslab.experiment.dispatch import (
    BlockDispatchCoordinator,
    DispatchProfile,
    SlotResourceClass,
    slot_resource_class,
)
from harnesslab.experiment.plan import MethodologyV2ExperimentPlan
from harnesslab.release.throughput_qualification import (
    CancellationProbe,
    ProfileQualification,
    QualificationTrial,
    select_qualified_profile,
)
from harnesslab.release.v6 import (
    V6_THROUGHPUT_R2_SELECTED_PROFILE_ID,
    build_v6_plan,
    selected_v6_dispatch_profile,
    v6_throughput_r2_profiles,
)

ROOT = Path(__file__).resolve().parents[1]
R2_EVIDENCE = ROOT / "release/core-real-matrix-v6-throughput-r2.json"


@pytest.fixture(scope="session")
def v6_plan() -> MethodologyV2ExperimentPlan:
    return build_v6_plan(ROOT, {})


def _profile_result(
    profile: DispatchProfile,
    wall_time_seconds: float,
    *,
    hard_checks_passed: bool = True,
) -> ProfileQualification:
    trial = QualificationTrial.model_construct(
        trial_id="constructed-selection-test",
        profile_id=profile.profile_id,
        profile_digest=profile.digest,
        wall_time_seconds=wall_time_seconds,
        dispatch_sequence_digest="sha256:" + "1" * 64,
        dispatch_sequence=(),
        completion_count=630,
        safety=cast(Any, None),
        host_telemetry=cast(Any, None),
        hard_checks_passed=hard_checks_passed,
    )
    return ProfileQualification(
        profile=profile.model_dump(mode="json"),
        profile_digest=profile.digest,
        trials=(trial, trial),
        median_wall_time_seconds=wall_time_seconds,
        logical_dispatch_reproduced=True,
        hard_checks_passed=hard_checks_passed,
    )


def test_r2_profiles_change_only_bounded_concurrency() -> None:
    a, b, c = v6_throughput_r2_profiles()
    assert (a.global_concurrency, a.max_harness_concurrency) == (4, 2)
    assert (b.global_concurrency, b.max_harness_concurrency) == (6, 2)
    assert (c.global_concurrency, c.max_harness_concurrency) == (6, 3)
    assert all(profile.max_direct_concurrency == 4 for profile in (a, b, c))
    assert all(max(profile.provider_concurrency.values()) == 2 for profile in (a, b, c))
    assert all(profile.max_judge_concurrency == 1 for profile in (a, b, c))
    assert selected_v6_dispatch_profile() == c
    assert c.profile_id == V6_THROUGHPUT_R2_SELECTED_PROFILE_ID


def test_frozen_r2_evidence_selects_the_production_default() -> None:
    evidence = json.loads(R2_EVIDENCE.read_text(encoding="utf-8"))
    qualification = evidence["qualification"]
    selected = selected_v6_dispatch_profile()
    assert qualification["selection"]["selected_profile_id"] == selected.profile_id
    assert qualification["selection"]["selected_profile_digest"] == selected.digest
    assert qualification["selection"]["c_improvement_over_b_percent"] >= 10
    assert qualification["selection"]["c_improvement_over_a_percent"] >= 10
    assert qualification["external_call_counts"] == {
        "real_provider_calls": 0,
        "real_harness_provider_calls": 0,
        "real_judge_calls": 0,
    }
    assert all(
        profile["logical_dispatch_reproduced"] and profile["hard_checks_passed"]
        for profile in qualification["profiles"]
    )
    dispatch_digests: set[str] = set()
    for profile in qualification["profiles"]:
        assert len(profile["trials"]) == 2
        for trial in profile["trials"]:
            dispatch_digests.add(trial["dispatch_sequence_digest"])
            assert trial["completion_count"] == 630
            assert len(trial["dispatch_sequence"]) == 630
            safety = trial["safety"]
            assert safety["terminal_slots"] == 630
            assert safety["resume_preserved_terminal_slots"] == 70
            assert safety["attempts_above_one"] == 0
            assert safety["heartbeat_count"] > 0
            for field in (
                "duplicate_claims",
                "scheduling_violations",
                "provider_cap_violations",
                "lane_cap_violations",
                "workspace_collisions",
                "artifact_collisions",
                "container_identity_collisions",
                "lease_losses",
                "cleanup_failures",
                "security_failures",
            ):
                assert safety[field] == 0
            assert safety["resource_pressure_violations"] == []
            telemetry = trial["host_telemetry"]
            assert telemetry["sample_count"] > 0
            assert telemetry["collection_errors"] == []
    assert dispatch_digests == {
        "sha256:bb73846c13f7cfaedcb639a01e08dc6fe8f62fce480ac81889d0ba67e0a4e3ac"
    }
    assert qualification["cancellation_probe"]["passed"] is True
    assert evidence["accepted_v6_control_sha256"] == (
        "sha256:52318dd45e843611840a046f7f85670941281026d10f56b36fe0df421e69f42f"
    )
    assert evidence["frozen_v5_incident_sha256"] == (
        "sha256:02f1b49092b2c592231e132fdcc97135f876d6694f513f2bc0b49897ad8e8cac"
    )


def test_dispatch_sequence_is_independent_of_completion_order(
    v6_plan: MethodologyV2ExperimentPlan,
) -> None:
    expected = tuple(slot.slot_id for slot in v6_plan.run_slots)
    observed: list[tuple[str, ...]] = []
    for newest_first in (False, True):
        coordinator = BlockDispatchCoordinator(v6_plan, v6_throughput_r2_profiles()[2])
        active: dict[str, SlotResourceClass] = {}
        while len(coordinator.dispatch_sequence) < len(expected):
            slot = coordinator.next_slot(active)
            if slot is None:
                selected = next(reversed(active)) if newest_first else next(iter(active))
                active.pop(selected)
                continue
            active[slot.slot_id] = slot_resource_class(slot)
        observed.append(coordinator.dispatch_sequence)
    assert observed == [expected, expected]


def test_selection_keeps_a_when_higher_profiles_miss_ten_percent() -> None:
    a, b, c = v6_throughput_r2_profiles()
    selection = select_qualified_profile(
        (
            _profile_result(a, 100.0),
            _profile_result(b, 95.0),
            _profile_result(c, 86.0),
        )
    )
    assert selection.selected_profile_id == a.profile_id
    assert selection.b_improvement_over_a_percent == 5.0
    assert selection.c_improvement_over_b_percent < 10.0


def test_selection_accepts_h3_only_when_it_clears_both_thresholds() -> None:
    a, b, c = v6_throughput_r2_profiles()
    selection = select_qualified_profile(
        (
            _profile_result(a, 100.0),
            _profile_result(b, 98.0),
            _profile_result(c, 80.0),
        )
    )
    assert selection.selected_profile_id == c.profile_id
    assert selection.c_improvement_over_b_percent >= 10.0
    assert selection.c_improvement_over_a_percent >= 10.0


def test_frozen_local_docker_cancellation_probe_cleaned_everything() -> None:
    evidence = json.loads(R2_EVIDENCE.read_text(encoding="utf-8"))
    result = CancellationProbe.model_validate(evidence["qualification"]["cancellation_probe"])
    assert result.passed
    assert result.status == "cancelled"
    assert result.cancellation_observed
    assert result.heartbeat_count > 0
    assert result.lease_losses == 0
    assert result.cleanup_failures == 0
    assert result.remaining_containers == 0
    assert result.workspace_cleaned


def test_profile_result_helper_does_not_leak_into_runtime_models() -> None:
    # Keep mypy aware that model_construct is deliberately test-only and unvalidated.
    value: Any = _profile_result(v6_throughput_r2_profiles()[0], 1.0)
    assert value.profile["profile_id"] == "V6_PROFILE_A_C4"
