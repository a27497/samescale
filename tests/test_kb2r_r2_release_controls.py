from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from harnesslab.egress import EGRESS_PROXY_IMAGE
from harnesslab.harness_lane.profile import CODEX_IMAGE
from harnesslab.multi_harness.profile import CLAUDE_IMAGE, DEEPSEEK_IMAGE
from harnesslab.release.contracts import load_real_evidence_plan, load_real_smoke_plan
from harnesslab.release.matrix import MatrixControlPlane
from harnesslab.release.r2 import (
    R2CanaryPolicy,
    V4ToV5ReadinessEquivalence,
    load_r2_canary_policy,
    load_readiness_equivalence,
    validate_r2_policy,
)
from harnesslab.release.smoke import EXPECTED_V5_CALL_IDS, RuntimeIdentities, SmokeControlPlane
from harnesslab.sandbox.models import ImageIdentity

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "release"

PROTECTED_SHA256 = {
    "release/core-real-evidence-plan-v4.json": (
        "5de29e88ff9482a34111e6639eb6a139045d812466614a5ceaeb6e796c76f90d"
    ),
    "release/core-real-smoke-plan-v4.json": (
        "cc3a8d9fd4df7e47d8f55df0dd7d7b922e2b972307f9ac11f86e9648a0df69ec"
    ),
    "release/kb2r-authorization-dossier.json": (
        "1c5ca81022d2a389637f9718254e746e81733b56819bef2d87bd62015eaf33e8"
    ),
    "release/kb2r-r1-continuation-policy.json": (
        "3239df4b635f9f96b55e390a59ddb9a6d4975d3a267de23eb7081904a0e1ea92"
    ),
    "release/kb2r-r1-authorization-dossier.json": (
        "e0b95fe11ddd6b5b524fe14afdb4180e719e34066a807f29ce72374b642954cd"
    ),
}


def _runtime() -> RuntimeIdentities:
    return RuntimeIdentities(
        codex_image=ImageIdentity(reference=CODEX_IMAGE, image_id="sha256:" + "1" * 64),
        claude_image=ImageIdentity(reference=CLAUDE_IMAGE, image_id="sha256:" + "2" * 64),
        deepseek_image=ImageIdentity(reference=DEEPSEEK_IMAGE, image_id="sha256:" + "3" * 64),
        egress_proxy_image=ImageIdentity(
            reference=EGRESS_PROXY_IMAGE, image_id="sha256:" + "4" * 64
        ),
        deepseek_config_digest="sha256:" + "5" * 64,
    )


def test_v5_replaces_only_cell7_and_preserves_core_shape_pair_and_ablation() -> None:
    v4 = load_real_evidence_plan(RELEASE / "core-real-evidence-plan-v4.json")
    v5 = load_real_evidence_plan(RELEASE / "core-real-evidence-plan-v5.json")
    smoke = load_real_smoke_plan(RELEASE / "core-real-smoke-plan-v5.json")

    assert v5.plan_id == "core-real-evidence-v5"
    assert v5.supersedes_plan_id == v4.plan_id
    assert v5.experiment_id == "core-real-matrix-v5"
    assert len(v5.cells) == 7
    assert sum(cell.lane == "M" for cell in v5.cells) == 4
    assert sum(cell.lane == "H" for cell in v5.cells) == 3
    assert sum(int(cell.planned_runs) for cell in v5.cells) == 630
    assert v5.preflight.direct_model_runs == 360
    assert v5.preflight.deepseek_runs == 0
    assert v5.judge.planned_calls == 63
    assert v5.ablation.expected_paired_observations == 90
    assert "reasoning_effort" in v5.paired_lane.required_frozen_controls
    assert [cell.model_dump() for cell in v5.cells[:6]] == [
        cell.model_dump() for cell in v4.cells[:6]
    ]
    assert v5.cells[6].cell_id == "model-deepseek-v4flash-chat"
    assert v5.cells[6].runtime == "direct-model"
    assert tuple(call.call_id for call in smoke.calls) == EXPECTED_V5_CALL_IDS
    assert smoke.release_plan_digest == v5.digest


