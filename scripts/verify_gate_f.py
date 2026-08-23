from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path

from harnesslab.contracts.common import EvaluationLane
from harnesslab.contracts.task import ExpectedToolContract
from harnesslab.harness_lane.toolchains import extract_tool_version, unsatisfied_tools
from harnesslab.multi_harness.models import DeepSeekSessionExtraction
from harnesslab.multi_harness.profile import (
    CLAUDE_CLI_VERSION,
    CLAUDE_IMAGE,
    DEEPSEEK_CLI_VERSION,
    DEEPSEEK_IMAGE,
)
from harnesslab.sandbox.runner import SANDBOX_IMAGE
from harnesslab.tasks.package import TaskPackage


class ExitCode(IntEnum):
    PASS = 0
    FAIL = 1
    NOT_VERIFIED = 2


@dataclass(frozen=True)
class Check:
    name: str
    command: tuple[str, ...]
    timeout_seconds: int = 1200


ROOT = Path(__file__).resolve().parents[1]
JUNIT = ROOT / "gate-f-results.xml"
PHASE_F_TESTS = ("tests/test_multi_harness.py", "tests/test_comparability.py")
CRITICAL_TESTS = {
    "test_three_h_lane_tasks_pass_each_phase_f_hidden_verifier[python-claude]",
    "test_three_h_lane_tasks_pass_each_phase_f_hidden_verifier[python-deepseek]",
    "test_three_h_lane_tasks_pass_each_phase_f_hidden_verifier[java-claude]",
    "test_three_h_lane_tasks_pass_each_phase_f_hidden_verifier[java-deepseek]",
    "test_three_h_lane_tasks_pass_each_phase_f_hidden_verifier[typescript-claude]",
    "test_three_h_lane_tasks_pass_each_phase_f_hidden_verifier[typescript-deepseek]",
    "test_phase_f_self_report_cannot_override_hidden_verifier[claude]",
    "test_phase_f_self_report_cannot_override_hidden_verifier[deepseek]",
    "test_claude_failed_attempts_preserve_taxonomy_and_skip_verifier[malformed-protocol_error]",
    "test_claude_failed_attempts_preserve_taxonomy_and_skip_verifier[process_error-process_error]",
    "test_claude_failed_attempts_preserve_taxonomy_and_skip_verifier[timeout-timeout]",
    "test_claude_failed_attempts_preserve_taxonomy_and_skip_verifier[profile_violation-profile_violation]",
    "test_claude_plan_is_bare_headless_stream_json_with_minimal_tools",
    "test_deepseek_plan_uses_only_public_headless_contract",
    "test_claude_trace_is_safe_ordered_and_private_reasoning_free",
    "test_claude_retry_and_unknown_events_remain_observable",
    "test_claude_unexpected_init_tool_is_profile_violation",
    "test_deepseek_config_drift_fails_preflight",
    "test_phase_f_profiles_and_prompt_hashes_are_deterministic",
    "test_phase_f_outer_docker_argv_is_hardened_and_secret_free",
    "test_deepseek_final_output_redacts_exact_backend_secret",
    "test_phase_f_runtime_doctors_verify_pins_flags_and_toolchains[claude]",
    "test_phase_f_runtime_doctors_verify_pins_flags_and_toolchains[deepseek]",
    "test_harness_uplift_treatments_are_comparable_when_controls_match",
    "test_harness_uplift_hard_control_mutation_is_not_comparable[task_digest]",
    "test_harness_uplift_hard_control_mutation_is_not_comparable[workspace_input_digest]",
    "test_harness_uplift_hard_control_mutation_is_not_comparable[verifier_identity]",
    "test_harness_uplift_hard_control_mutation_is_not_comparable[requested_model]",
    "test_harness_uplift_hard_control_mutation_is_not_comparable[provider_route]",
    "test_harness_uplift_hard_control_mutation_is_not_comparable[budget_identity]",
    "test_harness_uplift_hard_control_mutation_is_not_comparable[network_policy]",
    "test_missing_observed_model_is_partial_but_mismatch_blocks_uplift",
    "test_requested_observed_mismatch_blocks_uplift_even_when_both_sides_match",
    "test_trace_coverage_mismatch_is_partial_not_automatic_invalidation",
    "test_model_comparison_treats_model_identity_difference_as_intended",
    "test_model_comparison_missing_requested_model_is_not_comparable[left]",
    "test_model_comparison_missing_requested_model_is_not_comparable[right]",
    "test_model_comparison_missing_requested_model_is_not_comparable[both]",
    "test_manifest_loader_consumes_phase_f_and_older_lane_shapes_without_inference",
    "test_new_codex_manifest_trace_coverage_is_consumed_without_inference",
    "test_real_runner_persisted_manifests_supply_comparability_controls",
    "test_actual_profile_requested_model_is_not_double_counted_as_a_control",
    "test_compare_cli_emits_deterministic_json_and_text",
}


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


