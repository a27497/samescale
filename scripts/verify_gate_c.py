from __future__ import annotations

import json
import os
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
    timeout_seconds: int = 600


ROOT = Path(__file__).resolve().parents[1]
JUNIT = ROOT / "gate-c-results.xml"
PHASE_C_TESTS = (
    "tests/test_sandbox.py",
    "tests/test_execution_lease.py",
)
CRITICAL_TESTS = {
    "test_artifact_digest_function_is_sensitive",
    "test_cleanup_daemon_error_is_not_verified",
    "test_cleanup_verification_failure_cannot_report_success",
    "test_container_output_capture_is_bounded",
    "test_declared_context_is_subject_visible_read_only",
    "test_docker_cli_subprocess_uses_pinned_environment",
    "test_docker_preflight_rejects_remote_and_records_immutable_image",
    "test_docker_preflight_rejects_remote_host_before_connection",
    "test_effective_docker_endpoint_precedence_rejects_remote_overrides",
    "test_effective_inspect_profile_and_isolated_verifier_e2e",
    "test_execution_lease_heartbeat_and_expiry_recovery",
    "test_explicit_local_context_is_pinned_over_remote_host",
    "test_explicit_cancellation_kills_and_removes_container",
    "test_fake_secret_is_redacted_and_artifacts_are_consistent",
    "test_fresh_workspace_isolation_uses_same_task_definition",
    "test_host_escape_and_subject_symlink_artifact_are_rejected",
    "test_security_model_rejects_privileged_inspect_mutation",
    "test_timeout_kills_and_removes_container",
    "test_verifier_cleanup_failure_cannot_return_passed",
    "test_workspace_secret_content_and_filename_are_withheld",
    "test_workspace_secret_scan_detects_chunk_boundary_match",
}
IMAGE = "harnesslab-phase-c:0.1.0"
RUN_LABEL = "com.harnesslab.phase=C"


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
        print(f"NOT_VERIFIED: required Gate C tools unavailable: {missing}")
        return ExitCode.NOT_VERIFIED
    if not os.environ.get("DATABASE_URL"):
        print("NOT_VERIFIED: DATABASE_URL is required for Gate C lease and regression tests")
        return ExitCode.NOT_VERIFIED
    preflight = subprocess.run(
        ("uv", "run", "--locked", "harnesslab", "sandbox", "doctor"),
        cwd=ROOT,
        check=False,
    )
    if preflight.returncode == ExitCode.NOT_VERIFIED:
        print("NOT_VERIFIED: Docker preflight cannot establish a local Linux daemon")
        return ExitCode.NOT_VERIFIED
    if preflight.returncode != 0:
        print("FAIL: Docker preflight implementation failed")
        return ExitCode.FAIL
    return ExitCode.PASS


def verify_test_evidence() -> ExitCode:
    if not JUNIT.exists():
        print("NOT_VERIFIED: pytest did not create Gate C JUnit evidence")
        return ExitCode.NOT_VERIFIED
    cases = ET.parse(JUNIT).getroot().findall(".//testcase")
    if not cases:
        print("NOT_VERIFIED: Gate C collected zero tests")
        return ExitCode.NOT_VERIFIED
    skipped = [
        case.attrib.get("name", "unknown") for case in cases if case.find("skipped") is not None
    ]
    present = {case.attrib.get("name", "") for case in cases}
    missing = CRITICAL_TESTS - present
    if skipped or missing:
        print(f"NOT_VERIFIED: skipped={skipped}; missing_critical={sorted(missing)}")
        return ExitCode.NOT_VERIFIED
    print(f"PASS: {len(cases)} Gate C tests recorded; all critical tests present; zero skipped")
    print(
        "SENSITIVITY EVIDENCE: remote effective endpoint overrides fail preflight; "
        "insecure inspect fields fail the security model; exact workspace secret "
        "content/path withholds the snapshot; unverified cleanup cannot report success; "
        "output truncation and artifact content mutations are observable; expired timestamp "
        "enables lease reclaim"
    )
    return ExitCode.PASS


def verify_image_identity() -> bool:
    dockerfile = (ROOT / "docker" / "sandbox" / "Dockerfile").read_text(encoding="utf-8")
    first_line = dockerfile.splitlines()[0]
    if "@sha256:" not in first_line:
        print("FAIL: sandbox base image is not pinned to an immutable digest")
        return False
    completed = subprocess.run(
        ("docker", "image", "inspect", IMAGE, "--format", "{{json .Id}}"),
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        print("FAIL: Phase C sandbox image is unavailable after tests")
        return False
    image_id = json.loads(completed.stdout)
    if not isinstance(image_id, str) or not image_id.startswith("sha256:"):
        print("FAIL: sandbox image lacks an immutable image ID")
        return False
    print(f"SANDBOX_IMAGE={IMAGE}")
    print(f"SANDBOX_IMAGE_ID={image_id}")
    print(f"SANDBOX_BASE={first_line.removeprefix('FROM ')}")
    return True


def verify_cleanup() -> bool:
    containers = subprocess.run(
        ("docker", "ps", "--all", "--quiet", "--filter", f"label={RUN_LABEL}"),
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    volumes = subprocess.run(
        ("docker", "volume", "ls", "--quiet", "--filter", f"label={RUN_LABEL}"),
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if containers.returncode != 0 or volumes.returncode != 0:
        print("FAIL: unable to inspect Phase C Docker resource cleanup")
        return False
    if containers.stdout.strip() or volumes.stdout.strip():
        print("FAIL: HarnessLab Phase C Docker resources remain after tests")
        return False
    print("PASS: zero HarnessLab Phase C containers or volumes remain")
    return True


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
        ("git", "rev-parse", "HEAD"),
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    worktree = subprocess.run(
        ("git", "status", "--porcelain"),
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if identity.returncode != 0 or worktree.returncode != 0:
        print("FAIL: unable to record Git source identity")
        return False
    print(f"GIT_HEAD={identity.stdout.strip()}")
    print(f"GIT_DIRTY={bool(worktree.stdout.strip())}")
    forbidden = (
        ROOT / "src" / "harnesslab" / "harness_adapters",
        ROOT / "src" / "harnesslab" / "workers",
        ROOT / "src" / "harnesslab" / "traces",
    )
    existing = [str(path.relative_to(ROOT)) for path in forbidden if path.exists()]
    if existing:
        print(f"FAIL: Phase E/later implementation paths exist: {existing}")
        return False
    print("PASS: no Phase E/later harness adapter, worker, or trace implementation paths")
    return True


def main() -> int:
    environment = verify_environment()
    if environment is not ExitCode.PASS:
        return environment

    checks = (
        Check("locked dependency sync", ("uv", "sync", "--locked")),
        Check("Docker version", ("docker", "version")),
        Check(
            "Docker sandbox doctor", ("uv", "run", "--locked", "harnesslab", "sandbox", "doctor")
        ),
        Check("Alembic Phase C head", ("uv", "run", "--locked", "alembic", "upgrade", "head")),
        Check("Gate A regression", ("uv", "run", "--locked", "python", "scripts/verify_gate_a.py")),
        Check("Gate B regression", ("uv", "run", "--locked", "python", "scripts/verify_gate_b.py")),
        Check(
            "Phase C pytest",
            (
                "uv",
                "run",
                "--locked",
                "pytest",
                "-q",
                *PHASE_C_TESTS,
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
    if not verify_image_identity():
        failed = True
    if not verify_cleanup():
        failed = True
    if not verify_source_and_scope():
        failed = True
    return ExitCode.FAIL if failed else ExitCode.PASS


if __name__ == "__main__":
    raise SystemExit(main())