def test_v5_smoke_and_matrix_control_planes_are_exact_and_keyless() -> None:
    smoke = SmokeControlPlane.load(ROOT, plan_version="v5")
    matrix = MatrixControlPlane.load(ROOT, plan_version="v5")
    plan = matrix.build_plan(_runtime())

    assert tuple(binding.call.call_id for binding in smoke.bindings) == EXPECTED_V5_CALL_IDS
    assert [binding.runner_identity for binding in smoke.bindings] == [
        "DirectModelRunner",
        "DirectModelRunner",
        "DirectModelRunner",
        "CodexHarnessRunner",
        "CodexHarnessRunner",
        "MultiHarnessRunner",
        "DirectModelRunner",
        "JudgeRunner",
    ]
    assert plan.experiment_id == "core-real-matrix-v5"
    assert len(plan.run_slots) == 630
    assert plan.ablations[0].intent.value == "CONTROLLED_ABLATION"
    assert plan.repeat_count == 5
    assert len(plan.tasks) == 18


def test_v4_to_v5_readiness_equivalence_is_exact_six_and_fail_closed() -> None:
    equivalence = load_readiness_equivalence(RELEASE / "kb2r-r2-readiness-equivalence.json")
    assert tuple(entry.call_id for entry in equivalence.entries) == EXPECTED_V5_CALL_IDS[:6]
    assert all(entry.source == entry.target for entry in equivalence.entries)
    assert equivalence.scope == "TECHNICAL_READINESS_ONLY"
    assert equivalence.does_not_satisfy == (
        "V5_MATRIX_EVIDENCE",
        "FORMAL_STATISTICS",
        "K_B3_EVIDENCE",
        "K_C_EVIDENCE",
    )

    first = equivalence.entries[0]
    drifted = first.model_copy(
        update={"target": first.target.model_copy(update={"timeout_seconds": 179})}
    )
    with pytest.raises(ValidationError, match="not exactly equivalent"):
        V4ToV5ReadinessEquivalence.model_validate(
            {
                **equivalence.model_dump(mode="json"),
                "entries": [
                    drifted.model_dump(mode="json"),
                    *(entry.model_dump(mode="json") for entry in equivalence.entries[1:]),
                ],
            }
        )

    with pytest.raises(ValidationError, match="exact unchanged Calls 1-6"):
        V4ToV5ReadinessEquivalence.model_validate(
            {**equivalence.model_dump(mode="json"), "entries": equivalence.entries[:5]}
        )


def test_r2_canary_policy_model_forbids_substitution_retry_and_excess_launches() -> None:
    equivalence = load_readiness_equivalence(RELEASE / "kb2r-r2-readiness-equivalence.json")
    plan = load_real_evidence_plan(RELEASE / "core-real-evidence-plan-v5.json")
    smoke = load_real_smoke_plan(RELEASE / "core-real-smoke-plan-v5.json")
    policy = R2CanaryPolicy(
        policy_id="kb2r-r2-v5-canary",
        base_commit="290d99c26425dcf1b60bfc711a93640edd37645e",
        frozen_implementation_commit="1" * 40,
        release_plan_reference="release/core-real-evidence-plan-v5.json",
        release_plan_digest=plan.digest,
        smoke_plan_reference="release/core-real-smoke-plan-v5.json",
        smoke_plan_digest=smoke.digest,
        readiness_equivalence_reference="release/kb2r-r2-readiness-equivalence.json",
        readiness_equivalence_digest=equivalence.digest,
        cell7_call_id="smoke-7-model-deepseek-v4flash-chat",
        cell7_profile_id="model-deepseek-v4flash-chat",
        judge_call_id="smoke-8-judge-glm52-opencode-go",
        judge_profile_id="judge-glm52-opencode-go-chat",
        protected_file_sha256={"release/core-real-evidence-plan-v4.json": "sha256:" + "2" * 64},
    )
    assert policy.max_new_subject_launches == 1
    assert policy.max_new_judge_launches == 1
    assert policy.max_new_external_launches == 2
    assert policy.recovery_attempts_allowed == 0
    assert policy.substitution_after_freeze_allowed is False

    raw = policy.model_dump(mode="json")
    raw["cell7_profile_id"] = "substituted-profile"
    with pytest.raises(ValidationError):
        R2CanaryPolicy.model_validate(raw)


