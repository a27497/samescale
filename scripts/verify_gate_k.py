from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from harnesslab.egress import (
    EGRESS_PROXY_BASE,
    EGRESS_PROXY_IMAGE,
    EgressProxyRuntime,
    preflight_egress_network_isolation,
)
from harnesslab.release.contracts import (
    CoreReleaseError,
    build_corpus_manifest,
    evaluate_release_readiness,
    load_badcase_plan,
    load_contiguous_v2_histories,
    load_core_corpus,
    load_real_evidence_plan,
    load_real_smoke_plan,
    load_release_evidence,
    load_resume_claim_map,
    tag_creation_authorized,
    validate_dynamic_v2_history,
    validate_keyless_contract_state,
)
from harnesslab.release.final_verifier import (
    resolve_authoritative_snapshot,
    resolve_github_ci,
    verify_semantic_final_release,
)
from harnesslab.release.matrix import MatrixControlPlane
from harnesslab.release.models import EvidenceState
from harnesslab.release.smoke import SmokeControlPlane, resolve_runtime_identities

ROOT = Path(__file__).resolve().parents[1]
JUNIT = ROOT / "gate-k-results.xml"
REQUIRED_DOCS = (
    "README.md",
    "docs/ARCHITECTURE.md",
    "docs/EVAL_METHODOLOGY.md",
    "docs/FAIRNESS_CONTRACT.md",
    "docs/BADCASES.md",
    "docs/INTERVIEW_GUIDE.md",
    "docs/RESUME_SCOPE.md",
    "docs/SECURITY.md",
    "docs/RELEASE_EVIDENCE.md",
    "docs/REAL_EVIDENCE_AUTHORIZATION.md",
)
CRITICAL_TESTS = {
    "test_core_corpus_is_exact_balanced_deterministic_and_validated",
    "test_corpus_has_sixteen_semantic_families_and_one_cross_language_control",
    "test_corpus_rejects_duplicate_independent_scenario_family",
    "test_corpus_reconstruction_detects_semantic_metadata_drift",
    "test_corpus_rejects_a_mutated_verifier",
    "test_real_plan_has_frozen_kb0_profiles_and_exact_preflight",
    "test_planned_uplift_pair_cannot_bypass_provider_route_comparability",
    "test_ablation_plan_freezes_hard_controls_and_is_not_run",
    "test_release_evidence_is_strict_keyless_and_not_ready",
    "test_verified_evidence_and_resume_claims_cannot_be_forged",
    "test_resume_claim_map_refs_exist_and_real_claims_remain_unverified",
    "test_three_badcase_slots_are_explicitly_pending",
    "test_tag_guard_refuses_incomplete_release_and_tag_is_absent",
    "test_release_docs_and_fresh_setup_contract_exist",
    "test_ci_runs_keyless_gate_k_after_gate_j_without_real_execution",
    "test_final_release_rejects_arbitrary_matching_sha_artifact",
    "test_final_release_rejects_postgresql_select_one_without_experiment",
    "test_final_release_rejects_wrong_experiment_plan_digest",
    "test_final_release_rejects_wrong_experiment_corpus",
    "test_final_release_rejects_629_runs",
    "test_final_release_rejects_corrupt_run_manifest_set",
    "test_final_release_accepts_production_valid_capability_failure",
    "test_final_release_rejects_inconsistent_run_lifecycle",
    "test_final_release_rejects_fake_pair_evidence",
    "test_final_release_rejects_ablation_hard_control_drift",
    "test_final_release_rejects_corrupt_judge_report",
    "test_final_release_rejects_badcase_bound_to_wrong_run",
    "test_final_release_rejects_capability_pass_badcase",
    "test_final_release_rejects_unsupported_real_resume_claim",
    "test_final_release_rejects_remote_ci_head_or_workflow_mismatch",
    "test_fully_valid_fake_semantic_fixture_passes_and_issues_receipt",
    "test_kb0_provider_contracts_freeze_truthful_selected_profiles",
    "test_kb0_codex_custom_provider_is_explicit_secret_free_and_single_treatment",
    "test_opencode_go_claude_qwen_uses_typed_api_key_transport",
    "test_opencode_go_messages_exact_url_headers_and_shared_claude_route",
    "test_opencode_go_judge_exact_route_bearer_and_public_content_only",
    "test_v1_history_and_opencode_go_route_snapshot_are_frozen",
    "test_kb0_provider_scoped_egress_allows_fake_and_denies_bypass_and_targets",
    "test_kb0_subject_docker_uses_only_internal_proxy_network",
    "test_kb0_pair_is_configured_but_never_claims_comparable_or_uplift",
    "test_kb0_smoke_plan_is_exact_bounded_and_unexecuted",
    "test_kb0_matrix_preflight_and_release_hard_stop_are_unchanged",
    "test_smoke_production_control_plane_exact_eight_call_binding",
    "test_top_level_release_history_covers_repository_attempts_through_r16",
    "test_release_history_summary_accepts_a_future_contiguous_attempt",
    "test_release_history_summary_rejects_a_removed_attempt_reference",
    "test_release_history_summary_rejects_a_gap",
    "test_release_history_summary_rejects_latest_attempt_id_mismatch",
    "test_gate_k_dynamic_history_rejects_latest_failing_call_mismatch",
    "test_post_r4_smoke_history_is_safe_immutable_and_truthful",
    "test_post_r5_smoke_history_is_safe_immutable_and_truthful",
    "test_post_r6_smoke_history_is_safe_immutable_and_truthful",
    "test_post_r7_smoke_history_is_safe_immutable_and_truthful",
    "test_post_r9_attempt_6_history_is_safe_immutable_and_truthful",
    "test_post_r9_attempt_7_history_is_safe_immutable_and_truthful",
    "test_post_r10_attempt_8_history_is_safe_immutable_and_truthful",
    "test_post_r11_attempt_9_history_is_safe_immutable_and_truthful",
    "test_post_r12_attempt_10_history_is_safe_immutable_and_truthful",
    "test_post_r14_attempt_11_history_is_safe_immutable_and_truthful",
    "test_post_r15_attempt_12_history_is_safe_immutable_and_truthful",
    "test_real_matrix_preflight_is_exact_keyless_and_frozen",
    "test_real_matrix_has_no_implicit_full_launch_default",
    "test_diagnostic_sweep_skips_attempted_continues_and_is_non_promotable",
    "test_telemetry_reports_observed_values_and_requires_price_input",
    "test_v2_plans_and_attempts_1_through_12_remain_byte_identical",
    "test_attempt_13_and_diagnostic_are_safe_separate_and_non_promotable",
    "test_v3_smoke_changes_only_version_bindings_and_subject_timeout",
    "test_v3_matrix_preflight_and_exact_canary_are_frozen_keylessly",
    "test_v3_matrix_canary_is_inert_without_explicit_gate",
    "test_v3_diagnostic_runs_only_unattempted_calls_and_never_promotes",
    "test_production_smoke_persists_codex_precapture_infrastructure_evidence",
    "test_smoke_dry_run_preflight_performs_zero_provider_invocations",
    "test_v2_credential_preflight_prints_presence_only",
    "test_smoke_same_path_fake_execution_consumes_exact_plan_without_network",
    "test_smoke_missing_config_stops_before_first_call",
    "test_smoke_abort_on_first_failure_never_invokes_calls_four_through_eight",
    "test_smoke_typed_codex_infrastructure_failure_stops_without_retry_or_fallback",
    "test_smoke_post_r10_subject_command_failure_continues_to_call_five",
    "test_smoke_infra_timeout_trace_stops_at_call_four[ambiguous]",
    "test_smoke_infra_timeout_trace_stops_at_call_four[bwrap]",
    "test_smoke_infra_timeout_trace_stops_at_call_four[error]",
    "test_smoke_budget_exhaustion_rejects_exposed_wrong_model",
    "test_smoke_multi_harness_model_turn_failure_is_capability_result",
    "test_smoke_one_judge_call_only",
    "test_smoke_ninth_call_is_rejected_before_execution",
    "test_smoke_provider_fallbacks_are_rejected_in_production_assertions",
    "test_dsh_e1_not_exposed_is_accepted_without_observed_model_fabrication",
    "test_claude_smoke_requires_exact_exposed_observed_model",
    "test_dsh_incoherent_observed_model_state_is_rejected",
    "test_deepseek_runtime_config_drift_remains_rejected",
    "test_immutable_egress_proxy_image_identity_is_required",
    "test_internal_network_create_argv_requires_isolated_gateway_mode",
    "test_real_smoke_network_isolation_preflight_fails_before_first_call",
    "test_actual_docker_network_isolation_preflight_attests_and_cleans_up",
    "test_network_attestation_rejects_internal_bridge_without_isolated_gateway_mode",
    "test_actual_local_docker_egress_topology_denies_bypass_and_cleans_up",
    "test_egress_cleanup_attempts_every_resource_after_partial_failure",
    "test_codex_and_multiharness_cleanup_continue_after_subject_failure",
    "test_direct_success_uses_runtime_url_but_persists_only_route_identity",
    "test_direct_failure_uses_runtime_url_without_persisting_value",
    "test_codex_runtime_url_is_environment_only_and_ephemeral",
    "test_codex_runtime_values_are_absent_from_every_harness_artifact",
    "test_smoke_result_and_receipt_exclude_runtime_url_value",
    "test_runtime_entrypoint_removes_url_only_from_codex_child_environment",
    "test_pinned_codex_uses_generated_isolated_relay_profile_without_websockets",
    "test_pinned_codex_split_sandbox_executes_with_outer_filesystem_and_seccomp_network",
}


