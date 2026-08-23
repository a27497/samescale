from __future__ import annotations

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
JUNIT = ROOT / "gate-b-results.xml"
PHASE_B_TESTS = (
    "tests/test_task_package.py",
    "tests/test_task_verifier.py",
    "tests/test_task_fixtures.py",
)
CRITICAL_TESTS = {
    "test_complete_verifier_tree_defines_verifier_identity",
    "test_digest_is_stable_and_content_sensitive",
    "test_digest_reproducibility_check_fails_closed",
    "test_evidence_workspace_digest_precedes_verifier_side_effects",
    "test_fake_subject_runner_only_receives_subject_workspace",
    "test_fresh_materialization_isolated_and_hides_trusted_assets",
    "test_malformed_verifier_output_fails_closed",
    "test_polarity_validation_rejects_baseline_pass_and_oracle_fail",
    "test_tamper_and_exposed_test_deletion_cannot_create_pass",
    "test_three_fixture_polarity_and_hidden_asset_isolation",
    "test_verifier_timeout_fails_closed",
}
TASK_PATHS = (
    "tasks/micro-python-clamp/1.0.0",
    "tasks/micro-java-clamp/1.0.0",
    "tasks/micro-typescript-clamp/1.0.0",
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


def verify_test_evidence() -> ExitCode:
    if not JUNIT.exists():
        print("NOT_VERIFIED: pytest did not create Gate B JUnit evidence")
        return ExitCode.NOT_VERIFIED
    cases = ET.parse(JUNIT).getroot().findall(".//testcase")
    if not cases:
        print("NOT_VERIFIED: Gate B collected zero tests")
        return ExitCode.NOT_VERIFIED
    skipped = [
        case.attrib.get("name", "unknown") for case in cases if case.find("skipped") is not None
    ]
    present = {case.attrib.get("name", "") for case in cases}
    missing = CRITICAL_TESTS - present
    if skipped or missing:
        print(f"NOT_VERIFIED: skipped={skipped}; missing_critical={sorted(missing)}")
        return ExitCode.NOT_VERIFIED
    print(f"PASS: {len(cases)} Gate B tests recorded; all critical tests present; zero skipped")
    print(
        "SENSITIVITY EVIDENCE: task content and complete verifier-tree mutations change identity; "
        "workspace identity precedes verifier side effects; baseline/oracle polarity inversions "
        "fail validation; hidden verifier remains authoritative after exposed-test tamper"
    )
    return ExitCode.PASS


def verify_phase_boundary() -> bool:
    forbidden = (
        ROOT / "src" / "harnesslab" / "analyst",
        ROOT / "src" / "harnesslab" / "langgraph",
    )
    existing = [str(path.relative_to(ROOT)) for path in forbidden if path.exists()]
    if existing:
        print(f"FAIL: Phase J implementation paths exist: {existing}")
        return False
    source_files = list((ROOT / "src" / "harnesslab" / "tasks").rglob("*.py"))
    if not source_files:
        print("FAIL: Phase B task source corpus is empty")
        return False
    print(
        f"PASS: Phase B task sources present and no Phase J paths; "
        f"inspected {len(source_files)} source files"
    )
    return True


def main() -> int:
    missing_tools = [
        tool for tool in ("uv", "java", "javac", "node", "git") if shutil.which(tool) is None
    ]
    if missing_tools:
        print(f"NOT_VERIFIED: required Gate B tools unavailable: {missing_tools}")
        return ExitCode.NOT_VERIFIED

    checks = [
        Check("locked dependency sync", ("uv", "sync", "--locked")),
        Check("exact Python", ("uv", "run", "--locked", "python", "--version")),
        Check("Java runtime", ("java", "-version")),
        Check("Java compiler", ("javac", "-version")),
        Check("Node runtime", ("node", "--version")),
        Check(
            "Phase B pytest",
            (
                "uv",
                "run",
                "--locked",
                "pytest",
                "-q",
                *PHASE_B_TESTS,
                f"--junitxml={JUNIT}",
            ),
        ),
        *[
            Check(
                f"task validation: {task_path}",
                ("uv", "run", "--locked", "harnesslab", "task", "validate", task_path),
            )
            for task_path in TASK_PATHS
        ],
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
    evidence = verify_test_evidence()
    if evidence is ExitCode.NOT_VERIFIED:
        return ExitCode.NOT_VERIFIED
    if not verify_phase_boundary():
        failed = True
    return ExitCode.FAIL if failed else ExitCode.PASS


if __name__ == "__main__":
    raise SystemExit(main())
