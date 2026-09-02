from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from harnesslab.comparability.models import canonical_digest
from harnesslab.experiment.dispatch import DispatchProfile
from harnesslab.experiment.plan import MethodologyV2ExperimentPlan
from harnesslab.release.v6 import (
    V6_THROUGHPUT_R2_SELECTED_PROFILE_ID,
    selected_v6_dispatch_profile,
    v6_dispatch_profiles,
    validate_v6_matrix_authorization,
)
from harnesslab.release.v6_authorization import (
    V6_MATRIX_EXECUTION_PROFILE_IDENTITY,
    V6MatrixAuthorizationReceipt,
)

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION_RECEIPT = ROOT / "release/core-real-matrix-v6-integration-certification.json"


@dataclass(frozen=True)
class _MatrixPlanView:
    experiment_id: str
    digest: str
    run_slots: tuple[int, ...]


def _digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


@pytest.fixture(scope="module")
def v6_plan() -> MethodologyV2ExperimentPlan:
    control = json.loads(
        (ROOT / "release/core-real-matrix-v6-control.json").read_text(encoding="utf-8")
    )
    return cast(
        MethodologyV2ExperimentPlan,
        cast(
            object,
            _MatrixPlanView(
                experiment_id=control["experiment_id"],
                digest=control["plan_digest"],
                run_slots=tuple(range(control["subject_slot_count"])),
            ),
        ),
    )


def _matrix_authorization(
    plan: MethodologyV2ExperimentPlan,
) -> V6MatrixAuthorizationReceipt:
    raw: dict[str, Any] = {
        "schema_version": 1,
        "scope": "CORE_REAL_MATRIX_V6_630_SLOT_MATRIX",
        "authorization_id": "v6-integration-unit-test",
        "operator_reference": "operator:test",
        "authorized_at": datetime(2026, 8, 31, tzinfo=UTC),
        "experiment_id": plan.experiment_id,
        "plan_digest": plan.digest,
        "authorized_slot_count": 630,
        "execution_profile_identity": V6_MATRIX_EXECUTION_PROFILE_IDENTITY,
        "pricing_inputs_digest": "sha256:" + "a" * 64,
        "spend_authorized": True,
        "matrix_execution_authorized": True,
    }
    unsigned = V6MatrixAuthorizationReceipt.model_construct(
        **raw,
        authorization_digest="sha256:" + "0" * 64,
    )
    canonical = unsigned.model_dump(mode="json", exclude={"authorization_digest"})
    return V6MatrixAuthorizationReceipt.model_validate(
        {**canonical, "authorization_digest": _digest(canonical)}
    )


def test_profile_c_and_matching_matrix_authorization_pass_the_control_gate(
    v6_plan: MethodologyV2ExperimentPlan,
) -> None:
    selected = validate_v6_matrix_authorization(
        v6_plan,
        matrix_authorization=_matrix_authorization(v6_plan),
    )
    assert selected == selected_v6_dispatch_profile()
    assert selected.profile_id == V6_THROUGHPUT_R2_SELECTED_PROFILE_ID
    assert selected.digest == V6_MATRIX_EXECUTION_PROFILE_IDENTITY
    assert canonical_digest(selected.model_dump(mode="json")) == (
        "sha256:85117b2577f3456e0df573ed2467d19dee64bebca748e178bd92017dea6133b7"
    )


@pytest.mark.parametrize("profile", v6_dispatch_profiles())
def test_profile_a_or_b_cannot_be_used_for_formal_v6_matrix(
    profile: DispatchProfile,
    v6_plan: MethodologyV2ExperimentPlan,
) -> None:
    with pytest.raises(ValueError, match="final execution-profile binding mismatch"):
        validate_v6_matrix_authorization(
            v6_plan,
            matrix_authorization=_matrix_authorization(v6_plan),
            profile=profile,
        )

    raw = _matrix_authorization(v6_plan).model_dump(mode="json", exclude={"authorization_digest"})
    raw["execution_profile_identity"] = profile.digest
    with pytest.raises(ValidationError):
        V6MatrixAuthorizationReceipt.model_validate({**raw, "authorization_digest": _digest(raw)})


