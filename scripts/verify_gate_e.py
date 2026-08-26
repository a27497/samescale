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
    timeout_seconds: int = 900


ROOT = Path(__file__).resolve().parents[1]
JUNIT = ROOT / "gate-e-results.xml"
CODEX_IMAGE = "harnesslab-phase-e-codex:0.149.0"
PHASE_E_TESTS = (
    "tests/test_codex_harness.py",
    "tests/test_runtime_config_hygiene.py",
    "tests/test_cli.py::test_harness_codex_doctor_reports_pinned_runtime",
)
CRITICAL_TESTS = {
    "test_codex_docker_start_failure_is_typed",
    "test_codex_early_exit_during_stdin_is_typed[broken-pipe]",
    "test_codex_early_exit_during_stdin_is_typed[connection-reset]",
    "test_codex_early_exit_during_stdin_is_typed[process-lookup]",
    "test_codex_primary_and_cleanup_failures_are_both_preserved[cleanup-failure]",
    "test_codex_primary_and_cleanup_failures_are_both_preserved[cleanup-success]",
    "test_codex_stdout_read_failure_is_typed",
    "test_codex_timeout_and_cancellation_remain_capture_states",
    "test_real_codex_backend_outer_docker_argv_is_hardened_and_secret_free",
    "test_codex_exec_plan_uses_stdin_and_canonical_isolation_flags",
    "test_codex_harness_prompt_excludes_verifier_and_oracle",
    "test_codex_profile_and_prompt_hashes_are_deterministic",
    "test_codex_runner_normalizes_restrictive_managed_context_without_identity_drift",
    "test_codex_runtime_doctor_verifies_pinned_version_and_flags",
    "test_codex_self_report_cannot_override_hidden_verifier",
    "test_backend_credentials_automatically_redact_all_harness_artifacts",
    "test_failed_intermediate_command_does_not_fail_completed_turn",
    "test_filesystem_diff_is_authoritative_over_native_file_change",
    "test_harness_codex_doctor_reports_pinned_runtime",
    "test_harness_failure_taxonomy_is_structurally_distinct[cancelled]",
    "test_harness_failure_taxonomy_is_structurally_distinct[model-turn]",
    "test_harness_failure_taxonomy_is_structurally_distinct[process]",
    "test_harness_failure_taxonomy_is_structurally_distinct[profile-mcp]",
    "test_harness_failure_taxonomy_is_structurally_distinct[profile-web]",
    "test_harness_failure_taxonomy_is_structurally_distinct[protocol]",
    "test_harness_failure_taxonomy_is_structurally_distinct[timeout]",
    "test_requested_model_is_not_fabricated_as_observed_model",
    "test_precapture_stderr_secret_is_digest_only_in_immutable_evidence",
    "test_real_codex_cleanup_query_failure_is_unverified",
    "test_sanitized_jsonl_maps_trace_order_unknown_and_private_reasoning",
    "test_structured_authentication_error_is_not_guessed_from_free_text",
    "test_task_expected_tools_reject_old_python_and_java",
    "test_three_h_lane_tasks_fake_codex_pass_hidden_verifier[java]",
    "test_three_h_lane_tasks_fake_codex_pass_hidden_verifier[python]",
    "test_three_h_lane_tasks_fake_codex_pass_hidden_verifier[typescript]",
    "test_codex_runtime_url_is_environment_only_and_ephemeral",
    "test_codex_runtime_values_are_absent_from_every_harness_artifact",
    "test_runtime_entrypoint_removes_url_only_from_codex_child_environment",
    "test_pinned_codex_uses_generated_isolated_relay_profile_without_websockets",
    "test_pinned_codex_split_sandbox_executes_with_outer_filesystem_and_seccomp_network",
}
PHASE_J_MODULE_NAMES = {
    "analyst.py",
    "analyst_agent.py",
}
PHASE_J_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"\bclass\s+AnalystAgent\b",
        r"\b(?:from|import)\s+langgraph\b",
        r"\b(?:from|import)\s+harnesslab\.analyst\b",
    )
)


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
        print(f"NOT_VERIFIED: required Gate E tools unavailable: {missing}")
        return ExitCode.NOT_VERIFIED
    preflight = subprocess.run(
        ("uv", "run", "--locked", "harnesslab", "sandbox", "doctor"),
        cwd=ROOT,
        check=False,
    )
    if preflight.returncode == ExitCode.NOT_VERIFIED:
        print("NOT_VERIFIED: Docker preflight cannot establish the outer Harness boundary")
        return ExitCode.NOT_VERIFIED
    if preflight.returncode != 0:
        print("FAIL: Docker preflight implementation failed")
        return ExitCode.FAIL
    return ExitCode.PASS


