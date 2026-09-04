from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from harnesslab.evaluation_suites import (
    CandidateRole,
    ConfigurationBlockSummary,
    DiscriminativePreregistration,
    DiscriminativeQualificationEvidence,
    ExecutionLane,
    PairBlockSummary,
    QualificationBlock,
    QualificationDirection,
    QualificationFailureCode,
    StressDimensionName,
    StressEvidenceStatus,
    build_discriminative_preregistration,
    build_m8a_preregistration_bundle,
    evaluate_discriminative_qualification,
    load_m8a_preregistration_bundle,
)
from harnesslab.tasks.splits import SplitRole

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "evaluation_suites/m8a/keyless-candidate-preregistration-v1.json"
FROZEN_EVIDENCE = (
    ROOT / "release/core-corpus-v4.json",
    ROOT / "release/tier-b-qualification-v1.json",
    ROOT / "release/core-real-matrix-v6-control.json",
    ROOT / "release/core-real-matrix-v6-final-analysis.json",
)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _configuration_summary(
    configuration_id: str, *, passes: int, eligible: int = 3, planned: int = 3
) -> ConfigurationBlockSummary:
    return ConfigurationBlockSummary(
        configuration_id=configuration_id,
        planned=planned,
        capability_eligible=eligible,
        capability_passes=passes,
        capability_failures=eligible - passes,
    )


def _qualifying_evidence(
    policy: DiscriminativePreregistration, *, reverse: bool = False
) -> DiscriminativeQualificationEvidence:
    target = policy.preregistered_pairs[0]
    first_passes = {
        target.left_configuration_id: 1 if reverse else 3,
        target.right_configuration_id: 3 if reverse else 1,
    }
    stable_passes = {
        target.left_configuration_id: 1 if reverse else 2,
        target.right_configuration_id: 2 if reverse else 1,
    }
    configuration_ids = tuple(item.configuration_id for item in policy.selected_panel)
    first_configurations = tuple(
        _configuration_summary(
            configuration_id,
            passes=first_passes.get(configuration_id, 2),
        )
        for configuration_id in configuration_ids
    )
    stable_configurations = tuple(
        _configuration_summary(
            configuration_id,
            passes=stable_passes.get(configuration_id, 2),
        )
        for configuration_id in configuration_ids
    )
    first_pairs = tuple(
        PairBlockSummary(
            pair_id=pair.pair_id,
            comparable_pairs=3,
            discordant_pairs=2 if pair == target else 0,
            all_qualifying_evidence_comparable=True,
        )
        for pair in policy.preregistered_pairs
    )
    stable_pairs = tuple(
        PairBlockSummary(
            pair_id=pair.pair_id,
            comparable_pairs=3,
            discordant_pairs=1 if pair == target else 0,
            all_qualifying_evidence_comparable=True,
        )
        for pair in policy.preregistered_pairs
    )
    return DiscriminativeQualificationEvidence(
        task=build_m8a_preregistration_bundle(ROOT).inventory.candidates[0].task,
        population=SplitRole.DEVELOPMENT,
        panel_configuration_ids=configuration_ids,
        first_block=QualificationBlock(
            block_id="first-n3",
            repetitions_per_configuration=3,
            independently_scheduled=True,
            configurations=first_configurations,
            pairs=first_pairs,
        ),
        stability_block=QualificationBlock(
            block_id="stability-n3",
            repetitions_per_configuration=3,
            independently_scheduled=True,
            configurations=stable_configurations,
            pairs=stable_pairs,
        ),
        total_scheduled_blocks=2,
    )


def test_inventory_and_checked_artifact_are_exact_and_deterministic() -> None:
    first = build_m8a_preregistration_bundle(ROOT)
    second = build_m8a_preregistration_bundle(ROOT)
    checked = load_m8a_preregistration_bundle(ARTIFACT)

    assert first == second == checked
    assert first.inventory.core_count == 18
    assert first.inventory.tier_b_count == 3
    assert len(first.inventory.candidates) == 21
    assert sum(item.role is CandidateRole.CORE for item in first.inventory.candidates) == 18
    assert sum(item.role is CandidateRole.TIER_B for item in first.inventory.candidates) == 3
    assert {
        item.task.task_version
        for item in first.inventory.candidates
        if item.role is CandidateRole.CORE
    } == {"1.0.2"}
    assert {
        item.task.task_version
        for item in first.inventory.candidates
        if item.role is CandidateRole.TIER_B
    } == {"1.0.0"}
    assert all(item.population is SplitRole.DEVELOPMENT for item in first.inventory.candidates)
    assert all(not item.holdout_eligible for item in first.inventory.candidates)


