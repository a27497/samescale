# ruff: noqa: E501 -- immutable historical evidence digests remain visually auditable.

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from harnesslab.comparability.models import ComparisonFacts, canonical_digest
from harnesslab.egress import EGRESS_PROXY_IMAGE
from harnesslab.experiment.evidence import validate_manifest_against_slot
from harnesslab.harness_lane.profile import CODEX_IMAGE
from harnesslab.multi_harness.profile import CLAUDE_IMAGE, DEEPSEEK_IMAGE
from harnesslab.release.contracts import load_release_evidence, load_technical_readiness
from harnesslab.release.diagnostic import execute_component_diagnostics
from harnesslab.release.judge import build_real_judge_plan
from harnesslab.release.matrix import (
    MATRIX_CANARY_TASK_ID,
    MATRIX_PILOT_TASK_IDS,
    MatrixControlPlane,
    MatrixControlPlaneError,
    execute_real_matrix_canary,
)
from harnesslab.release.smoke import (
    EXPECTED_CALL_IDS,
    RuntimeIdentities,
    SmokeCallResult,
    SmokeControlPlane,
    SmokeExecutionReceipt,
    SmokeExecutionStatus,
    SmokeFailureCategory,
)
from harnesslab.sandbox.models import ImageIdentity
from harnesslab.tasks.package import digest_tree

ROOT = Path(__file__).resolve().parents[1]