@dataclass(frozen=True)
class Check:
    name: str
    command: tuple[str, ...]
    timeout_seconds: int = 1200


def run(check: Check) -> bool:
    print(f"\n=== {check.name} ===", flush=True)
    print("COMMAND:", subprocess.list2cmdline(check.command), flush=True)
    try:
        result = subprocess.run(check.command, cwd=ROOT, check=False, timeout=check.timeout_seconds)
    except subprocess.TimeoutExpired:
        print(f"FAIL: command exceeded {check.timeout_seconds}s")
        return False
    print(f"{'PASS' if result.returncode == 0 else 'FAIL'}: exit={result.returncode}")
    return result.returncode == 0


def verify_junit() -> bool:
    try:
        cases = ET.parse(JUNIT).getroot().findall(".//testcase")
    except (OSError, ET.ParseError):
        print("FAIL: Gate K JUnit evidence is unavailable")
        return False
    names = {case.attrib.get("name", "") for case in cases}
    skipped = [
        case.attrib.get("name", "unknown") for case in cases if case.find("skipped") is not None
    ]
    missing = CRITICAL_TESTS - names
    if not cases or skipped or missing:
        print(
            "FAIL: Gate K test evidence incomplete: "
            f"cases={len(cases)} skipped={skipped} missing={sorted(missing)}"
        )
        return False
    print(f"PASS: {len(cases)} Gate K focused tests recorded; critical set present; zero skipped")
    return True