def test_core_cannot_become_holdout_and_tier_b_cannot_auto_promote_to_stress() -> None:
    bundle = build_m8a_preregistration_bundle(ROOT)
    core = next(item for item in bundle.inventory.candidates if item.role is CandidateRole.CORE)
    core_payload = core.model_dump(mode="json")
    core_payload["holdout_eligible"] = True
    with pytest.raises(ValidationError):
        type(core).model_validate(core_payload)

    stress = bundle.stress_audit.candidates[0]
    stress_payload = stress.model_dump(mode="json")
    stress_payload["stress_member_eligible"] = True
    with pytest.raises(ValidationError):
        type(stress).model_validate(stress_payload)


def test_panel_is_registry_bound_product_coverage_not_historical_outcomes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_read_text = Path.read_text

    def reject_historical_reads(path: Path, *args: object, **kwargs: object) -> str:
        if path.name.startswith("core-real-matrix-v6"):
            raise AssertionError("panel selection read historical outcomes")
        return original_read_text(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", reject_historical_reads)
    policy = build_discriminative_preregistration(ROOT)

    assert policy.selection_uses_historical_outcomes is False
    assert policy.live_provider_availability_claimed is False
    assert policy.direction_neutral is True
    assert policy.named_winner is None
    assert policy.empirical_execution_authorization_required is True
    assert len(policy.selected_panel) == 6
    assert len({item.model_family for item in policy.selected_panel}) == 3
    assert {item.lane for item in policy.selected_panel} == {
        ExecutionLane.DIRECT,
        ExecutionLane.HARNESS,
    }
    assert len(policy.preregistered_pairs) == 3
    assert all(item.live_provider_availability == "NOT_ASSESSED" for item in policy.selected_panel)
    assert all(item.configuration_identity for item in policy.selected_panel)
    panel = {item.configuration_id: item for item in policy.selected_panel}
    for pair in policy.preregistered_pairs:
        left = panel[pair.left_configuration_id]
        right = panel[pair.right_configuration_id]
        assert left.provider_profile_id == right.provider_profile_id
        assert left.model_id == right.model_id
        assert {left.lane, right.lane} == {ExecutionLane.DIRECT, ExecutionLane.HARNESS}


def test_direction_neutral_policy_accepts_either_qualifying_direction() -> None:
    policy = build_discriminative_preregistration(ROOT)
    left_higher = evaluate_discriminative_qualification(_qualifying_evidence(policy), policy)
    right_higher = evaluate_discriminative_qualification(
        _qualifying_evidence(policy, reverse=True), policy
    )

    assert left_higher.status == right_higher.status == "QUALIFIES"
    assert left_higher.direction is QualificationDirection.LEFT_HIGHER
    assert right_higher.direction is QualificationDirection.RIGHT_HIGHER


def test_result_identity_uses_the_pair_that_reproduces_in_stability() -> None:
    policy = build_discriminative_preregistration(ROOT)
    baseline = _qualifying_evidence(policy)
    assert baseline.stability_block is not None
    first_pair, stable_pair = policy.preregistered_pairs[:2]

    first_passes = {
        first_pair.left_configuration_id: 3,
        first_pair.right_configuration_id: 1,
        stable_pair.left_configuration_id: 3,
        stable_pair.right_configuration_id: 1,
    }
    stability_passes = {
        first_pair.left_configuration_id: 1,
        first_pair.right_configuration_id: 2,
        stable_pair.left_configuration_id: 2,
        stable_pair.right_configuration_id: 1,
    }
    first_block = baseline.first_block.model_copy(
        update={
            "configurations": tuple(
                _configuration_summary(
                    item.configuration_id,
                    passes=first_passes.get(item.configuration_id, 2),
                )
                for item in baseline.first_block.configurations
            ),
            "pairs": tuple(
                item.model_copy(
                    update={
                        "discordant_pairs": 2
                        if item.pair_id in {first_pair.pair_id, stable_pair.pair_id}
                        else 0
                    }
                )
                for item in baseline.first_block.pairs
            ),
        }
    )
    stability_block = baseline.stability_block.model_copy(
        update={
            "configurations": tuple(
                _configuration_summary(
                    item.configuration_id,
                    passes=stability_passes.get(item.configuration_id, 2),
                )
                for item in baseline.stability_block.configurations
            ),
            "pairs": tuple(
                item.model_copy(
                    update={
                        "discordant_pairs": 1
                        if item.pair_id in {first_pair.pair_id, stable_pair.pair_id}
                        else 0
                    }
                )
                for item in baseline.stability_block.pairs
            ),
        }
    )
    result = evaluate_discriminative_qualification(
        baseline.model_copy(
            update={"first_block": first_block, "stability_block": stability_block}
        ),
        policy,
    )

    assert result.status == "QUALIFIES"
    assert result.qualifying_pair_id == stable_pair.pair_id


def test_first_block_n3_coverage_comparability_discordance_and_gap_fail_closed() -> None:
    policy = build_discriminative_preregistration(ROOT)
    baseline = _qualifying_evidence(policy)

    short_block = baseline.first_block.model_copy(update={"repetitions_per_configuration": 2})
    result = evaluate_discriminative_qualification(
        baseline.model_copy(update={"first_block": short_block}), policy
    )
    assert QualificationFailureCode.FIRST_BLOCK_N3_REQUIRED in result.reason_codes

    configurations = list(baseline.first_block.configurations)
    configurations[0] = _configuration_summary(
        configurations[0].configuration_id, passes=2, eligible=2
    )
    low_coverage = baseline.first_block.model_copy(update={"configurations": tuple(configurations)})
    result = evaluate_discriminative_qualification(
        baseline.model_copy(update={"first_block": low_coverage}), policy
    )
    assert QualificationFailureCode.CAPABILITY_COVERAGE_BELOW_80_PERCENT in result.reason_codes

    pairs = list(baseline.first_block.pairs)
    pairs[0] = pairs[0].model_copy(update={"all_qualifying_evidence_comparable": False})
    noncomparable = baseline.first_block.model_copy(update={"pairs": tuple(pairs)})
    assert (
        evaluate_discriminative_qualification(
            baseline.model_copy(update={"first_block": noncomparable}), policy
        ).status
        == "REJECTED"
    )

    pairs[0] = baseline.first_block.pairs[0].model_copy(update={"discordant_pairs": 1})
    insufficient = baseline.first_block.model_copy(update={"pairs": tuple(pairs)})
    result = evaluate_discriminative_qualification(
        baseline.model_copy(update={"first_block": insufficient}), policy
    )
    assert QualificationFailureCode.INSUFFICIENT_FIRST_BLOCK_DISCORDANCE in result.reason_codes

    target = policy.preregistered_pairs[0]
    configurations = list(baseline.first_block.configurations)
    right_index = next(
        index
        for index, item in enumerate(configurations)
        if item.configuration_id == target.right_configuration_id
    )
    configurations[right_index] = _configuration_summary(target.right_configuration_id, passes=2)
    low_gap = baseline.first_block.model_copy(update={"configurations": tuple(configurations)})
    result = evaluate_discriminative_qualification(
        baseline.model_copy(update={"first_block": low_gap}), policy
    )
    assert QualificationFailureCode.ABSOLUTE_PASS_RATE_GAP_BELOW_TWO_THIRDS in result.reason_codes

    all_pass = baseline.first_block.model_copy(
        update={
            "configurations": tuple(
                _configuration_summary(item.configuration_id, passes=3)
                for item in baseline.first_block.configurations
            )
        }
    )
    result = evaluate_discriminative_qualification(
        baseline.model_copy(update={"first_block": all_pass}), policy
    )
    assert QualificationFailureCode.FLOOR_OR_CEILING in result.reason_codes

    result = evaluate_discriminative_qualification(
        baseline.model_copy(update={"rerun_until_success": True}), policy
    )
    assert QualificationFailureCode.RERUN_POLICY_VIOLATION in result.reason_codes


def test_stability_n3_independence_discordance_and_direction_fail_closed() -> None:
    policy = build_discriminative_preregistration(ROOT)
    baseline = _qualifying_evidence(policy)

    missing = evaluate_discriminative_qualification(
        baseline.model_copy(update={"stability_block": None}), policy
    )
    assert QualificationFailureCode.STABILITY_BLOCK_MISSING in missing.reason_codes

    assert baseline.stability_block is not None
    short_block = baseline.stability_block.model_copy(update={"repetitions_per_configuration": 2})
    result = evaluate_discriminative_qualification(
        baseline.model_copy(update={"stability_block": short_block}), policy
    )
    assert QualificationFailureCode.STABILITY_BLOCK_N3_REQUIRED in result.reason_codes

    dependent = baseline.stability_block.model_copy(update={"independently_scheduled": False})
    result = evaluate_discriminative_qualification(
        baseline.model_copy(update={"stability_block": dependent}), policy
    )
    assert QualificationFailureCode.STABILITY_BLOCK_NOT_INDEPENDENT in result.reason_codes

    no_discordance_pairs = tuple(
        item.model_copy(update={"discordant_pairs": 0}) for item in baseline.stability_block.pairs
    )
    no_discordance = baseline.stability_block.model_copy(update={"pairs": no_discordance_pairs})
    result = evaluate_discriminative_qualification(
        baseline.model_copy(update={"stability_block": no_discordance}), policy
    )
    assert QualificationFailureCode.STABILITY_DISCORDANCE_MISSING in result.reason_codes

    reversed_stability = _qualifying_evidence(policy, reverse=True).stability_block
    assert reversed_stability is not None
    result = evaluate_discriminative_qualification(
        baseline.model_copy(update={"stability_block": reversed_stability}), policy
    )
    assert QualificationFailureCode.STABILITY_DIRECTION_MISMATCH in result.reason_codes


def test_retrospective_and_stress_audit_are_explicitly_non_promoting() -> None:
    bundle = build_m8a_preregistration_bundle(ROOT)

    assert bundle.retrospective.status == "RETROSPECTIVE_NON_QUALIFYING"
    assert bundle.retrospective.current_memberships_created == 0
    assert all(
        result.status == "RETROSPECTIVE_NON_QUALIFYING" for result in bundle.retrospective.results
    )
    assert bundle.stress_audit.stress_suite_release_ready is False
    assert all(not item.stress_member_eligible for item in bundle.stress_audit.candidates)
    assert all(item.proven_dimension_count < 3 for item in bundle.stress_audit.candidates)
    assert all(not item.has_required_anchor_dimension for item in bundle.stress_audit.candidates)
    assert set(StressDimensionName) == {
        assessment.dimension
        for candidate in bundle.stress_audit.candidates
        for assessment in candidate.dimensions
    }
    assert any(
        assessment.status is StressEvidenceStatus.REQUIRES_EMPIRICAL_EVIDENCE
        for candidate in bundle.stress_audit.candidates
        for assessment in candidate.dimensions
    )
    assert bundle.gap_report.new_tasks_required is True
    assert bundle.gap_report.current_discriminative_memberships == 0
    assert bundle.gap_report.current_stress_memberships == 0

    audit_payload = bundle.stress_audit.model_dump(mode="json")
    audit_payload["stress_suite_release_ready"] = True
    with pytest.raises(ValidationError):
        type(bundle.stress_audit).model_validate(audit_payload)


def test_build_does_not_modify_frozen_evidence_and_records_zero_external_calls() -> None:
    before = {path: _hash(path) for path in FROZEN_EVIDENCE}
    bundle = build_m8a_preregistration_bundle(ROOT)
    after = {path: _hash(path) for path in FROZEN_EVIDENCE}

    assert before == after
    assert bundle.frozen_evidence_modified is False
    assert bundle.external_calls.model_dump() == {
        "provider": 0,
        "harness": 0,
        "judge": 0,
        "matrix": 0,
        "llm_explanation": 0,
    }