V2_RAW_SHA256 = {
    "release/core-real-evidence-plan.json": "27b71bcbdc45345e3f4f0d49d8233487e7b543b230352baec4823f82b83be351",
    "release/core-real-smoke-plan.json": "3b47638b2521a34871573f3b088319be7e8c775c817c1931e307b2a41e62d81f",
    "release/history/core-real-v2-attempt-1.json": "87a4be341c2c8f8c4d56c40f013ae0717e8cf5e37c2b4d562a1e89e5e49b3ad1",
    "release/history/core-real-v2-attempt-2.json": "c31d6d9973c8fa98d2a6d6ed70ebe247aa4456be2940741aaa654b60c0178165",
    "release/history/core-real-v2-attempt-3.json": "26e1d83bffd43687ae9fc0d9d1b9b4eb8126a2572a0074a63034e97be0bea0ba",
    "release/history/core-real-v2-attempt-4.json": "4ae22d2f8a645be77325e61d1c0dd90aa7772764e5386d1ff61d331c0cfb0c7b",
    "release/history/core-real-v2-attempt-5.json": "25e6c13384dddb8ac7ba96fd5bcf3fe99ed327dfab7fac417248a21066d2ceeb",
    "release/history/core-real-v2-attempt-6.json": "6f73faf2838f3c8081a096c8dbb192e16f275cc7faab91d9cccee25bab796bc5",
    "release/history/core-real-v2-attempt-7.json": "dc60d817d0f2da206a49bb8fbfd4ac3aedd4f6a926e6d921b7975fa43a2c4ac7",
    "release/history/core-real-v2-attempt-8.json": "4b4aab5f8f80558dd8ce34e6bf0b735ca961b42201705c066b839444d289e0ac",
    "release/history/core-real-v2-attempt-9.json": "3daccd24c04cee4dfd543a714ee6a9c2349e15b89b27682a5656efa428b3a92e",
    "release/history/core-real-v2-attempt-10.json": "f0ac51ed46004a32194e6474da0eb96d3b776086dee9dc2e34deafbdd7adbbec",
    "release/history/core-real-v2-attempt-11.json": "241cb9f50bc9067a563344d22a84a582debab0131cf5260810078ec157d93710",
    "release/history/core-real-v2-attempt-12.json": "cc9b368dccf341c0be5c7ff622dab6bca82b2b4cacb49be76f218682133a0099",
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


def _environment() -> dict[str, str]:
    return {
        "HARNESSLAB_GPT56_RELAY_BASE_URL": "https://matrix-test.invalid",
        "HARNESSLAB_GPT56_RELAY_API_KEY": "fake-relay-reference",
        "HARNESSLAB_OPENCODE_GO_API_KEY": "fake-opencode-reference",
        "DEEPSEEK_API_KEY": "fake-deepseek-reference",
    }


class _V3DiagnosticInvoker:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.calls: list[str] = []

    async def invoke(self, binding: object) -> SmokeCallResult:
        call = binding.frozen.call  # type: ignore[attr-defined]
        self.calls.append(call.call_id)
        artifact = self.root / call.call_id / call.call_id
        artifact.mkdir(parents=True)
        (artifact / "manifest.json").write_text(
            json.dumps(
                {
                    "requested_model": call.requested_model,
                    "observed_model": call.requested_model,
                    "outcome": "verified_pass",
                    "workspace_input_digest": "sha256:" + "6" * 64,
                    "workspace_output_digest": "sha256:" + "7" * 64,
                    "verifier_passed": True,
                    "verifier_score": 1.0,
                    "duration_ms": 10,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return SmokeCallResult(
            call_id=call.call_id,
            evidence_references=(str(artifact),),
            evidence_digests=(digest_tree(artifact),),
        )


def test_v2_plans_and_attempts_1_through_12_remain_byte_identical() -> None:
    for reference, expected in V2_RAW_SHA256.items():
        assert hashlib.sha256((ROOT / reference).read_bytes()).hexdigest() == expected


def test_attempt_13_and_diagnostic_are_safe_separate_and_non_promotable() -> None:
    history = json.loads((ROOT / "release/history/core-real-v2-attempt-13.json").read_text())
    diagnostic = json.loads((ROOT / "release/diagnostics/core-real-v2-attempt-13.json").read_text())
    manifest = load_release_evidence(ROOT / "release/release-evidence.json")

    assert history["receipt_digest"] == (
        "sha256:0f0480013e61a1dffdf0503f19e32e99a58ce757a1272745d8ad5e4e27d3b2da"
    )
    assert history["receipt_digest_domain"] == "RAW_FILE_SHA256"
    assert history["attempted_top_level_launches"] == 4
    assert tuple(call["call_id"] for call in history["calls"]) == EXPECTED_CALL_IDS[:4]
    assert all(
        call["evidence_digest_domain"] == "ARTIFACT_TREE_DIGEST" for call in history["calls"]
    )
    assert history["calls_5_to_8"] == "NOT_RUN"
    assert diagnostic["evidence_class"] == "DIAGNOSTIC_ONLY"
    assert diagnostic["release_promotable"] is False
    assert tuple(call["call_id"] for call in diagnostic["calls"]) == EXPECTED_CALL_IDS[4:]
    assert diagnostic["report_digest"] == (
        "sha256:b7eb662e0ace21b4f7e8ddc08ff5e8fc92ca386738e907457b4f5efd704bf5c3"
    )
    assert manifest.release_history.latest_attempt_id.endswith("attempt-13")
    assert manifest.release_history.complete_smoke.value == "NOT_VERIFIED"
    assert manifest.real_matrix.state.value == "NOT_RUN"


def test_v3_cycle_one_is_separate_and_technical_readiness_is_non_promotional() -> None:
    history = json.loads((ROOT / "release/history/core-real-v3-attempt-1.json").read_text())
    diagnostic = json.loads((ROOT / "release/diagnostics/core-real-v3-attempt-1.json").read_text())
    readiness = load_technical_readiness(ROOT / "release/technical-readiness-v3.json")

    assert history["status"] == "ABORTED"
    assert history["attempted_top_level_launches"] == 5
    assert history["calls_6_to_8"] == "NOT_RUN"
    assert diagnostic["evidence_class"] == "DIAGNOSTIC_ONLY"
    assert diagnostic["release_promotable"] is False
    assert [item["call_id"] for item in diagnostic["calls"]] == list(EXPECTED_CALL_IDS[5:])
    assert readiness.subject_plane_technical_ready.value == "REACHED"
    assert readiness.judge_plane_reached.value == "REACHED"
    assert readiness.complete_release_smoke.value == "NOT_REACHED"
    assert readiness.core_release_ready is False
    assert readiness.release_state_effect == "NONE"
    assert len(readiness.observations) == 8


def test_real_judge_plan_reuses_frozen_v3_profile_suite_and_thresholds() -> None:
    plan, _suite, _definitions = build_real_judge_plan(
        ROOT, {"HARNESSLAB_OPENCODE_GO_API_KEY": "REFERENCE_ONLY"}
    )

    assert plan.calibration_id == "core-real-judge-v3"
    assert len(plan.judge_cells) == 1
    assert len(plan.slots) == 63
    assert plan.judge_cells[0].model_profile.requested_model == "glm-5.2"
    assert plan.judge_cells[0].runner_contract == "provider-adapter-v1"
    assert plan.qualification_policy.minimum_macro_f1 == 0.95


def test_v3_smoke_changes_only_version_bindings_and_subject_timeout() -> None:
    v2 = SmokeControlPlane.load(ROOT, plan_version="v2")
    v3 = SmokeControlPlane.load(ROOT, plan_version="v3")

    assert v3.release_plan.plan_id == "core-real-evidence-v3"
    assert v3.release_plan.experiment_id == "core-real-matrix-v3"
    assert v3.smoke_plan.plan_id == "core-real-smoke-v3"
    assert tuple(call.call_id for call in v3.smoke_plan.calls) == EXPECTED_CALL_IDS
    assert [call.timeout_seconds for call in v3.smoke_plan.calls] == [180] * 7 + [90]
    assert [profile.timeout_seconds for profile in v3.release_plan.selected_profiles] == [
        180,
        180,
        180,
        180,
        180,
        180,
        180,
        90,
    ]
    for old, new in zip(v2.smoke_plan.calls, v3.smoke_plan.calls, strict=True):
        old_facts = old.model_dump(mode="json", exclude={"timeout_seconds"})
        new_facts = new.model_dump(mode="json", exclude={"timeout_seconds"})
        assert old_facts == new_facts


def test_v3_matrix_preflight_and_exact_canary_are_frozen_keylessly() -> None:
    control = MatrixControlPlane.load(ROOT, plan_version="v3")
    receipt = control.preflight(_runtime())
    full = control.build_plan(_runtime())
    canary_digest, canary_ids = control.select_slots(_runtime(), "canary")
    pilot_digest, pilot_ids = control.select_slots(_runtime(), "pilot")

    assert receipt.matrix_id == "core-real-matrix-v3"
    assert (receipt.cells, receipt.tasks, receipt.repeats, receipt.logical_runs) == (7, 18, 5, 630)
    assert receipt.real_calls == 0
    canary = tuple(slot for slot in full.run_slots if slot.slot_id in set(canary_ids))
    pilot = tuple(slot for slot in full.run_slots if slot.slot_id in set(pilot_ids))
    assert canary_digest == pilot_digest == full.digest
    assert len(canary) == 7
    assert full.experiment_id == "core-real-matrix-v3"
    assert {slot.cell_id for slot in canary} == {cell.cell_id for cell in receipt.cells_detail}
    assert {slot.task.task_id for slot in canary} == {MATRIX_CANARY_TASK_ID}
    assert {slot.repeat_index for slot in canary} == {0}
    assert len(pilot) == 21
    assert {slot.task.task_id for slot in pilot} == set(MATRIX_PILOT_TASK_IDS)
    assert {slot.repeat_index for slot in pilot} == {0}
    assert set(canary_ids) < set(pilot_ids)
    profiles = control._profiles(_runtime())
    assert {
        (
            profile.request_timeout_seconds
            if hasattr(profile, "request_timeout_seconds")
            else profile.execution_timeout_seconds
        )
        for profile in profiles.values()
    } == {180}


def test_v3_deepseek_runtime_family_accepts_only_its_phase_f_producer_alias() -> None:
    slot = next(
        item
        for item in MatrixControlPlane.load(ROOT, plan_version="v3")
        .build_plan(_runtime())
        .run_slots
        if item.cell_id == "harness-deepseek-v4flash"
    )
    facts = ComparisonFacts(
        evidence_identity=canonical_digest({"fixture": "deepseek-alias"}),
        task_id=slot.task.task_id,
        task_version=slot.task.task_version,
        task_digest=slot.task.task_digest,
        workspace_input_digest=slot.task.workspace_input_digest,
        context_identity=slot.task.context_identity or "NONE",
        verifier_identity=slot.task.verifier_identity,
        requested_model=slot.requested_model,
        observed_model=None,
        provider_route=slot.provider_route,
        budget_identity=slot.task.budget_identity,
        network_policy=slot.task.network_policy.value,
        harness="deepseek-harness",
        harness_version=slot.harness_version,
        harness_profile_identity=slot.profile_identity,
        prompt_identity=None,
        trace_coverage="FINAL_OUTPUT_ONLY",
    )
    raw = {
        "profile_hash": slot.harness_config_identity,
        "profile": {"reasoning_effort": slot.reasoning_effort},
    }

    validate_manifest_against_slot(raw, facts, slot)


@pytest.mark.asyncio
async def test_v3_matrix_canary_is_inert_without_explicit_gate(tmp_path: Path) -> None:
    with pytest.raises(MatrixControlPlaneError, match="--allow-real-matrix-canary"):
        await execute_real_matrix_canary(
            ROOT,
            allow_real_matrix_canary=False,
            artifact_root=tmp_path / "artifacts",
            runtime_root=tmp_path / "runtime",
        )


@pytest.mark.asyncio
async def test_v3_diagnostic_runs_only_unattempted_calls_and_never_promotes(
    tmp_path: Path,
) -> None:
    control = SmokeControlPlane.load(ROOT, plan_version="v3")
    receipt = SmokeExecutionReceipt(
        plan_id=control.smoke_plan.plan_id,
        smoke_plan_digest=control.smoke_plan_digest,
        release_plan_digest=control.release_plan.digest,
        status=SmokeExecutionStatus.ABORTED,
        attempted_top_level_launches=4,
        failing_call_id=EXPECTED_CALL_IDS[3],
        failure_category=SmokeFailureCategory.HARNESS_FAILURE,
        results=(),
    )
    receipt_path = tmp_path / "smoke-execution.json"
    receipt_path.write_text(receipt.canonical_json() + "\n")
    output = tmp_path / "diagnostic"
    invoker = _V3DiagnosticInvoker(output)

    report = await execute_component_diagnostics(
        control,
        control.resolve_real_bindings(_environment(), _runtime()),
        invoker,
        attempt_receipt_path=receipt_path,
        artifact_root=output,
    )

    assert invoker.calls == list(EXPECTED_CALL_IDS[4:])
    assert report.smoke_attempted_call_ids == EXPECTED_CALL_IDS[:4]
    assert report.diagnostic_call_ids == EXPECTED_CALL_IDS[4:]
    assert report.release_promotable is False