def test_missing_or_mismatched_matrix_authorization_is_rejected(
    v6_plan: MethodologyV2ExperimentPlan,
) -> None:
    with pytest.raises(ValueError, match="Matrix authorization"):
        validate_v6_matrix_authorization(
            v6_plan,
            matrix_authorization=cast(V6MatrixAuthorizationReceipt, None),
        )

    mismatched = _matrix_authorization(v6_plan).model_copy(
        update={"authorization_digest": "sha256:" + "b" * 64}
    )
    with pytest.raises(ValueError, match="Matrix authorization"):
        validate_v6_matrix_authorization(v6_plan, matrix_authorization=mismatched)


def test_integration_receipt_binds_both_lanes_and_frozen_controls() -> None:
    receipt = json.loads(INTEGRATION_RECEIPT.read_text(encoding="utf-8"))
    provenance = receipt["source_provenance"]
    assert provenance["lane_a"]["source_head"] == ("91b27068b670e7b4a7b3aab833d1f06ce0438e49")
    assert provenance["lane_b"]["source_head"] == ("b1496d522b0d192f51d0e47ae0d03dd1edd8975f")
    # The integration receipt binds the historical V6 and canary controls accepted
    # by the integration certification. A later pricing correction intentionally
    # changed both live control files without rewriting frozen provenance.
    assert receipt["v6_control"]["sha256"] == (
        "sha256:52318dd45e843611840a046f7f85670941281026d10f56b36fe0df421e69f42f"
    )
    assert receipt["canary_control"]["identity"] == (
        "sha256:c9749a9941061c460fde7c750e6d1b0d39b03d5291333dfae91003f8be7ea78a"
    )
    reference = ROOT / receipt["throughput_r2"]["reference"]
    assert receipt["throughput_r2"]["evidence_identity"] == (
        "sha256:" + hashlib.sha256(reference.read_bytes()).hexdigest()
    )
    assert receipt["throughput_r2"]["selected_profile_digest"] == (
        V6_MATRIX_EXECUTION_PROFILE_IDENTITY
    )
    assert receipt["matrix_authorization_boundary"] == {
        "required_receipt_type": "V6MatrixAuthorizationReceipt",
        "scope": "CORE_REAL_MATRIX_V6_630_SLOT_MATRIX",
        "authorized_slot_count": 630,
        "required_execution_profile_identity": V6_MATRIX_EXECUTION_PROFILE_IDENTITY,
        "profile_a_authorization": "REJECTED",
        "profile_b_authorization": "REJECTED",
        "missing_authorization": "REJECTED",
        "mismatched_authorization": "REJECTED",
        "canary_authorization_reusable_for_matrix": False,
    }


def test_integration_receipt_records_zero_real_calls_and_pending_hosted_ci() -> None:
    receipt = json.loads(INTEGRATION_RECEIPT.read_text(encoding="utf-8"))
    assert set(receipt["external_execution"].values()) == {0}
    assert receipt["ci_status"] == {
        "github_hosted_fast_ci": "PENDING_MINUTES",
        "github_hosted_full_release_ci": "PENDING_MINUTES",
        "self_hosted_ci": "NOT_CONFIGURED_YET",
    }
    canary = receipt["canary_control"]
    assert len(canary["call_ids"]) == canary["max_primary_calls"] == 3
    assert canary["retries"] == canary["semantic_retries"] == canary["substitutions"] == 0
    assert canary["throughput_profile_authorization_required"] is False
    assert canary["matrix_execution_authorized"] is False
    local = receipt["local_certification"]
    assert local["result"] == "PASS"
    assert all(local[f"gate_{letter}"] == "PASS" for letter in "abcdefghijk")
    assert local["keyless_qualifications"] == "PASS"
    assert local["fresh_setup"] == ("NOT_REPRODUCIBLE_ACTIONS_ONLY_PREFLIGHT_AND_RUNTIME_PASS")
    assert local["targeted_tests"] == local["quality_checks"] == "PASS"