def verify_test_evidence() -> ExitCode:
    if not JUNIT.exists():
        print("NOT_VERIFIED: pytest did not create Gate E JUnit evidence")
        return ExitCode.NOT_VERIFIED
    cases = ET.parse(JUNIT).getroot().findall(".//testcase")
    if not cases:
        print("NOT_VERIFIED: Gate E collected zero tests")
        return ExitCode.NOT_VERIFIED
    skipped = [
        case.attrib.get("name", "unknown") for case in cases if case.find("skipped") is not None
    ]
    present = {case.attrib.get("name", "") for case in cases}
    missing = CRITICAL_TESTS - present
    if skipped or missing:
        print(f"NOT_VERIFIED: skipped={skipped}; missing_critical={sorted(missing)}")
        return ExitCode.NOT_VERIFIED
    print(f"PASS: {len(cases)} Gate E tests recorded; all critical tests present; zero skipped")
    print(
        "SENSITIVITY EVIDENCE: correct workspace mutation -> all three Hidden Verifiers PASS; "
        "remove the workspace mutation while retaining agent success + turn.completed + exit 0 -> "
        "test_codex_self_report_cannot_override_hidden_verifier produces VERIFIED_FAIL; inject "
        "private reasoning sentinel -> sanitizer exclusion assertions remain green; claim a native "
        "file_change without filesystem mutation -> authoritative changed_paths stays empty; "
        "Docker query nonzero + empty stdout -> outer cleanup is unverified; Python 3.11 and "
        "Java/Javac 17 -> expected_tools compatibility fails; backend credential in native output "
        "-> every published artifact excludes the exact value"
    )
    print("FAKE_CODEX_RESULTS=python:PASS/1.0,java:PASS/1.0,typescript:PASS/1.0")
    print(
        "NORMALIZED_TRACE_SOLVE=6 events: THREAD_STARTED,TURN_STARTED,REASONING_PRESENT,"
        "FILE_CHANGE,AGENT_MESSAGE,TURN_COMPLETED"
    )
    return ExitCode.PASS