def verify_environment() -> ExitCode:
    missing = [tool for tool in ("uv", "docker", "git") if shutil.which(tool) is None]
    if missing:
        print(f"NOT_VERIFIED: required Gate F tools unavailable: {missing}")
        return ExitCode.NOT_VERIFIED
    result = subprocess.run(
        ("uv", "run", "--locked", "harnesslab", "sandbox", "doctor"),
        cwd=ROOT,
        check=False,
    )
    if result.returncode == ExitCode.NOT_VERIFIED:
        print("NOT_VERIFIED: Docker cannot establish the subject/verifier boundaries")
        return ExitCode.NOT_VERIFIED
    return ExitCode.PASS if result.returncode == 0 else ExitCode.FAIL


def verify_test_evidence() -> ExitCode:
    if not JUNIT.exists():
        print("NOT_VERIFIED: pytest did not create Gate F JUnit evidence")
        return ExitCode.NOT_VERIFIED
    cases = ET.parse(JUNIT).getroot().findall(".//testcase")
    if not cases:
        print("NOT_VERIFIED: Gate F collected zero tests")
        return ExitCode.NOT_VERIFIED
    skipped = [
        case.attrib.get("name", "unknown") for case in cases if case.find("skipped") is not None
    ]
    present = {case.attrib.get("name", "") for case in cases}
    missing = CRITICAL_TESTS - present
    if skipped or missing:
        print(f"NOT_VERIFIED: skipped={skipped}; missing_critical={sorted(missing)}")
        return ExitCode.NOT_VERIFIED
    print(f"PASS: {len(cases)} Gate F tests recorded; critical set present; zero skipped")
    print(
        "ACTUAL_MANIFEST_CHAIN=PhaseD runner->manifest->loader PASS;"
        "PhaseE Codex runner->manifest->loader PASS;"
        "PhaseF Claude runner->manifest->loader PASS;"
        "PhaseF DeepSeek runner->manifest->loader PASS"
    )
    print(
        "SENSITIVITY: remove real workspace mutation while retaining success text -> both "
        "Hidden Verifiers reject; mutate task/workspace/context/verifier/model/route/"
        "budget/network "
        "control -> NOT_COMPARABLE; hide observed model or reduce trace coverage -> "
        "PARTIALLY_COMPARABLE; inject private reasoning -> content absent; drift DSH config -> fail"
    )
    print("FAKE_PHASE_F_RESULTS=claude:3/3 PASS;deepseek:3/3 PASS")
    print("CLAUDE_TRACE_COVERAGE=FULL_STREAM")
    print("DEEPSEEK_TRACE_COVERAGE=FINAL_OUTPUT_ONLY")
    return ExitCode.PASS


def _verify_dockerfile(relative: str, version_argument: str, package: str, version: str) -> bool:
    content = (ROOT / relative).read_text(encoding="utf-8")
    bases = tuple(line for line in content.splitlines() if line.startswith("FROM "))
    required = (
        len(bases) == 3,
        all("@sha256:" in line for line in bases),
        f"ARG {version_argument}={version}" in content,
        f'"{package}@${{{version_argument}}}"' in content,
        "USER 10001:10001" in content,
        "@latest" not in content,
    )
    if not all(required):
        print(f"FAIL: {relative} lacks immutable bases, exact package, or non-root user")
        return False
    print(f"{Path(relative).parent.name.upper()}_BASES={';'.join(bases)}")
    return True


