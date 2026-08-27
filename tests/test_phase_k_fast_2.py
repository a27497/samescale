# ruff: noqa: E501 -- immutable historical evidence digests remain visually auditable.

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from harnesslab.egress import EGRESS_PROXY_IMAGE
from harnesslab.harness_lane.profile import CODEX_IMAGE
from harnesslab.multi_harness.profile import CLAUDE_IMAGE, DEEPSEEK_IMAGE
from harnesslab.release.contracts import load_release_evidence
from harnesslab.release.diagnostic import execute_component_diagnostics
from harnesslab.release.matrix import (
    MATRIX_CANARY_ID,
    MATRIX_CANARY_TASK_ID,
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
    canary = control.build_canary_plan(_runtime())

    assert receipt.matrix_id == "core-real-matrix-v3"
    assert (receipt.cells, receipt.tasks, receipt.repeats, receipt.logical_runs) == (7, 18, 5, 630)
    assert receipt.real_calls == 0
    assert len(canary.run_slots) == 7
    assert canary.experiment_id == MATRIX_CANARY_ID
    assert {slot.cell_id for slot in canary.run_slots} == {
        cell.cell_id for cell in receipt.cells_detail
    }
    assert {slot.task.task_id for slot in canary.run_slots} == {MATRIX_CANARY_TASK_ID}
    assert {slot.repeat_index for slot in canary.run_slots} == {0}
    profiles = control._profiles(_runtime())
    assert {
        (
            profile.request_timeout_seconds
            if hasattr(profile, "request_timeout_seconds")
            else profile.execution_timeout_seconds
        )
        for profile in profiles.values()
    } == {180}


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
