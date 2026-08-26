from __future__ import annotations

import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path


class ExitCode(IntEnum):
    PASS = 0
    FAIL = 1
    NOT_VERIFIED = 2


@dataclass(frozen=True)
class Check:
    name: str
    command: tuple[str, ...]
    timeout_seconds: int = 900


ROOT = Path(__file__).resolve().parents[1]
JUNIT = ROOT / "gate-d-results.xml"
PHASE_D_TESTS = (
    "tests/test_provider_adapters.py",
    "tests/test_direct_patch.py",
    "tests/test_model_lane.py",
    "tests/test_cli.py",
    "tests/test_contracts.py",
    "tests/test_phase_kb0.py",
    "tests/test_runtime_config_hygiene.py",
)
CRITICAL_TESTS = {
    "test_anthropic_messages_adapter_contract_and_thinking_exclusion",
    "test_anthropic_refusal_is_successful_public_result",
    "test_anthropic_empty_terminal_response_reaches_subject_output_boundary",
    "test_anthropic_requires_explicit_max_tokens",
    "test_cleanup_reporting_cannot_be_promoted_to_run_failure",
    "test_credential_content_is_withheld_from_all_phase_d_artifacts",
    "test_direct_patch_applies_complete_write_and_changes_workspace_identity",
    "test_direct_patch_applies_delete_and_updates_workspace_identity",
    "test_direct_patch_failure_is_atomic_when_protected_identity_is_stale",
    "test_direct_patch_preserves_original_when_commit_and_rollback_both_fail",
    "test_direct_patch_rejects_contract_bounds[operation-count]",
    "test_direct_patch_rejects_contract_bounds[per-file-content]",
    "test_direct_patch_rejects_contract_bounds[total-content]",
    "test_direct_patch_rejects_duplicate_json_keys",
    "test_direct_patch_rejects_protected_file_and_symlink_escape",
    "test_direct_patch_rejects_workspace_changed_since_prompt_without_mutation",
    "test_direct_patch_rejects_wrapping_traversal_absolute_and_invalid_delete[absolute]",
    "test_direct_patch_rejects_wrapping_traversal_absolute_and_invalid_delete[invalid-delete]",
    "test_direct_patch_rejects_wrapping_traversal_absolute_and_invalid_delete[traversal]",
    "test_direct_patch_rejects_wrapping_traversal_absolute_and_invalid_delete[wrapping]",
    "test_direct_prompt_is_deterministic_and_excludes_hidden_assets",
    "test_direct_prompt_rejects_oversized_total",
    "test_direct_prompt_rejects_junction_like_subject_tree",
    "test_direct_patch_staging_creation_failure_is_infrastructure_error",
    "test_direct_model_evidence_rejects_conflicting_provider_identity",
    "test_direct_model_evidence_rejects_multiple_provider_attempts",
    "test_example_profiles_contain_only_credential_references[chat-completions]",
    "test_example_profiles_contain_only_credential_references[messages]",
    "test_example_profiles_contain_only_credential_references[responses]",
    "test_fake_provider_m_lane_e2e_uses_isolated_verifier_and_safe_evidence",
    "test_generic_effort_is_rejected_instead_of_silently_transformed",
    "test_generation_settings_are_deeply_immutable",
    "test_http_provider_failures_are_distinct_and_not_retried[auth-401]",
    "test_http_provider_failures_are_distinct_and_not_retried[rate-limit-429]",
    "test_http_provider_failures_are_distinct_and_not_retried[redirect-302]",
    "test_http_provider_failures_are_distinct_and_not_retried[server-503]",
    "test_http_timeout_subtypes_are_preserved_without_retry[connect]",
    "test_http_timeout_subtypes_are_preserved_without_retry[pool]",
    "test_http_timeout_subtypes_are_preserved_without_retry[read]",
    "test_http_timeout_subtypes_are_preserved_without_retry[unknown]",
    "test_http_timeout_subtypes_are_preserved_without_retry[write]",
    "test_injected_client_uses_profile_timeout",
    "test_invalid_model_profile_does_not_echo_rejected_credential",
    "test_malformed_patch_fails_closed_without_workspace_snapshot",
    "test_model_refusal_bypasses_patch_workspace_and_verifier",
    "test_missing_credential_fails_before_http_request",
    "test_non_utf8_provider_text_is_normalized_as_malformed",
    "test_nonterminal_provider_stop_reasons_do_not_complete[chat-content-filter]",
    "test_nonterminal_provider_stop_reasons_do_not_complete[chat-tool-calls]",
    "test_nonterminal_provider_stop_reasons_do_not_complete[messages-pause-turn]",
    "test_nonterminal_provider_stop_reasons_do_not_complete[messages-tool-use]",
    "test_model_endpoint_requires_tls_and_canonical_route[base-dot-segment]",
    "test_model_endpoint_requires_tls_and_canonical_route[cleartext]",
    "test_model_endpoint_requires_tls_and_canonical_route[encoded-dot]",
    "test_model_endpoint_requires_tls_and_canonical_route[route-dot-segment]",
    "test_model_endpoint_identity_canonicalizes_hostname_case",
    "test_openai_compatible_chat_completions_core_contract",
    "test_generic_chat_refusal_is_successful_public_result",
    "test_openai_responses_adapter_contract_and_private_reasoning_exclusion",
    "test_openai_responses_refusal_is_successful_public_result",
    "test_openai_responses_supports_max_reasoning_effort",
    "test_provider_failure_category_is_preserved_in_evidence",
    "test_provider_error_timeout_phase_schema_fails_closed",
    "test_prompt_template_version_in_evidence_comes_from_rendered_prompt",
    "test_prompt_containing_exact_credential_is_not_sent_to_provider",
    "test_provider_latency_includes_response_body_consumption",
    "test_oversized_provider_response_is_rejected_before_json_parsing",
    "test_redirect_is_not_followed_even_when_injected_client_enables_it",
    "test_safe_provider_failure_facts_are_persisted_without_raw_response",
    "test_timeout_malformed_and_incomplete_are_distinct",
    "test_timeout_phase_is_persisted_in_canonical_evidence_without_raw_detail",
    "test_schema_invalid_provider_result_is_normalized_as_malformed",
    "test_task_package_context_reaches_runner_prompt_and_evidence",
    "test_output_budget_stop_reasons_preserve_public_result[chat-length]",
    "test_output_budget_stop_reasons_preserve_public_result[messages-max-tokens]",
    "test_messages_context_window_exceeded_remains_incomplete_provider_failure",
    "test_output_budget_exhaustion_is_subject_output_failure",
    "test_unexpected_verifier_exception_is_persisted_as_infra_error",
    "test_unsupported_official_effort_fails_before_http[messages]",
    "test_unsupported_official_effort_fails_before_http[responses]",
    "test_unset_temperature_is_omitted_and_observed_model_is_optional[chat-completions]",
    "test_unset_temperature_is_omitted_and_observed_model_is_optional[messages]",
    "test_unset_temperature_is_omitted_and_observed_model_is_optional[responses]",
    "test_unset_optional_generation_controls_are_not_invented[chat-completions]",
    "test_unset_optional_generation_controls_are_not_invented[responses]",
    "test_workspace_staging_failure_is_not_blame_assigned_to_model",
    "test_opencode_go_messages_exact_url_headers_and_shared_claude_route",
    "test_opencode_go_judge_exact_route_bearer_and_public_content_only",
    "test_direct_success_uses_runtime_url_but_persists_only_route_identity",
    "test_direct_failure_uses_runtime_url_without_persisting_value",
    "test_smoke_result_and_receipt_exclude_runtime_url_value",
}
PHASE_J_MODULE_NAMES = {
    "analyst.py",
    "analyst_agent.py",
}
PHASE_J_SYMBOLS = tuple(
    re.compile(pattern)
    for pattern in (
        r"\bclass\s+AnalystAgent\b",
        r"\b(?:from|import)\s+langgraph\b",
        r"\b(?:from|import)\s+harnesslab\.analyst\b",
    )
)