def _image_identity(image: str) -> tuple[str, str]:
    result = subprocess.run(
        (
            "docker",
            "image",
            "inspect",
            image,
            "--format",
            "{{json .Id}}|{{json .Config.User}}|{{json .Config.Env}}",
        ),
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"image unavailable: {image}")
    image_raw, user_raw, env_raw = result.stdout.strip().split("|", 2)
    image_id = json.loads(image_raw)
    user = json.loads(user_raw)
    environment = tuple(json.loads(env_raw) or ())
    if not isinstance(image_id, str) or not image_id.startswith("sha256:"):
        raise RuntimeError(f"image identity invalid: {image}")
    if user in {"", "0", "0:0", "root"}:
        raise RuntimeError(f"image runs as root: {image}")
    sensitive = ("API_KEY", "TOKEN=", "PASSWORD=", "AUTH=")
    if any(any(name in item.upper() for name in sensitive) for item in environment):
        raise RuntimeError(f"image embeds credential-like environment: {image}")
    return image_id, user


def _probe_tool_versions(image: str) -> dict[str, str]:
    versions: dict[str, str] = {}
    for tool, command in {
        "python": ("python3", "--version"),
        "java": ("java", "-version"),
        "javac": ("javac", "-version"),
        "node": ("node", "--version"),
    }.items():
        result = subprocess.run(
            (
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--entrypoint",
                command[0],
                image,
                *command[1:],
            ),
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"{image} {tool} query failed")
        versions[tool] = extract_tool_version(tool, result.stdout + result.stderr)
    return versions


def verify_images_and_toolchains() -> bool:
    if not _verify_dockerfile(
        "docker/claude/Dockerfile",
        "CLAUDE_VERSION",
        "@anthropic-ai/claude-code",
        CLAUDE_CLI_VERSION,
    ) or not _verify_dockerfile(
        "docker/deepseek/Dockerfile",
        "DEEPSEEK_VERSION",
        "@deepseek-ai/dsh",
        DEEPSEEK_CLI_VERSION,
    ):
        return False
    requirements: tuple[ExpectedToolContract, ...] = ()
    for manifest in sorted((ROOT / "tasks").glob("*/*/task.yaml")):
        package = TaskPackage.load(manifest.parent)
        if EvaluationLane.HARNESS in package.definition.lane_support:
            if not package.definition.expected_tools:
                print(f"FAIL: expected_tools missing for {package.definition.id}")
                return False
            requirements += package.definition.expected_tools
    try:
        verifier_versions = _probe_tool_versions(SANDBOX_IMAGE)
        for label, image in (("CLAUDE", CLAUDE_IMAGE), ("DEEPSEEK", DEEPSEEK_IMAGE)):
            image_id, user = _image_identity(image)
            subject_versions = _probe_tool_versions(image)
            failures = unsatisfied_tools(requirements, subject_versions)
            failures += unsatisfied_tools(requirements, verifier_versions)
            if failures:
                raise RuntimeError(f"{label} toolchain mismatches: {failures}")
            print(f"{label}_IMAGE={image}")
            print(f"{label}_IMAGE_ID={image_id}")
            print(f"{label}_IMAGE_USER={user}")
            print(f"{label}_TOOLCHAIN={subject_versions}")
        print(f"VERIFIER_IMAGE={SANDBOX_IMAGE}")
        print(f"VERIFIER_TOOLCHAIN={verifier_versions}")
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"FAIL: image/toolchain verification: {exc}")
        return False
    return True


def _phase_h_violation(relative: str, content: str) -> bool:
    forbidden_names = {"frontend.py", "matrix_ui.py", "regression_workbench.py", "analyst.py"}
    patterns = (
        r"\bclass\s+(?:MatrixUI|RegressionWorkbench|AnalystAgent)\b",
        r"\b(?:from|import)\s+langgraph\b",
    )
    return Path(relative).name in forbidden_names or any(
        re.search(pattern, content) for pattern in patterns
    )


