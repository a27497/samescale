from __future__ import annotations

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
    timeout_seconds: int = 300


ROOT = Path(__file__).resolve().parents[1]
JUNIT = ROOT / "gate-a-results.xml"
CRITICAL_TESTS = {
    "test_database_connectivity",
    "test_doctor_reports_pass_with_database",
    "test_health_reports_healthy_database",
    "test_migration_from_empty_database",
}


def run(check: Check, *, env: dict[str, str] | None = None, expected_failure: bool = False) -> bool:
    print(f"\n=== {check.name} ===", flush=True)
    print("COMMAND:", subprocess.list2cmdline(check.command), flush=True)
    try:
        completed = subprocess.run(
            check.command,
            cwd=ROOT,
            env=env,
            check=False,
            timeout=check.timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        print(f"FAIL: command exceeded {check.timeout_seconds}s")
        return False
    if expected_failure:
        passed = completed.returncode != 0
        print(f"SENSITIVITY {'PASS' if passed else 'FAIL'}: exit={completed.returncode}")
        return passed
    passed = completed.returncode == 0
    print(f"{'PASS' if passed else 'FAIL'}: exit={completed.returncode}")
    return passed


def verify_test_evidence() -> ExitCode:
    if not JUNIT.exists():
        print("NOT_VERIFIED: pytest did not create JUnit evidence")
        return ExitCode.NOT_VERIFIED
    root = ET.parse(JUNIT).getroot()
    cases = root.findall(".//testcase")
    if not cases:
        print("NOT_VERIFIED: pytest collected zero tests")
        return ExitCode.NOT_VERIFIED
    skipped = [
        case.attrib.get("name", "unknown") for case in cases if case.find("skipped") is not None
    ]
    present = {case.attrib.get("name", "") for case in cases}
    missing = CRITICAL_TESTS - present
    if skipped or missing:
        print(f"NOT_VERIFIED: skipped={skipped}; missing_critical={sorted(missing)}")
        return ExitCode.NOT_VERIFIED
    print(f"PASS: {len(cases)} tests recorded; all critical tests present; zero skipped")
    return ExitCode.PASS


def verify_source_identity() -> bool:
    import harnesslab

    module_path = Path(harnesslab.__file__).resolve()
    print(f"REPOSITORY_ROOT={ROOT}")
    print(f"HARNESSLAB_SOURCE={module_path}")
    try:
        module_path.relative_to(ROOT)
    except ValueError:
        print("FAIL: imported HarnessLab is outside the working tree")
        return False
    return True


def verify_worktree_text() -> ExitCode:
    listed = subprocess.run(
        ("git", "ls-files", "--cached", "--others", "--exclude-standard"),
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if listed.returncode != 0:
        print("NOT_VERIFIED: unable to enumerate the Git working tree")
        return ExitCode.NOT_VERIFIED
    relative_paths = [Path(line) for line in listed.stdout.splitlines() if line]
    if not relative_paths:
        print("NOT_VERIFIED: Git working-tree corpus is empty")
        return ExitCode.NOT_VERIFIED

    text_files = 0
    violations: list[str] = []
    for relative_path in relative_paths:
        content = (ROOT / relative_path).read_bytes()
        if b"\x00" in content:
            continue
        text_files += 1
        for line_number, line in enumerate(content.splitlines(keepends=True), start=1):
            if line.rstrip(b"\r\n").endswith((b" ", b"\t")):
                violations.append(f"{relative_path}:{line_number}")
    if text_files == 0:
        print("NOT_VERIFIED: no text files were available for whitespace validation")
        return ExitCode.NOT_VERIFIED
    if violations:
        print(f"FAIL: trailing whitespace at {violations}")
        return ExitCode.FAIL
    print(f"PASS: {text_files} tracked/untracked text files checked for trailing whitespace")
    return ExitCode.PASS


def main() -> int:
    if shutil.which("uv") is None:
        print("NOT_VERIFIED: uv is unavailable")
        return ExitCode.NOT_VERIFIED
    if not os.environ.get("DATABASE_URL"):
        print("NOT_VERIFIED: DATABASE_URL is required for Gate A")
        return ExitCode.NOT_VERIFIED

    checks = [
        Check("locked dependency sync", ("uv", "sync", "--locked")),
        Check("exact Python", ("uv", "run", "--locked", "python", "--version")),
        Check("CLI help", ("uv", "run", "--locked", "harnesslab", "--help")),
        Check("CLI version", ("uv", "run", "--locked", "harnesslab", "--version")),
        Check("CLI doctor", ("uv", "run", "--locked", "harnesslab", "doctor")),
        Check("Alembic current head", ("uv", "run", "--locked", "alembic", "upgrade", "head")),
        Check(
            "pytest",
            (
                "uv",
                "run",
                "--locked",
                "pytest",
                "-q",
                f"--junitxml={JUNIT}",
            ),
            timeout_seconds=600,
        ),
        Check("Ruff check", ("uv", "run", "--locked", "ruff", "check", ".")),
        Check("Ruff format", ("uv", "run", "--locked", "ruff", "format", "--check", ".")),
        Check("mypy", ("uv", "run", "--locked", "mypy", "src", "tests", "scripts")),
        Check("git whitespace", ("git", "diff", "--check")),
    ]

    failed = False
    for check in checks:
        if not run(check):
            failed = True

    if not verify_source_identity():
        failed = True
    worktree_evidence = verify_worktree_text()
    if worktree_evidence is ExitCode.NOT_VERIFIED:
        return ExitCode.NOT_VERIFIED
    if worktree_evidence is ExitCode.FAIL:
        failed = True
    evidence = verify_test_evidence()
    if evidence is ExitCode.NOT_VERIFIED:
        return ExitCode.NOT_VERIFIED

    mutation_env = os.environ.copy()
    mutation_env["DATABASE_URL"] = (
        "postgresql+psycopg://harnesslab:intentionally_wrong@127.0.0.1:5432/harnesslab"
        "?connect_timeout=2"
    )
    sensitivity = run(
        Check(
            "health DB-failure sensitivity",
            (
                "uv",
                "run",
                "--locked",
                "pytest",
                "-q",
                "tests/test_api_health.py::test_health_reports_healthy_database",
            ),
            timeout_seconds=30,
        ),
        env=mutation_env,
        expected_failure=True,
    )
    print(
        "MUTATION: valid PostgreSQL credentials -> intentionally invalid password; "
        "test_health_reports_healthy_database must turn red"
    )
    if not sensitivity:
        failed = True

    return ExitCode.FAIL if failed else ExitCode.PASS


if __name__ == "__main__":
    raise SystemExit(main())