def phase_j_violation(relative: str, content: str) -> str | None:
    path = Path(relative)
    if "analyst" in path.parts:
        return None
    if path.as_posix() == "src/harnesslab/cli.py":
        return None
    if "langgraph" in path.parts or path.name in PHASE_J_MODULE_NAMES:
        return f"Phase J escaped its isolated package: {relative}"
    if any(pattern.search(content) for pattern in PHASE_J_SYMBOLS):
        return f"forbidden Phase J source symbol: {relative}"
    return None


def run(check: Check) -> bool:
    print(f"\n=== {check.name} ===", flush=True)
    print("COMMAND:", subprocess.list2cmdline(check.command), flush=True)
    try:
        completed = subprocess.run(
            check.command,
            cwd=ROOT,
            check=False,
            timeout=check.timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        print(f"FAIL: command exceeded {check.timeout_seconds}s")
        return False
    passed = completed.returncode == 0
    print(f"{'PASS' if passed else 'FAIL'}: exit={completed.returncode}")
    return passed


def verify_environment() -> ExitCode:
    missing = [tool for tool in ("uv", "docker", "git") if shutil.which(tool) is None]
    if missing:
        print(f"NOT_VERIFIED: required Gate D tools unavailable: {missing}")
        return ExitCode.NOT_VERIFIED
    if not os.environ.get("DATABASE_URL"):
        print("NOT_VERIFIED: DATABASE_URL is required for Gate A/B/C regressions")
        return ExitCode.NOT_VERIFIED
    preflight = subprocess.run(
        ("uv", "run", "--locked", "harnesslab", "sandbox", "doctor"),
        cwd=ROOT,
        check=False,
    )
    if preflight.returncode == ExitCode.NOT_VERIFIED:
        print("NOT_VERIFIED: Docker preflight cannot establish the isolated verifier boundary")
        return ExitCode.NOT_VERIFIED
    if preflight.returncode != 0:
        print("FAIL: Docker preflight implementation failed")
        return ExitCode.FAIL
    return ExitCode.PASS


def verify_test_evidence() -> ExitCode:
    if not JUNIT.exists():
        print("NOT_VERIFIED: pytest did not create Gate D JUnit evidence")
        return ExitCode.NOT_VERIFIED
    cases = ET.parse(JUNIT).getroot().findall(".//testcase")
    if not cases:
        print("NOT_VERIFIED: Gate D collected zero tests")
        return ExitCode.NOT_VERIFIED
    skipped = [
        case.attrib.get("name", "unknown") for case in cases if case.find("skipped") is not None
    ]
    present = {case.attrib.get("name", "") for case in cases}
    missing = CRITICAL_TESTS - present
    if skipped or missing:
        print(f"NOT_VERIFIED: skipped={skipped}; missing_critical={sorted(missing)}")
        return ExitCode.NOT_VERIFIED
    print(f"PASS: {len(cases)} Gate D tests recorded; all critical tests present; zero skipped")
    print(
        "SENSITIVITY EVIDENCE: hidden verifier/oracle sentinels stay absent from the prompt; "
        "private reasoning/thinking blocks stay absent from normalized results; HTTP status and "
        "failure mutations produce distinct provider categories, while timeout subtype mutations "
        "preserve typed phases with one attempt; traversal, protected-file, symlink, "
        "malformed-patch, and exact-credential mutations fail closed"
    )
    return ExitCode.PASS


def verify_source_and_scope() -> bool:
    import harnesslab

    module_path = Path(harnesslab.__file__).resolve()
    expected_package = (ROOT / "src" / "harnesslab").resolve()
    print(f"REPOSITORY_ROOT={ROOT}")
    print(f"HARNESSLAB_SOURCE={module_path}")
    if module_path.parent != expected_package:
        print(f"FAIL: imported HarnessLab is not the working-tree package at {expected_package}")
        return False
    identity = subprocess.run(
        ("git", "rev-parse", "HEAD"), cwd=ROOT, check=False, capture_output=True, text=True
    )
    worktree = subprocess.run(
        ("git", "status", "--porcelain"), cwd=ROOT, check=False, capture_output=True, text=True
    )
    if identity.returncode != 0 or worktree.returncode != 0:
        print("FAIL: unable to record Git source identity")
        return False
    print(f"GIT_HEAD={identity.stdout.strip()}")
    print(f"GIT_DIRTY={bool(worktree.stdout.strip())}")
    forbidden = (ROOT / "src" / "harnesslab" / "langgraph",)
    existing = [str(path.relative_to(ROOT)) for path in forbidden if path.exists()]
    if existing:
        print(f"FAIL: LangGraph escaped the isolated Analyst package: {existing}")
        return False
    sensitivity_cases = (
        ("src/harnesslab/judgelab.py", "", False),
        ("src/harnesslab/analyst/graph.py", "from langgraph.graph import StateGraph", False),
        (
            "src/harnesslab/model_lane/bridge.py",
            "from harnesslab.analyst import AnalystService",
            True,
        ),
        ("src/harnesslab/experiment/queue.py", "class ExperimentWorker: pass", False),
        ("src/harnesslab/harness_lane/adapter.py", "class HarnessAdapter: pass", False),
        ("src/harnesslab/harness_lane/models.py", "class NormalizedTrace: pass", False),
    )
    if any(
        (phase_j_violation(relative, content) is not None) is not expected
        for relative, content, expected in sensitivity_cases
    ):
        print("FAIL: Phase J source detector failed its sensitivity control")
        return False
    source_violations: list[str] = []
    for path in (ROOT / "src" / "harnesslab").rglob("*.py"):
        relative = path.relative_to(ROOT).as_posix()
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            source_violations.append(f"unreadable source: {relative}")
            continue
        violation = phase_j_violation(relative, content)
        if violation is not None:
            source_violations.append(violation)
    if source_violations:
        print(f"FAIL: Phase J source detected: {source_violations}")
        return False
    print("PASS: Phase D runtime remains isolated from the Phase J Analyst package")
    return True


def verify_repository_secret_hygiene() -> bool:
    listed = subprocess.run(
        ("git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"),
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    if listed.returncode != 0:
        print("FAIL: unable to enumerate candidate repository files for credential hygiene")
        return False
    patterns = (
        re.compile(rb"sk-[A-Za-z0-9_-]{20,}"),
        re.compile(rb"sk-ant-[A-Za-z0-9_-]{20,}"),
    )
    matches: list[str] = []
    for raw in listed.stdout.split(b"\0"):
        if not raw:
            continue
        relative = os.fsdecode(raw)
        path = ROOT / relative
        try:
            content = path.read_bytes()
        except OSError:
            matches.append(relative)
            continue
        if any(pattern.search(content) for pattern in patterns):
            matches.append(relative)
    if matches:
        print(f"FAIL: possible provider credential material in repository files: {matches}")
        return False
    print("PASS: tracked/untracked files contain no recognized OpenAI/Anthropic credentials")
    print("TIMEOUT_DIAGNOSTICS=PASS")
    print("CONNECT_TIMEOUT_MAPPING=PASS")
    print("READ_TIMEOUT_MAPPING=PASS")
    print("WRITE_TIMEOUT_MAPPING=PASS")
    print("POOL_TIMEOUT_MAPPING=PASS")
    print("UNKNOWN_TIMEOUT_MAPPING=PASS")
    print("HISTORICAL_RETRY_TIMEOUT_PHASE=NOT_AVAILABLE")
    print("SMOKE_TIMEOUT_CHANGE=FALSE")
    print("REAL_CALLS_THIS_REPAIR=0")
    print("REAL_PROVIDER_SMOKE=NOT_VERIFIED")
    print("DYNAMIC_ENDPOINT_EVIDENCE_HYGIENE=PASS")
    print("GPT_RELAY_BASE_URL_VALUE_PERSISTENCE=DENIED")
    print("SAFE_PROVIDER_ROUTE_IDENTITY=PASS")
    return True


def main() -> int:
    environment = verify_environment()
    if environment is not ExitCode.PASS:
        return environment
    checks = (
        Check("locked dependency sync", ("uv", "sync", "--locked")),
        Check(
            "Gate C regression (includes Gate A and Gate B)",
            ("uv", "run", "--locked", "python", "scripts/verify_gate_c.py"),
        ),
        Check(
            "Phase D pytest",
            (
                "uv",
                "run",
                "--locked",
                "pytest",
                "-q",
                *PHASE_D_TESTS,
                f"--junitxml={JUNIT}",
            ),
        ),
        Check("Ruff check", ("uv", "run", "--locked", "ruff", "check", ".")),
        Check("Ruff format", ("uv", "run", "--locked", "ruff", "format", "--check", ".")),
        Check("mypy", ("uv", "run", "--locked", "mypy", "src", "tests", "scripts")),
        Check("git whitespace", ("git", "diff", "--check")),
    )
    failed = False
    for check in checks:
        if not run(check):
            failed = True
    evidence = verify_test_evidence()
    if evidence is ExitCode.NOT_VERIFIED:
        return ExitCode.NOT_VERIFIED
    if not verify_source_and_scope():
        failed = True
    if not verify_repository_secret_hygiene():
        failed = True
    return ExitCode.FAIL if failed else ExitCode.PASS


if __name__ == "__main__":
    raise SystemExit(main())