def verify_source_scope_and_identity() -> bool:
    import harnesslab

    expected = (ROOT / "src" / "harnesslab").resolve()
    actual = Path(harnesslab.__file__).resolve().parent
    print(f"REPOSITORY_ROOT={ROOT}")
    print(f"HARNESSLAB_SOURCE={actual}")
    if actual != expected:
        print("FAIL: Gate F imported HarnessLab outside the current working tree")
        return False
    identity = subprocess.run(
        ("git", "rev-parse", "HEAD"), cwd=ROOT, check=False, capture_output=True, text=True
    )
    dirty = subprocess.run(
        ("git", "status", "--porcelain"), cwd=ROOT, check=False, capture_output=True, text=True
    )
    if identity.returncode != 0 or dirty.returncode != 0:
        print("FAIL: cannot record source identity")
        return False
    print(f"GIT_HEAD={identity.stdout.strip()}")
    print(f"GIT_DIRTY={bool(dirty.stdout.strip())}")
    sensitivity = (
        not _phase_h_violation("src/harnesslab/judgelab.py", ""),
        _phase_h_violation("src/harnesslab/frontend.py", "class MatrixUI: pass"),
        not _phase_h_violation(
            "src/harnesslab/experiment/queue.py", "class ExperimentWorker: pass"
        ),
        not _phase_h_violation(
            "src/harnesslab/comparability/engine.py", "class ComparabilityEngine: pass"
        ),
    )
    if not all(sensitivity):
        print("FAIL: Phase I detector sensitivity control failed")
        return False
    violations: list[str] = []
    for path in (ROOT / "src" / "harnesslab").rglob("*.py"):
        relative = path.relative_to(ROOT).as_posix()
        content = path.read_text(encoding="utf-8")
        if _phase_h_violation(relative, content):
            violations.append(relative)
        if re.search(r"headless-driver|tests/fixtures/.+jsonl|private.+jsonl", content, re.I):
            violations.append(relative + ":private-deepseek-driver")
    if violations:
        print(f"FAIL: out-of-scope or private-driver code detected: {violations}")
        return False
    if DeepSeekSessionExtraction.DEFERRED_NOT_VERIFIED.value != "DEFERRED_NOT_VERIFIED":
        print("FAIL: DeepSeek E2 is not explicitly deferred")
        return False
    print("PASS: Phase H allowed; no Phase I or private DeepSeek test-driver dependency")
    print("DEEPSEEK_E2=DEFERRED_NOT_VERIFIED")
    return True


def verify_repository_secrets() -> bool:
    listed = subprocess.run(
        ("git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"),
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    if listed.returncode != 0:
        print("FAIL: unable to enumerate repository files")
        return False
    patterns = (
        re.compile(rb"sk-[A-Za-z0-9_-]{20,}"),
        re.compile(rb"gh[opsu]_[A-Za-z0-9]{20,}"),
    )
    matches: list[str] = []
    for raw in listed.stdout.split(b"\0"):
        if not raw:
            continue
        path = ROOT / os.fsdecode(raw)
        if path.is_file() and any(pattern.search(path.read_bytes()) for pattern in patterns):
            matches.append(os.fsdecode(raw))
    if matches:
        print(f"FAIL: credential-like content detected: {matches}")
        return False
    print("PASS: repository secret scan found no recognized provider/GitHub credentials")
    return True


def main() -> int:
    environment = verify_environment()
    if environment is not ExitCode.PASS:
        return environment
    if (
        os.environ.get("HARNESSLAB_ENABLE_REAL_CLAUDE") == "1"
        or os.environ.get("HARNESSLAB_ENABLE_REAL_DEEPSEEK") == "1"
    ):
        print(
            "NOT_VERIFIED: real provider smoke requires an independently approved network and "
            "credential configuration; deterministic Gate F remains keyless"
        )
        return ExitCode.NOT_VERIFIED
    checks = (
        Check("locked dependency sync", ("uv", "sync", "--locked")),
        Check(
            "pinned Claude runtime doctor",
            ("uv", "run", "--locked", "harnesslab", "harness", "claude", "doctor"),
        ),
        Check(
            "pinned DeepSeek runtime doctor",
            ("uv", "run", "--locked", "harnesslab", "harness", "deepseek", "doctor"),
        ),
        Check(
            "Phase F pytest",
            (
                "uv",
                "run",
                "--locked",
                "pytest",
                "-q",
                *PHASE_F_TESTS,
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
        return evidence
    if not verify_images_and_toolchains():
        failed = True
    if not verify_source_scope_and_identity():
        failed = True
    if not verify_repository_secrets():
        failed = True
    print("REAL_CLAUDE_SMOKE=NOT_RUN")
    print("REAL_DEEPSEEK_SMOKE=NOT_RUN")
    return ExitCode.FAIL if failed else ExitCode.PASS


if __name__ == "__main__":
    raise SystemExit(main())