def verify_contract_mode() -> bool:
    try:
        checked = load_core_corpus(ROOT / "release/core-corpus.json")
        rebuilt = build_corpus_manifest(ROOT)
        plan = load_real_evidence_plan(ROOT / "release/core-real-evidence-plan.json")
        smoke = load_real_smoke_plan(ROOT / "release/core-real-smoke-plan.json")
        smoke_control = SmokeControlPlane.load(ROOT)
        v3_plan = load_real_evidence_plan(ROOT / "release/core-real-evidence-plan-v3.json")
        v3_smoke = load_real_smoke_plan(ROOT / "release/core-real-smoke-plan-v3.json")
        v3_smoke_control = SmokeControlPlane.load(ROOT, plan_version="v3")
        evidence = load_release_evidence(ROOT / "release/release-evidence.json")
        claims = load_resume_claim_map(ROOT / "release/resume-claim-evidence.json")
        badcases = load_badcase_plan(ROOT / "release/badcases.json")
        validate_keyless_contract_state(evidence)
    except CoreReleaseError as exc:
        print(f"FAIL: release contract invalid: {exc}")
        return False
    if rebuilt != checked:
        print("FAIL: checked corpus differs from independently rebuilt task inventory")
        return False
    if any(not (ROOT / path).is_file() for path in REQUIRED_DOCS):
        print("FAIL: Core document set is incomplete")
        return False
    if any(
        not (ROOT / reference).exists()
        for claim in claims.claims
        if claim.status is EvidenceState.VERIFIED
        for reference in claim.evidence_refs
    ):
        print("FAIL: VERIFIED resume claim references missing evidence")
        return False
    if len(badcases.slots) != 3 or any(
        slot.status is not EvidenceState.NOT_VERIFIED for slot in badcases.slots
    ):
        print("FAIL: K-A BadCase placeholders are not fail-closed")
        return False
    workflow = (ROOT / ".github/workflows/full-ci.yml").read_text(encoding="utf-8")
    if workflow.index("scripts/verify_gate_j.py") >= workflow.index("scripts/verify_gate_k.py"):
        print("FAIL: Gate K is not ordered after Gate J")
        return False
    if "--final-release" in workflow:
        print("FAIL: ordinary CI invokes final release mode")
        return False
    tracked_environment_files = subprocess.run(
        ("git", "ls-files", "*.env", ".env", ".env.*"),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    tracked_env = [path for path in tracked_environment_files if not path.endswith(".env.example")]
    if tracked_env:
        print(f"FAIL: environment credential file is tracked: {tracked_env}")
        return False
    serialized_release = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (
            "release/core-real-evidence-plan.json",
            "release/core-real-smoke-plan.json",
            "release/core-real-evidence-plan-v3.json",
            "release/core-real-smoke-plan-v3.json",
            "release/release-evidence.json",
            "release/resume-claim-evidence.json",
        )
    )
    secret_patterns = (
        r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}",
        r"(?i)bearer\s+[A-Za-z0-9._-]{20,}",
    )
    if any(re.search(pattern, serialized_release) for pattern in secret_patterns):
        print("FAIL: release artifact contains secret-like material")
        return False
    readiness = evaluate_release_readiness(evidence)
    if readiness.core_release_ready or tag_creation_authorized(evidence):
        print("FAIL: incomplete K-A evidence authorized a release")
        return False
    if plan.deepseek_e2 is not EvidenceState.DEFERRED_NOT_VERIFIED:
        print("FAIL: DeepSeek E2 state drifted")
        return False
    if smoke.real_evaluation_call_count != 0 or smoke.execution_state is not EvidenceState.NOT_RUN:
        print("FAIL: K-B0 smoke plan implies a real call")
        return False
    if smoke_control.preflight().attempted_top_level_launches != 0:
        print("FAIL: K-B0 smoke preflight attempted a provider call")
        return False
    if (
        v3_plan.plan_id != "core-real-evidence-v3"
        or v3_plan.experiment_id != "core-real-matrix-v3"
        or v3_smoke.plan_id != "core-real-smoke-v3"
        or v3_smoke.release_plan_digest != v3_plan.digest
        or [call.timeout_seconds for call in v3_smoke.calls] != [180] * 7 + [90]
        or [profile.timeout_seconds for profile in v3_plan.selected_profiles] != [180] * 7 + [90]
        or v3_smoke_control.preflight().attempted_top_level_launches != 0
    ):
        print("FAIL: v3 smoke/release contract drifted")
        return False
    try:
        runtime = asyncio.run(resolve_runtime_identities())
        v3_matrix = MatrixControlPlane.load(ROOT, plan_version="v3")
        v3_matrix_receipt = v3_matrix.preflight(runtime)
        v3_full = v3_matrix.build_plan(runtime)
        v3_canary_digest, v3_canary_ids = v3_matrix.select_slots(runtime, "canary")
        v3_pilot_digest, v3_pilot_ids = v3_matrix.select_slots(runtime, "pilot")
        v3_canary = tuple(slot for slot in v3_full.run_slots if slot.slot_id in set(v3_canary_ids))
        v3_pilot = tuple(slot for slot in v3_full.run_slots if slot.slot_id in set(v3_pilot_ids))
    except Exception as exc:
        print(f"FAIL: v3 Matrix contract unavailable: {type(exc).__name__}")
        return False
    if (
        v3_matrix_receipt.matrix_id != "core-real-matrix-v3"
        or (
            v3_matrix_receipt.cells,
            v3_matrix_receipt.tasks,
            v3_matrix_receipt.repeats,
            v3_matrix_receipt.logical_runs,
            v3_matrix_receipt.real_calls,
        )
        != (7, 18, 5, 630, 0)
        or v3_canary_digest != v3_full.digest
        or v3_pilot_digest != v3_full.digest
        or len(v3_canary) != 7
        or {slot.task.task_id for slot in v3_canary} != {"core-python-deduplicate"}
        or {slot.repeat_index for slot in v3_canary} != {0}
        or len(v3_pilot) != 21
        or {slot.repeat_index for slot in v3_pilot} != {0}
        or not set(v3_canary_ids) < set(v3_pilot_ids)
    ):
        print("FAIL: v3 Matrix or exact canary contract drifted")
        return False
    history = json.loads((ROOT / plan.history_reference).read_text(encoding="utf-8"))
    try:
        v2_histories, v2_history_references = load_contiguous_v2_histories(
            ROOT / "release/history", ROOT
        )
        validate_dynamic_v2_history(
            v2_histories,
            v2_history_references,
            evidence.release_history,
            smoke_plan_digest=smoke.digest,
            release_plan_digest=plan.digest,
            smoke_call_ids=tuple(call.call_id for call in smoke.calls),
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL: immutable v2 history contract failed: {exc}")
        return False
    histories_by_id = {item["attempt_id"]: item for item in v2_histories}
    post_r4_history = v2_histories[1]
    post_r5_history = v2_histories[2]
    post_r6_history = v2_histories[3]
    post_r7_history = v2_histories[4]
    post_r9_attempt_6 = v2_histories[5]
    post_r9_attempt_7 = v2_histories[6]
    post_r10_attempt_8 = v2_histories[7]
    post_r11_attempt_9 = v2_histories[8]
    post_r12_attempt_10 = histories_by_id.get("core-real-smoke-v2-attempt-10", {})
    post_r14_attempt_11 = histories_by_id.get("core-real-smoke-v2-attempt-11", {})
    post_r15_attempt_12 = histories_by_id.get("core-real-smoke-v2-attempt-12", {})
    snapshot = json.loads(
        (ROOT / plan.official_route_snapshot_reference).read_text(encoding="utf-8")
    )
    if (
        history.get("authoritative_commit") != "45e83d735cee48d9a29361da5964cee83d048a42"
        or history.get("evidence_plan", {}).get("canonical_digest")
        != "sha256:b97a0798b7855b0544c8acdb861551bc918d57fc6fbda834cc13c992955ad098"
        or history.get("smoke_plan", {}).get("canonical_digest")
        != "sha256:a9a21424199fc30437589e4526a4bf91dbe2dce65520a69077924098d7dc528f"
        or len(history.get("attempts", ())) != 3
    ):
        print("FAIL: immutable v1 plan or attempt history drifted")
        return False
    latest_summary = evidence.release_history
    if (
        len(latest_summary.keyless_repairs) != 1
        or latest_summary.keyless_repairs[0].repair_id != "R12"
        or latest_summary.keyless_repairs[0].after_attempt_id != "core-real-smoke-v2-attempt-9"
        or latest_summary.keyless_repairs[0].state != "KEYLESS_VERIFIED"
        or latest_summary.keyless_repairs[0].real_calls != 0
        or latest_summary.complete_smoke is not EvidenceState.NOT_VERIFIED
        or latest_summary.matrix_evidence is not EvidenceState.NOT_RUN
        or latest_summary.release_verification is not EvidenceState.NOT_VERIFIED
        or evidence.remote_ci.state is not EvidenceState.NOT_VERIFIED
        or evidence.core_release_ready
    ):
        print("FAIL: top-level release history is inconsistent with immutable v2 attempts")
        return False
    release_docs = (ROOT / "docs/RELEASE_EVIDENCE.md").read_text(encoding="utf-8")
    authorization_docs = (ROOT / "docs/REAL_EVIDENCE_AUTHORIZATION.md").read_text(encoding="utf-8")
    resume_docs = (ROOT / "docs/RESUME_SCOPE.md").read_text(encoding="utf-8")
    if (
        "attempt-1.json` through `history/core-real-v2-attempt-13.json`" not in release_docs
        or "Attempt 13 executed Calls 1-4" not in authorization_docs
        or "post-R12 real Claude verification remains `NOT_RUN` / `NOT_REACHED`" not in release_docs
        or "Calls 2-8 were `NOT_RUN`" not in authorization_docs
        or "attempts 1-13" not in resume_docs
        or "post-R12 real Claude verification remains `NOT_RUN` / `NOT_REACHED`" not in resume_docs
        or "Attempts 3, 6, 10, 11, and 12" not in authorization_docs
        or "Root cause remains `NOT_DETERMINED`" not in authorization_docs
    ):
        print("FAIL: top-level release documentation lags immutable v2 history")
        return False
    if (
        post_r4_history.get("source_commit") != "07e48c2b3eb330c3ff56a8473bb98025f86490b3"
        or post_r4_history.get("receipt_digest")
        != "sha256:e25ddea75fa5ca2ade3167bc063d9b771da1af5381f5a13403af118e136976d2"
        or post_r4_history.get("attempted_top_level_launches") != 4
        or [call.get("outcome") for call in post_r4_history.get("calls", ())]
        != ["verified_fail", "verified_pass", "verified_pass", "INFRASTRUCTURE"]
        or post_r4_history.get("calls_5_to_8") != "NOT_RUN"
        or post_r4_history.get("retry_count") != 0
        or post_r4_history.get("fallback_count") != 0
    ):
        print("FAIL: immutable post-R4 smoke history drifted")
        return False
    if (
        post_r5_history.get("source_commit") != "519ee8034af845f636aac8d836536dd4c4601bd0"
        or post_r5_history.get("receipt_digest")
        != "sha256:bb0f747005b90caa1983168f84d9dcc468be7e1ea7e575f488ce66e41e30faae"
        or post_r5_history.get("attempted_top_level_launches") != 1
        or post_r5_history.get("calls", [{}])[0].get("provider_failure") != "timeout"
        or post_r5_history.get("calls", [{}])[0].get("timeout_phase") != "read"
        or post_r5_history.get("calls_2_to_8") != "NOT_RUN"
        or post_r5_history.get("retry_count") != 0
        or post_r5_history.get("fallback_count") != 0
        or post_r5_history.get("raw_evidence_hygiene") != "REJECTED_CONFIG_VALUE_DISCLOSURE"
    ):
        print("FAIL: immutable post-R5 smoke history drifted")
        return False
    if (
        post_r6_history.get("source_commit") != "06027d08735886a2add1c492081154a4374ea3e2"
        or post_r6_history.get("receipt_digest")
        != "sha256:c3eb90ce738805311f8ed35209c86b387749865739b797047f2b0ac5207b0856"
        or post_r6_history.get("attempted_top_level_launches") != 4
        or [call.get("outcome") for call in post_r6_history.get("calls", ())]
        != ["verified_fail", "verified_pass", "verified_pass", "harness_error"]
        or post_r6_history.get("calls", [{}, {}, {}, {}])[3].get("harness_failure") != "timeout"
        or post_r6_history.get("calls_5_to_8") != "NOT_RUN"
        or post_r6_history.get("retry_count") != 0
        or post_r6_history.get("fallback_count") != 0
        or post_r6_history.get("runtime_value_hygiene")
        != {"base_url_present": "NO", "api_key_present": "NO"}
    ):
        print("FAIL: immutable post-R6 smoke history drifted")
        return False
    if (
        post_r7_history.get("source_commit") != "029c0d84036dc697786fad02910c4212298ed28c"
        or post_r7_history.get("receipt_digest")
        != "sha256:9a8e4892d2fd070f004038068bc30aa2b327f366414455cf494be4a65fb6941a"
        or post_r7_history.get("attempted_top_level_launches") != 4
        or [call.get("outcome") for call in post_r7_history.get("calls", ())]
        != ["verified_fail", "subject_output_error", "verified_pass", "harness_error"]
        or post_r7_history.get("calls", [{}, {}, {}, {}])[3].get("harness_failure") != "timeout"
        or post_r7_history.get("safe_command_diagnostics", {}).get("root_cause")
        != "CODEX_INNER_BWRAP_USER_NAMESPACE_DENIED"
        or post_r7_history.get("calls_5_to_8") != "NOT_RUN"
        or post_r7_history.get("retry_count") != 0
        or post_r7_history.get("fallback_count") != 0
        or post_r7_history.get("runtime_value_hygiene")
        != {"relay_base_url_present": "NO", "api_key_present": "NO"}
    ):
        print("FAIL: immutable post-R7 smoke history drifted")
        return False
    if (
        post_r9_attempt_6.get("source_commit") != "14d18f9ac00cff18395c951a52c65f3469c199ad"
        or post_r9_attempt_6.get("receipt_digest")
        != "sha256:ba773df2c0b75d256ce5477e1ec4950286103031ebdd114bb33d730c45a28175"
        or post_r9_attempt_6.get("attempted_top_level_launches") != 1
        or post_r9_attempt_6.get("calls", [{}])[0].get("provider_failure") != "timeout"
        or post_r9_attempt_6.get("calls", [{}])[0].get("timeout_phase") != "read"
        or post_r9_attempt_6.get("calls_2_to_8") != "NOT_RUN"
        or post_r9_attempt_6.get("retry_count") != 0
        or post_r9_attempt_6.get("fallback_count") != 0
    ):
        print("FAIL: immutable post-R9 attempt 6 history drifted")
        return False
    if (
        post_r9_attempt_7.get("source_commit") != "14d18f9ac00cff18395c951a52c65f3469c199ad"
        or post_r9_attempt_7.get("receipt_digest")
        != "sha256:fc77340afe9b71988c005af6bdbe519944287927767ff43f4a100743b8db02ed"
        or post_r9_attempt_7.get("attempted_top_level_launches") != 4
        or [call.get("outcome") for call in post_r9_attempt_7.get("calls", ())]
        != ["verified_pass", "verified_pass", "verified_pass", "harness_error"]
        or post_r9_attempt_7.get("calls", [{}, {}, {}, {}])[3].get(
            "original_persisted_harness_failure"
        )
        != "timeout"
        or post_r9_attempt_7.get("r10_classification_review")
        != "CLEAN_EXECUTION_BUDGET_EXHAUSTION_CANDIDATE"
        or post_r9_attempt_7.get("safe_r9_diagnostics", {}).get("successful_command_count") != 1
        or post_r9_attempt_7.get("safe_r9_diagnostics", {}).get("failed_command_count") != 0
        or post_r9_attempt_7.get("security_profile", {}).get("status") != "PASS"
        or post_r9_attempt_7.get("calls_5_to_8") != "NOT_RUN"
        or post_r9_attempt_7.get("retry_count") != 0
        or post_r9_attempt_7.get("fallback_count") != 0
    ):
        print("FAIL: immutable post-R9 attempt 7 history drifted")
        return False
    if (
        post_r10_attempt_8.get("source_commit") != "2eb2be74c131e330be48467495b8c559776be146"
        or post_r10_attempt_8.get("receipt_digest")
        != "sha256:45eae792acbb7f8bc92d3097804dbc5c13ad85f181910f24092543d5d8c9749e"
        or post_r10_attempt_8.get("attempted_top_level_launches") != 4
        or [call.get("outcome") for call in post_r10_attempt_8.get("calls", ())]
        != ["subject_output_error", "verified_fail", "verified_fail", "harness_error"]
        or post_r10_attempt_8.get("calls", [{}, {}, {}, {}])[3].get(
            "original_persisted_harness_failure"
        )
        != "timeout"
        or post_r10_attempt_8.get("calls", [{}, {}, {}, {}])[3].get(
            "original_persisted_process_exit_code"
        )
        is not None
        or post_r10_attempt_8.get("r11_classification_review", {}).get("failed_command_reason")
        != "SUBJECT_COMMAND_NONZERO_EXIT"
        or post_r10_attempt_8.get("r11_classification_review", {}).get("safe_reason_detail")
        != "GIT_WORKSPACE_PROBE_NOT_REPOSITORY"
        or post_r10_attempt_8.get("r11_classification_review", {}).get("successful_command_count")
        != 1
        or post_r10_attempt_8.get("r11_classification_review", {}).get(
            "subject_nonzero_command_count"
        )
        != 1
        or post_r10_attempt_8.get("security_profile", {}).get("status") != "PASS"
        or post_r10_attempt_8.get("runtime_value_hygiene", {}).get("status") != "PASS"
        or post_r10_attempt_8.get("calls_5_to_8") != "NOT_RUN"
        or post_r10_attempt_8.get("retry_count") != 0
        or post_r10_attempt_8.get("fallback_count") != 0
    ):
        print("FAIL: immutable post-R10 attempt 8 history drifted")
        return False
    if (
        post_r11_attempt_9.get("source_commit") != "9f7ac3836da83d6009e2caa5eade07683ed68c7f"
        or post_r11_attempt_9.get("receipt_digest")
        != "sha256:750cb6a6d396bc49c43d07b9912bb5a84f016849d6e799faac435a750a0516bb"
        or post_r11_attempt_9.get("attempted_top_level_launches") != 6
        or [call.get("outcome") for call in post_r11_attempt_9.get("calls", ())]
        != [
            "verified_fail",
            "subject_output_error",
            "subject_output_error",
            "harness_error",
            "harness_error",
            "harness_error",
        ]
        or post_r11_attempt_9.get("calls", [{}, {}, {}, {}, {}, {}])[5].get("harness_failure")
        != "process_error"
        or post_r11_attempt_9.get("calls", [{}, {}, {}, {}, {}, {}])[5].get("trace_event_count")
        != 0
        or post_r11_attempt_9.get("calls_7_to_8") != "NOT_RUN"
        or post_r11_attempt_9.get("retry_count") != 0
        or post_r11_attempt_9.get("fallback_count") != 0
        or post_r11_attempt_9.get("runtime_value_hygiene", {}).get("status") != "PASS"
    ):
        print("FAIL: immutable post-R11 attempt 9 history drifted")
        return False
    attempt_10_call = post_r12_attempt_10.get("calls", [{}])[0]
    attempt_10_hygiene = post_r12_attempt_10.get("runtime_value_hygiene", {})
    if (
        post_r12_attempt_10.get("source_commit") != "faf3b506c88421717c80a6848acbb08451e4314a"
        or post_r12_attempt_10.get("receipt_digest")
        != "sha256:be06f9eff5303db4f808b61dcf7da98d8a76a574a469f4bec474a8de95bff1df"
        or post_r12_attempt_10.get("attempted_top_level_launches") != 1
        or post_r12_attempt_10.get("failing_call_id") != "smoke-1-model-gpt56-relay-responses"
        or post_r12_attempt_10.get("failure_category") != "PROVIDER_FAILURE"
        or attempt_10_call.get("provider_failure") != "timeout"
        or attempt_10_call.get("timeout_phase") != "read"
        or attempt_10_call.get("observed_model") is not None
        or attempt_10_call.get("outcome") != "provider_error"
        or attempt_10_call.get("verifier") != "NOT_RUN"
        or post_r12_attempt_10.get("calls_2_to_8") != "NOT_RUN"
        or post_r12_attempt_10.get("retry_count") != 0
        or post_r12_attempt_10.get("fallback_count") != 0
        or attempt_10_hygiene.get("status") != "PASS"
        or attempt_10_hygiene.get("all_runtime_value_match_file_count") != 0
        or attempt_10_hygiene.get("recognized_credential_pattern_match_file_count") != 0
        or attempt_10_hygiene.get("scan_error_count") != 0
    ):
        print("FAIL: immutable post-R12 attempt 10 history drifted")
        return False
    attempt_11_call = post_r14_attempt_11.get("calls", [{}])[0]
    attempt_11_hygiene = post_r14_attempt_11.get("runtime_value_hygiene", {})
    if (
        post_r14_attempt_11.get("source_commit") != "a8800c1c5143743f23903cdc84f2fe2390d55604"
        or post_r14_attempt_11.get("receipt_digest")
        != "sha256:72cc8eb4d076fe2d25fa8aabdbc23b4a69b865aaa492f30a6849be6f72d4c0b0"
        or post_r14_attempt_11.get("attempted_top_level_launches") != 1
        or post_r14_attempt_11.get("failing_call_id") != "smoke-1-model-gpt56-relay-responses"
        or post_r14_attempt_11.get("failure_category") != "PROVIDER_FAILURE"
        or attempt_11_call.get("provider_failure") != "timeout"
        or attempt_11_call.get("timeout_phase") != "read"
        or attempt_11_call.get("latency_ms") != 90405
        or attempt_11_call.get("attempt_count") != 1
        or attempt_11_call.get("observed_model") is not None
        or attempt_11_call.get("outcome") != "provider_error"
        or attempt_11_call.get("verifier") != "NOT_RUN"
        or "read_timeout_stage" in attempt_11_call
        or post_r14_attempt_11.get("calls_2_to_8") != "NOT_RUN"
        or post_r14_attempt_11.get("retry_count") != 0
        or post_r14_attempt_11.get("fallback_count") != 0
        or attempt_11_hygiene.get("status") != "PASS"
        or attempt_11_hygiene.get("all_runtime_value_match_file_count") != 0
        or attempt_11_hygiene.get("recognized_credential_pattern_match_file_count") != 0
        or attempt_11_hygiene.get("scan_error_count") != 0
    ):
        print("FAIL: immutable post-R14 attempt 11 history drifted")
        return False
    attempt_12_call = post_r15_attempt_12.get("calls", [{}])[0]
    attempt_12_hygiene = post_r15_attempt_12.get("runtime_value_hygiene", {})
    if (
        post_r15_attempt_12.get("source_commit") != "8d87c641e847c1b3bd0d53a96ef2655ed102d2d4"
        or post_r15_attempt_12.get("receipt_digest")
        != "sha256:056d49742d72366cdc630651563846aa15f3eee00d961bbbc3c98c9e9bc5f0a3"
        or post_r15_attempt_12.get("attempted_top_level_launches") != 1
        or post_r15_attempt_12.get("failing_call_id") != "smoke-1-model-gpt56-relay-responses"
        or post_r15_attempt_12.get("failure_category") != "PROVIDER_FAILURE"
        or attempt_12_call.get("provider_failure") != "timeout"
        or attempt_12_call.get("timeout_phase") != "read"
        or attempt_12_call.get("read_timeout_stage") != "waiting_for_response_headers"
        or attempt_12_call.get("latency_ms") != 90358
        or attempt_12_call.get("attempt_count") != 1
        or attempt_12_call.get("observed_model") is not None
        or attempt_12_call.get("outcome") != "provider_error"
        or attempt_12_call.get("verifier") != "NOT_RUN"
        or attempt_12_call.get("evidence_digest")
        != "sha256:18a15e9166a2848b4cab24cd04f710268d581c2c973718c2f31de4babe19c687"
        or post_r15_attempt_12.get("calls_2_to_8") != "NOT_RUN"
        or post_r15_attempt_12.get("retry_count") != 0
        or post_r15_attempt_12.get("fallback_count") != 0
        or attempt_12_hygiene.get("status") != "PASS"
        or attempt_12_hygiene.get("all_runtime_value_match_file_count") != 0
        or attempt_12_hygiene.get("recognized_credential_pattern_match_file_count") != 0
        or attempt_12_hygiene.get("scan_error_count") != 0
        or "predates direct-provider transport-phase tracing"
        not in " ".join(post_r15_attempt_12.get("limitations", ()))
        or "NOT_DETERMINED" not in " ".join(post_r15_attempt_12.get("limitations", ()))
    ):
        print("FAIL: immutable post-R15 attempt 12 history drifted")
        return False
    if (
        snapshot.get("provider_provenance") != "THIRD_PARTY_INFERENCE_PLATFORM"
        or snapshot.get("fixed_base_url") != "https://opencode.ai/zen/go"
        or snapshot.get("live_model_probe_performed") is not False
        or snapshot.get("judge_thinking_control") != "PROVIDER_DEFAULT_NOT_EXPLICITLY_CONFIGURED"
    ):
        print("FAIL: OpenCode Go official route snapshot drifted")
        return False
    if (
        smoke.release_plan_digest != plan.digest
        or len(plan.selected_profiles) != 8
        or {item.profile_id for item in smoke.calls}
        != {item.profile_id for item in plan.selected_profiles}
    ):
        print("FAIL: K-B0 smoke/release profile binding drifted")
        return False
    tag = subprocess.run(
        ("git", "tag", "--list", "v1.0.0-core"),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if tag:
        print("FAIL: v1.0.0-core exists before final release authorization")
        return False
    print(f"CORE_CORPUS={len(checked.tasks)} digest={checked.digest} PASS")
    print(f"SELECTED_PROVIDER_PROFILES={len(plan.selected_profiles)} CONFIGURED_NOT_SMOKED PASS")
    for state_name in (
        "MODEL_GPT56_RELAY_PROFILE",
        "MODEL_QWEN38_OPENCODE_GO_PROFILE",
        "MODEL_DEEPSEEK_V4PRO_PROFILE",
        "CODEX_GPT56_MEDIUM",
        "CODEX_GPT56_HIGH",
        "CLAUDE_QWEN38",
        "DEEPSEEK_E1_V4FLASH",
        "JUDGE_GLM52",
    ):
        print(f"{state_name}=CONFIGURED_NOT_SMOKED")
    print(
        f"REAL_MATRIX_PLAN={len(plan.cells)} cells x {plan.preflight.task_count} tasks "
        f"x {plan.preflight.repeat_count} repeats PASS"
    )
    print("PAIRED_LANE=CONFIGURED_NOT_VERIFIED; ComparabilityEngine smoke evidence required")
    print("CONTROLLED_ABLATION=CONFIGURED_NOT_RUN; reasoning_effort is sole treatment")
    try:
        proxy_image = asyncio.run(EgressProxyRuntime().ensure_image())
        network = asyncio.run(preflight_egress_network_isolation())
    except Exception as exc:
        print(f"FAIL: egress security attestation unavailable: {type(exc).__name__}")
        return False
    print(
        "K_B1_SMOKE_CONTROL_PLANE=PASS; command='harnesslab release smoke preflight'; "
        f"plan_digest={smoke_control.smoke_plan_digest}"
    )
    print("K_B1_SMOKE_PLAN=8 top-level calls; output ceiling=14256; FROZEN_PLAN_DRIFT=NONE")
    print("OPENCODE_GO_ROUTE_CONTRACT=PASS")
    print("OPENCODE_GO_CREDENTIAL_TRANSPORT=PASS")
    print("OPENCODE_GO_PROVENANCE=PASS")
    print("V1_HISTORY_PRESERVED=PASS")
    print("V2_SMOKE_PLAN=8_CALLS_14256_TOKENS")
    print("V2_HISTORY_PRESERVED=PASS")
    print(f"V3_RELEASE_PLAN=PASS digest={v3_plan.digest}")
    print(f"V3_SMOKE_PLAN=PASS digest={v3_smoke.digest}")
    print(f"V3_MATRIX_PLAN=PASS digest={v3_matrix_receipt.experiment_plan_digest}")
    print("V3_MATRIX_LOGICAL_RUNS=630")
    print(f"V3_MATRIX_CANARY_SELECTION=7_EXISTING_SLOTS digest={v3_canary_digest}")
    print(f"V3_MATRIX_PILOT_SELECTION=21_EXISTING_SLOTS digest={v3_pilot_digest}")
    print(f"EGRESS_PROXY_BASE={EGRESS_PROXY_BASE}")
    print(f"EGRESS_PROXY_IMAGE={EGRESS_PROXY_IMAGE}")
    print(f"EGRESS_PROXY_IMAGE_ID={proxy_image.image_id}")
    print(f"INTERNAL_NETWORK_DRIVER={network.driver}")
    print(f"INTERNAL_NETWORK_INTERNAL={str(network.internal).lower()}")
    print(f"INTERNAL_NETWORK_IPV6={str(network.enable_ipv6).lower()}")
    print(f"INTERNAL_NETWORK_GATEWAY_MODE_IPV4={network.gateway_mode_ipv4}")
    print("HOST_GATEWAY_BYPASS=DENIED")
    print("SUBJECT_PROXY_REACHABILITY=PASS")
    print("DIRECT_PUBLIC_BYPASS=DENIED")
    print("VERIFIER_NETWORK=none")
    print("EGRESS_PROXY_SECURITY_ATTESTATION=PASS; LOCAL_DOCKER_BYPASS_DENIAL=PASS")
    print("DEEPSEEK_E2=DEFERRED_NOT_VERIFIED")
    print("FAKE_KEYLESS_CONTRACT_EVIDENCE=PASS; REAL_RELEASE_EVIDENCE=NOT_VERIFIED")
    print("V2_SMOKE_TIMEOUT_CHANGE=FALSE")
    print("V3_SUBJECT_TIMEOUT_SECONDS=180")
    print("V3_JUDGE_TIMEOUT_SECONDS=90")
    print("V2_SMOKE_PLAN_DRIFT=NONE")
    print("V2_RELEASE_PLAN_DRIFT=NONE")
    print("REAL_CALLS_THIS_REPAIR=0")
    print("REAL_CALLS_SO_FAR=0")
    print("OUTPUT_BUDGET_TRUNCATION_SEMANTICS=PASS")
    print("V2_REAL_ATTEMPT_1_TOP_LEVEL_LAUNCHES=2")
    print("V2_REAL_ATTEMPT_2_TOP_LEVEL_LAUNCHES=4")
    print("POST_R4_SMOKE_HISTORY_PRESERVED=PASS")
    print("POST_R5_SMOKE_HISTORY_PRESERVED=PASS")
    print("POST_R6_SMOKE_HISTORY_PRESERVED=PASS")
    print("POST_R7_SMOKE_HISTORY_PRESERVED=PASS")
    print("POST_R9_ATTEMPT_6_HISTORY=PRESERVED")
    print("POST_R9_ATTEMPT_7_HISTORY=PRESERVED")
    print("POST_R10_ATTEMPT_8_HISTORY=PRESERVED")
    print("POST_R11_ATTEMPT_9_HISTORY=PRESERVED")
    print("POST_R12_ATTEMPT_10_HISTORY=PRESERVED")
    print("POST_R14_ATTEMPT_11_HISTORY=PRESERVED")
    print("POST_R15_ATTEMPT_12_HISTORY=PRESERVED")
    print("ATTEMPT_13_HISTORY=PRESERVED")
    print("ATTEMPT_13_DIAGNOSTIC=SEPARATE_NON_PROMOTABLE")
    print(f"V2_RELEASE_HISTORY=ATTEMPTS_1_TO_{len(v2_histories)}_CURRENT")
    print("POST_R12_REAL_CLAUDE_SMOKE=NOT_RUN_NOT_REACHED")
    print("GPT_RELAY_READ_TIMEOUT_HISTORY=ATTEMPTS_3_6_10_11_12")
    print("GPT_RELAY_READ_TIMEOUT_ROOT_CAUSE=NOT_DETERMINED")
    print("SMOKE_CAPABILITY_TIMEOUT_CONTINUES=PASS")
    print("SMOKE_SUBJECT_COMMAND_FAILURE_CONTINUES=PASS")
    print("SMOKE_INFRA_TIMEOUT_STOPS=PASS")
    print("SMOKE_NULL_OBSERVED_MODEL_ON_BUDGET_EXHAUSTION=PASS")
    print("R8_LEGACY_LANDLOCK_WORKSPACE_WRITE=REJECTED_BY_PINNED_0_149_0")
    print("CODEX_STARTUP_FAILURE_EVIDENCE=PASS")
    print("CODEX_EARLY_EXIT_PHASE_CLASSIFICATION=PASS")
    print("CODEX_STARTUP_SECRET_HYGIENE=PASS")
    print("CODEX_CLEANUP_INVARIANT=PASS")
    print("DYNAMIC_ENDPOINT_EVIDENCE_HYGIENE=PASS")
    print("GPT_RELAY_BASE_URL_VALUE_PERSISTENCE=DENIED")
    print("SAFE_PROVIDER_ROUTE_IDENTITY=PASS")
    print("CODEX_RUNTIME_URL_ARGV_HYGIENE=PASS")
    print("CODEX_RUNTIME_CONFIG_VALUE_PERSISTENCE=DENIED")
    print("CODEX_AMBIENT_CONFIG_ISOLATION=PASS")
    print("CODEX_GENERATED_PROFILE_LOAD=PASS")
    print("CODEX_CUSTOM_PROVIDER_SELECTED=PASS")
    print("CODEX_CUSTOM_PROVIDER_WEBSOCKET=DISABLED")
    print("CODEX_RELAY_CONNECT_TARGET_BINDING=PASS")
    print("CODEX_AMBIENT_USER_CONFIG_ISOLATION=PASS")
    print("CODEX_RUNTIME_URL_CHILD_ENV=ABSENT")
    print("EGRESS_PROXY_POLICY_UNCHANGED=PASS")
    print("CODEX_FILESYSTEM_ENFORCEMENT=OUTER_DOCKER")
    print("CODEX_INNER_FILESYSTEM_POLICY=UNRESTRICTED")
    print("CODEX_INNER_NETWORK_POLICY=DENY")
    print("CODEX_INNER_NETWORK_ENFORCEMENT=SECCOMP")
    print("CODEX_BWRAP_DEPENDENCY=ABSENT")
    print("CODEX_PINNED_SHELL_EXECUTION=PASS")
    print("CODEX_EFFECTIVE_WORKSPACE_WRITE=PASS")
    print("CODEX_TOOL_NETWORK=DENIED")
    print("CODEX_OUTER_DOCKER_SECURITY=PASS")
    print("P_LANE_EFFECTIVE_NETWORK_CONTROL=PASS")
    print("CORE_RELEASE_READY=FALSE")
    print("REAL_EVIDENCE_AUTHORIZATION_REQUIRED=TRUE")
    print("PHASE_K_B1_R6_RUNTIME_CONFIGURATION_EVIDENCE_IDENTITY_SEPARATION_KEYLESS")
    print("PHASE_K_B1_R7_CODEX_GENERATED_PROVIDER_PROFILE_ACTIVATION_KEYLESS")
    for key, state in sorted(evidence.real_statuses.items()):
        print(f"{key}={state.value}")
    print("v1.0.0-core=ABSENT")
    return True


async def verify_final_release(
    database_url: str | None, artifact_root_raw: str | None, github_run_id: str | None
) -> bool:
    try:
        checked = load_core_corpus(ROOT / "release/core-corpus.json")
        rebuilt = build_corpus_manifest(ROOT)
        plan = load_real_evidence_plan(ROOT / "release/core-real-evidence-plan.json")
        manifest = load_release_evidence(ROOT / "release/release-evidence.json")
        claims = load_resume_claim_map(ROOT / "release/resume-claim-evidence.json")
        badcases = load_badcase_plan(ROOT / "release/badcases.json")
        if not database_url or not artifact_root_raw or not github_run_id:
            raise CoreReleaseError(
                "--database-url, --artifact-root, and --github-run-id are required"
            )
        local_head = subprocess.run(
            ("git", "rev-parse", "HEAD"), cwd=ROOT, check=True, capture_output=True, text=True
        ).stdout.strip()
        if not manifest.judge_report.identity or not manifest.judge_report.identity.startswith(
            "judge-report:"
        ):
            raise CoreReleaseError("judge_report must identify judge-report:<calibration-id>")
        calibration_id = manifest.judge_report.identity.removeprefix("judge-report:")
        snapshot = await resolve_authoritative_snapshot(
            database_url,
            (Path(artifact_root_raw),),
            experiment_id=plan.experiment_id,
            calibration_id=calibration_id,
        )
        ci = resolve_github_ci(github_run_id)
        receipt = verify_semantic_final_release(
            repository_root=ROOT,
            checked_corpus=checked,
            rebuilt_corpus=rebuilt,
            release_plan=plan,
            manifest=manifest,
            claims=claims,
            badcases=badcases,
            snapshot=snapshot,
            ci=ci,
            local_head=local_head,
        )
        if not tag_creation_authorized(manifest, receipt):
            raise CoreReleaseError("semantic receipt did not authorize tag creation")
    except (
        CoreReleaseError,
        OSError,
        SQLAlchemyError,
        subprocess.SubprocessError,
        ValueError,
    ) as exc:
        print(f"NOT_VERIFIED: final release refused: {exc}")
        print("CORE_RELEASE_READY=FALSE")
        return False
    print("CORE_RELEASE_READY=TRUE")
    print(f"SEMANTIC_RELEASE_RECEIPT={receipt.release_manifest_digest}")
    print("TAG_CREATION_AUTHORIZED=TRUE")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="HarnessLab Phase K release verifier")
    parser.add_argument("--final-release", action="store_true")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--artifact-root")
    parser.add_argument("--github-run-id")
    arguments = parser.parse_args()
    if arguments.final_release:
        return (
            0
            if asyncio.run(
                verify_final_release(
                    arguments.database_url, arguments.artifact_root, arguments.github_run_id
                )
            )
            else 2
        )
    JUNIT.unlink(missing_ok=True)
    checks = (
        Check(
            "Gate K focused contract tests",
            (
                "uv",
                "run",
                "--locked",
                "pytest",
                "tests/test_release_contracts.py",
                "tests/test_release_semantic_verifier.py",
                "tests/test_phase_kb0.py",
                "tests/test_phase_kb0_review.py",
                "tests/test_phase_k_fast.py",
                "tests/test_phase_k_fast_2.py",
                "tests/test_runtime_config_hygiene.py",
                f"--junitxml={JUNIT}",
                "-q",
            ),
        ),
        Check(
            "Fresh setup contract",
            ("uv", "run", "--locked", "python", "scripts/verify_fresh_setup.py"),
        ),
        Check("Ruff lint", ("uv", "run", "--locked", "ruff", "check", ".")),
        Check("Ruff format", ("uv", "run", "--locked", "ruff", "format", "--check", ".")),
        Check("Mypy", ("uv", "run", "--locked", "mypy", "src", "tests", "scripts")),
        Check("Git whitespace", ("git", "diff", "--check")),
    )
    for check in checks:
        if not run(check):
            return 1
    return 0 if verify_junit() and verify_contract_mode() else 1


if __name__ == "__main__":
    sys.exit(main())