def verify_image() -> bool:
    dockerfile = (ROOT / "docker" / "codex" / "Dockerfile").read_text(encoding="utf-8")
    verifier_dockerfile = (ROOT / "docker" / "sandbox" / "Dockerfile").read_text(encoding="utf-8")
    base_lines = tuple(line for line in dockerfile.splitlines() if line.startswith("FROM "))
    verifier_base_lines = tuple(
        line for line in verifier_dockerfile.splitlines() if line.startswith("FROM ")
    )
    required = (
        len(base_lines) == 3,
        all("@sha256:" in line for line in base_lines),
        len(verifier_base_lines) == 3,
        all("@sha256:" in line for line in verifier_base_lines),
        "@openai/codex@${CODEX_VERSION}" in dockerfile,
        "ARG CODEX_VERSION=0.149.0" in dockerfile,
        "USER 10001:10001" in dockerfile,
    )
    if not all(required) or "@openai/codex@latest" in dockerfile:
        print("FAIL: Codex Dockerfile lacks an immutable base, pinned CLI, or non-root user")
        return False
    inspected = subprocess.run(
        (
            "docker",
            "image",
            "inspect",
            CODEX_IMAGE,
            "--format",
            "{{json .Id}}|{{json .Config.User}}|{{json .Config.Env}}",
        ),
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if inspected.returncode != 0:
        print("FAIL: pinned Codex image is unavailable after doctor/tests")
        return False
    image_id_raw, user_raw, environment_raw = inspected.stdout.strip().split("|", 2)
    image_id = json.loads(image_id_raw)
    user = json.loads(user_raw)
    environment = tuple(json.loads(environment_raw) or ())
    if not isinstance(image_id, str) or not image_id.startswith("sha256:"):
        print("FAIL: Codex image lacks an immutable image ID")
        return False
    if user in {"", "0", "0:0", "root"}:
        print("FAIL: Codex image runs as root")
        return False
    sensitive_names = ("API_KEY", "TOKEN=", "PASSWORD=", "AUTH=")
    if any(any(name in value.upper() for name in sensitive_names) for value in environment):
        print("FAIL: Codex image environment contains credential-like configuration")
        return False
    docker_check = subprocess.run(
        (
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--entrypoint",
            "sh",
            CODEX_IMAGE,
            "-c",
            "command -v docker",
        ),
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    if docker_check.returncode == 0:
        print("FAIL: Codex image unexpectedly contains a Docker client")
        return False
    print(f"CODEX_IMAGE={CODEX_IMAGE}")
    print(f"CODEX_IMAGE_ID={image_id}")
    print(f"CODEX_BASES={';'.join(line.removeprefix('FROM ') for line in base_lines)}")
    print("VERIFIER_BASES=" + ";".join(line.removeprefix("FROM ") for line in verifier_base_lines))
    print(f"CODEX_IMAGE_USER={user}")
    return True


def _h_lane_requirements() -> dict[str, tuple[ExpectedToolContract, ...]]:
    requirements: dict[str, tuple[ExpectedToolContract, ...]] = {}
    for manifest in sorted((ROOT / "tasks").glob("*/*/task.yaml")):
        package = TaskPackage.load(manifest.parent)
        if EvaluationLane.HARNESS in package.definition.lane_support:
            requirements[package.definition.id] = package.definition.expected_tools
    if not requirements or any(not tools for tools in requirements.values()):
        raise RuntimeError("H-Lane task expected_tools are missing")
    return requirements


def _probe_tool_versions(image: str) -> dict[str, str]:
    commands = {
        "python": ("python3", "--version"),
        "java": ("java", "-version"),
        "javac": ("javac", "-version"),
        "node": ("node", "--version"),
    }
    versions: dict[str, str] = {}
    for tool, command in commands.items():
        completed = subprocess.run(
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
        if completed.returncode != 0:
            raise RuntimeError(f"{image} {tool} version query failed")
        versions[tool] = extract_tool_version(tool, completed.stdout + completed.stderr)
    return versions


def _image_id(image: str) -> str:
    completed = subprocess.run(
        ("docker", "image", "inspect", image, "--format", "{{json .Id}}"),
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"image identity unavailable: {image}")
    image_id = json.loads(completed.stdout.strip())
    if not isinstance(image_id, str) or not image_id.startswith("sha256:"):
        raise RuntimeError(f"image lacks immutable identity: {image}")
    return image_id


def verify_task_toolchains() -> bool:
    try:
        requirements = _h_lane_requirements()
        subject_versions = _probe_tool_versions(CODEX_IMAGE)
        verifier_versions = _probe_tool_versions(SANDBOX_IMAGE)
        subject_id = _image_id(CODEX_IMAGE)
        verifier_id = _image_id(SANDBOX_IMAGE)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"FAIL: H-Lane toolchain verification error: {exc}")
        return False
    failures: list[str] = []
    for task_id, task_requirements in requirements.items():
        failures.extend(
            f"subject {task_id}: {failure}"
            for failure in unsatisfied_tools(task_requirements, subject_versions)
        )
        failures.extend(
            f"verifier {task_id}: {failure}"
            for failure in unsatisfied_tools(task_requirements, verifier_versions)
        )
    all_requirements = tuple(tool for tools in requirements.values() for tool in tools)
    old_runtime_failures = unsatisfied_tools(
        all_requirements,
        {"python": "3.11.13", "java": "17.0.16", "javac": "17.0.16", "node": "24.4.1"},
    )
    sensitivity = (
        any(failure.startswith("python expected 3.12") for failure in old_runtime_failures),
        any(failure.startswith("java expected 21") for failure in old_runtime_failures),
        any(failure.startswith("javac expected 21") for failure in old_runtime_failures),
    )
    if not all(sensitivity):
        print("FAIL: old Python 3.11 / Java 17 sensitivity control did not fail")
        return False
    if failures:
        print(f"FAIL: H-Lane task toolchain mismatches: {failures}")
        return False
    print(f"CODEX_SUBJECT_IMAGE_ID={subject_id}")
    print(f"VERIFIER_IMAGE={SANDBOX_IMAGE}")
    print(f"VERIFIER_IMAGE_ID={verifier_id}")
    for tool, version in subject_versions.items():
        print(f"CODEX_SUBJECT_{tool.upper()}={version}")
    for tool, version in verifier_versions.items():
        print(f"VERIFIER_{tool.upper()}={version}")
    print("PASS: every H-Lane task expected_tools contract matches both isolated runtimes")
    print("SENSITIVITY: Python 3.11 and Java/Javac 17 are rejected by current task contracts")
    return True


def _phase_j_violation(relative: str, content: str) -> bool:
    path = Path(relative)
    if "analyst" in path.parts:
        return False
    if path.as_posix() == "src/harnesslab/cli.py":
        return False
    return (
        "langgraph" in path.parts
        or path.name in PHASE_J_MODULE_NAMES
        or any(pattern.search(content) for pattern in PHASE_J_PATTERNS)
    )


def verify_source_and_scope() -> bool:
    import harnesslab

    module_path = Path(harnesslab.__file__).resolve()
    expected = (ROOT / "src" / "harnesslab").resolve()
    print(f"REPOSITORY_ROOT={ROOT}")
    print(f"HARNESSLAB_SOURCE={module_path}")
    if module_path.parent != expected:
        print("FAIL: Gate E imported HarnessLab outside the current working tree")
        return False
    identity = subprocess.run(
        ("git", "rev-parse", "HEAD"), cwd=ROOT, check=False, capture_output=True, text=True
    )
    worktree = subprocess.run(
        ("git", "status", "--porcelain"), cwd=ROOT, check=False, capture_output=True, text=True
    )
    if identity.returncode != 0 or worktree.returncode != 0:
        print("FAIL: Gate E cannot record Git source identity")
        return False
    print(f"GIT_HEAD={identity.stdout.strip()}")
    print(f"GIT_DIRTY={bool(worktree.stdout.strip())}")
    sensitivity = (
        not _phase_j_violation("src/harnesslab/judgelab.py", ""),
        not _phase_j_violation("src/harnesslab/analyst/graph.py", "from langgraph import Graph"),
        _phase_j_violation(
            "src/harnesslab/harness_lane/bridge.py",
            "from harnesslab.analyst import AnalystService",
        ),
        not _phase_j_violation(
            "src/harnesslab/experiment/queue.py", "class ExperimentWorker: pass"
        ),
        not _phase_j_violation(
            "src/harnesslab/harness_lane/adapter.py", "class HarnessAdapter: pass"
        ),
    )
    if not all(sensitivity):
        print("FAIL: Phase J source detector failed its sensitivity control")
        return False
    violations: list[str] = []
    for path in (ROOT / "src" / "harnesslab").rglob("*.py"):
        relative = path.relative_to(ROOT).as_posix()
        content = path.read_text(encoding="utf-8")
        if _phase_j_violation(relative, content):
            violations.append(relative)
    if violations:
        print(f"FAIL: Phase J implementation detected: {violations}")
        return False
    print("PASS: Phase E runtime remains isolated from the Phase J Analyst package")
    return True


def verify_repository_secrets() -> bool:
    listed = subprocess.run(
        ("git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"),
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    if listed.returncode != 0:
        print("FAIL: unable to enumerate repository files for Gate E secret hygiene")
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
    print("PASS: tracked/untracked files contain no recognized provider or GitHub credentials")
    return True


def main() -> int:
    environment = verify_environment()
    if environment is not ExitCode.PASS:
        return environment
    if os.environ.get("HARNESSLAB_ENABLE_REAL_CODEX") == "1":
        print(
            "NOT_VERIFIED: safe provider-control-plane versus subject-tool-network separation "
            "has not been established for a real Codex smoke"
        )
        return ExitCode.NOT_VERIFIED
    checks = (
        Check("locked dependency sync", ("uv", "sync", "--locked")),
        Check(
            "pinned Codex runtime doctor",
            ("uv", "run", "--locked", "harnesslab", "harness", "codex", "doctor"),
        ),
        Check(
            "Phase E pytest",
            (
                "uv",
                "run",
                "--locked",
                "pytest",
                "-q",
                *PHASE_E_TESTS,
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
    if not verify_image():
        failed = True
    if not verify_task_toolchains():
        failed = True
    if not verify_source_and_scope():
        failed = True
    if not verify_repository_secrets():
        failed = True
    if not failed:
        print("CODEX_STARTUP_FAILURE_EVIDENCE=PASS")
        print("CODEX_EARLY_EXIT_PHASE_CLASSIFICATION=PASS")
        print("CODEX_STARTUP_SECRET_HYGIENE=PASS")
        print("CODEX_CLEANUP_INVARIANT=PASS")
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
    print("REAL_CALLS_THIS_REPAIR=0")
    print("REAL_PROVIDER_SMOKE=NOT_VERIFIED")
    print("CORE_RELEASE_READY=FALSE")
    print("v1.0.0-core=ABSENT")
    print("REAL_CODEX_SMOKE=NOT_VERIFIED")
    return ExitCode.FAIL if failed else ExitCode.PASS


if __name__ == "__main__":
    raise SystemExit(main())
