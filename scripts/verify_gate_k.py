from __future__ import annotations

import argparse
import asyncio
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
    load_core_corpus,
    load_real_evidence_plan,
    load_real_smoke_plan,
    load_release_evidence,
    load_resume_claim_map,
    tag_creation_authorized,
    validate_keyless_contract_state,
)
from harnesslab.release.final_verifier import (
    resolve_authoritative_snapshot,
    resolve_github_ci,
    verify_semantic_final_release,
)
from harnesslab.release.models import EvidenceState
from harnesslab.release.smoke import SmokeControlPlane

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
    "test_kb0_claude_qwen_uses_only_explicit_bailian_environment",
    "test_kb0_provider_scoped_egress_allows_fake_and_denies_bypass_and_targets",
    "test_kb0_subject_docker_uses_only_internal_proxy_network",
    "test_kb0_pair_is_configured_but_never_claims_comparable_or_uplift",
    "test_kb0_smoke_plan_is_exact_bounded_and_unexecuted",
    "test_kb0_matrix_preflight_and_release_hard_stop_are_unchanged",
    "test_smoke_production_control_plane_exact_eight_call_binding",
    "test_smoke_dry_run_preflight_performs_zero_provider_invocations",
    "test_smoke_same_path_fake_execution_consumes_exact_plan_without_network",
    "test_smoke_missing_config_stops_before_first_call",
    "test_smoke_abort_on_first_failure_never_invokes_calls_four_through_eight",
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
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
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
            "release/release-evidence.json",
            "release/resume-claim-evidence.json",
        )
    )
    secret_patterns = (r"sk-[A-Za-z0-9_-]{20,}", r"(?i)bearer\s+[A-Za-z0-9._-]{20,}")
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
        "MODEL_QWEN38_BAILIAN_PROFILE",
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
    print("K_B1_SMOKE_PLAN=8 top-level calls; output ceiling=14256; NOT_RUN")
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
    print("FAKE_KEYLESS_CONTRACT_EVIDENCE=PASS; REAL_RELEASE_EVIDENCE=NOT_RUN")
    print("REAL_EVALUATION_CALL_COUNT=0")
    print("CORE_RELEASE_READY=FALSE")
    print("REAL_EVIDENCE_AUTHORIZATION_REQUIRED=TRUE")
    print("PHASE_K_B0_DSH_OBSERVED_MODEL_FIXED_AWAITING_REAL_SMOKE_AUTHORIZATION")
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