def test_frozen_r2_policy_binds_v5_equivalence_and_only_two_new_launches() -> None:
    policy = load_r2_canary_policy(RELEASE / "kb2r-r2-canary-policy.json")
    equivalence = load_readiness_equivalence(RELEASE / "kb2r-r2-readiness-equivalence.json")
    control = SmokeControlPlane.load(ROOT, plan_version="v5")
    validate_r2_policy(ROOT, control, policy, equivalence)

    assert policy.cell7_call_id == EXPECTED_V5_CALL_IDS[6]
    assert policy.judge_call_id == EXPECTED_V5_CALL_IDS[7]
    assert policy.max_new_subject_launches == 1
    assert policy.max_new_judge_launches == 1
    assert policy.max_new_external_launches == 2
    assert policy.recovery_attempts_allowed == 0
    assert policy.substitution_after_freeze_allowed is False


def test_r2_artifacts_are_portable_and_do_not_require_ignored_evidence() -> None:
    paths = (
        RELEASE / "core-real-evidence-plan-v5.json",
        RELEASE / "core-real-smoke-plan-v5.json",
        RELEASE / "kb2r-r2-core-qualification.json",
        RELEASE / "kb2r-r2-canary-policy.json",
        RELEASE / "kb2r-r2-closure-dossier.json",
        RELEASE / "kb2r-r2-provenance-portability.json",
        RELEASE / "kb2r-r2-readiness-equivalence.json",
    )
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert "/home/" not in text
        assert "/Users/" not in text
        json.loads(text)
    portability = json.loads(
        (RELEASE / "kb2r-r2-provenance-portability.json").read_text(encoding="utf-8")
    )
    assert portability["mutates_r1_policy"] is False
    assert portability["tracked_absolute_operator_paths"] == 0


def test_deepseek_and_judge_keyless_decisions_are_frozen_without_score_selection() -> None:
    qualification = json.loads(
        (RELEASE / "kb2r-r2-core-qualification.json").read_text(encoding="utf-8")
    )
    deepseek = qualification["deepseek_forensics"]
    judge = qualification["judge_audit"]
    assert deepseek["real_calls"] == 0
    assert deepseek["core_qualification"] == "PROVIDER_BOOTSTRAP_CONTRACT_INCOMPATIBLE"
    assert deepseek["disposition"] == "UNQUALIFIED_FOR_CORE_V5"
    assert deepseek["keyless_reproduction"]["result"] == "PASS"
    assert [candidate["rank"] for candidate in qualification["cell7_candidates"]] == [1, 2]
    assert qualification["cell7_candidates"][0]["selected"] is True
    assert judge["real_calls"] == 0
    assert judge["redesign_required"] is False
    assert judge["historical_not_bare_json_interpretation"].startswith("DIAGNOSTIC_")


def test_r2_closure_is_ready_for_separate_authorization_but_not_spend_or_execution() -> None:
    dossier = json.loads((RELEASE / "kb2r-r2-closure-dossier.json").read_text(encoding="utf-8"))
    assert dossier["authorization_decision"] == "READY_FOR_FULL_MATRIX_AUTHORIZATION"
    assert dossier["full_matrix_spend_authorized"] is False
    assert dossier["full_matrix_executed"] is False
    assert len(dossier["core_cells"]) == 7
    assert dossier["core_cells"][6]["capability_outcome"] == (
        "FAIL_SUBJECT_OUTPUT_ERROR_MAX_TOKENS"
    )
    assert dossier["core_cells"][6]["infrastructure_outcome"] == "SUCCESS"
    assert dossier["judge_canary"]["outcome"] == "JUDGED"
    assert dossier["judge_canary"]["observed_model"] == "glm-5.2"
    assert dossier["r2_execution"]["total_new_external_launches"] == 2
    assert dossier["r2_execution"]["recovery_attempts"] == 0
    assert dossier["r2_execution"]["reran_calls_1_to_6"] is False
    assert dossier["methodology"]["paired_lane_reasoning_effort_policy"] == "HARD_CONTROL"
    assert dossier["methodology"]["formal_ablation_paired_observations_required"] == 90
    assert dossier["full_matrix_preflight"]["cost_status"] == "UNKNOWN_NOT_ZERO"
    assert dossier["full_matrix_preflight"]["blocking_reason_codes"] == [
        "FULL_MATRIX_PRICING_UNKNOWN",
        "FULL_MATRIX_BUDGET_NOT_AUTHORIZED",
    ]


def test_v4_and_r1_historical_evidence_remains_byte_identical() -> None:
    for reference, expected in PROTECTED_SHA256.items():
        assert hashlib.sha256((ROOT / reference).read_bytes()).hexdigest() == expected
