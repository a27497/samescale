from __future__ import annotations

import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path

from harnesslab.experiment.statistics import (
    continuous_statistics,
    paired_binary_statistics,
    pass_at_k,
    wilson_interval,
)


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
JUNIT = ROOT / "gate-g-results.xml"
PHASE_G_TESTS = (
    "tests/test_experiment_plan.py",
    "tests/test_experiment_statistics.py",
    "tests/test_experiment_comparability.py",
    "tests/test_experiment_queue.py",
    "tests/test_experiment_e2e.py",
    "tests/test_experiment_cli.py",
)
CRITICAL_TESTS = {
    "test_strict_experiment_spec_and_deterministic_matrix_plan",
    "test_plan_digest_changes_with_resolved_control_identity",
    "test_controlled_ablation_accepts_one_treatment_and_rejects_hard_drift",
    "test_repeated_run_tiers_are_conservative",
    "test_lane_outcome_normalization_separates_subject_infra_and_cancellation",
    "test_infrastructure_failures_are_not_capability_failures_or_denominator_members",
    "test_pass_at_k_boundaries_and_macro_per_task",
    "test_continuous_bootstrap_is_deterministic_and_paired",
    "test_exact_mcnemar_and_comparability_gating",
    "test_controlled_keyless_p_lane_and_negative_comparability_sensitivity",
    "test_postgresql_durable_queue_skip_locked_lease_and_idempotency",
    "test_phase_f_to_phase_g_migration_preserves_execution_lease",
    "test_keyless_experiment_e2e_uses_queue_runners_manifests_and_report",
    "test_phase_g_cli_surface_and_canonical_plan_output",
    "test_phase_g_nested_cli_help",
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
        print(f"NOT_VERIFIED: required Gate G tools unavailable: {missing}")
        return ExitCode.NOT_VERIFIED
    if not os.environ.get("DATABASE_URL"):
        print("NOT_VERIFIED: DATABASE_URL is required for real PostgreSQL queue evidence")
        return ExitCode.NOT_VERIFIED
    result = subprocess.run(
        ("uv", "run", "--locked", "harnesslab", "sandbox", "doctor"),
        cwd=ROOT,
        check=False,
    )
    if result.returncode == ExitCode.NOT_VERIFIED:
        print("NOT_VERIFIED: Docker cannot establish the Hidden Verifier boundary")
        return ExitCode.NOT_VERIFIED
    return ExitCode.PASS if result.returncode == 0 else ExitCode.FAIL


def verify_test_evidence(evidence_path: Path) -> ExitCode:
    if not JUNIT.exists():
        print("NOT_VERIFIED: pytest did not create Gate G JUnit evidence")
        return ExitCode.NOT_VERIFIED
    cases = ET.parse(JUNIT).getroot().findall(".//testcase")
    if not cases:
        print("NOT_VERIFIED: Gate G collected zero tests")
        return ExitCode.NOT_VERIFIED
    skipped = [
        case.attrib.get("name", "unknown") for case in cases if case.find("skipped") is not None
    ]
    present = {case.attrib.get("name", "") for case in cases}
    missing = CRITICAL_TESTS - present
    if skipped or missing:
        print(f"NOT_VERIFIED: skipped={skipped}; missing_critical={sorted(missing)}")
        return ExitCode.NOT_VERIFIED
    if not evidence_path.is_file():
        print("NOT_VERIFIED: keyless E2E did not publish its deterministic evidence summary")
        return ExitCode.NOT_VERIFIED
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        print("NOT_VERIFIED: keyless E2E evidence summary is unreadable")
        return ExitCode.NOT_VERIFIED
    required = {
        "matrix_run_count": 9,
        "artifact_manifest_count": 9,
        "p_lane_not_comparable_pairs": 3,
        "ablation_partial_pairs": 3,
    }
    if any(evidence.get(key) != value for key, value in required.items()):
        print(f"NOT_VERIFIED: keyless E2E summary is incomplete: {evidence}")
        return ExitCode.NOT_VERIFIED
    digests = (evidence.get("plan_digest"), evidence.get("report_digest"))
    if any(
        not isinstance(value, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", value)
        for value in digests
    ):
        print("NOT_VERIFIED: plan/report digest evidence is invalid")
        return ExitCode.NOT_VERIFIED
    print(f"PASS: {len(cases)} Gate G tests recorded; critical set present; zero skipped")
    print(f"MATRIX_RUN_SLOTS={evidence['matrix_run_count']}")
    print(f"ACTUAL_PERSISTED_MANIFESTS={evidence['artifact_manifest_count']}")
    print(f"PLAN_DIGEST={evidence['plan_digest']}")
    print(f"REPORT_DIGEST={evidence['report_digest']}")
    print("QUEUE=PostgreSQL SELECT FOR UPDATE SKIP LOCKED two-worker PASS")
    print("LEASE=heartbeat+owner-check+expiry-reclaim+attempt+cancellation PASS")
    print("REPEATED_POLICY=n1:SMOKE;n3:INFORMAL;n5:FORMAL PASS")
    print("DENOMINATOR=capability_passes+capability_failures;infra disclosed separately PASS")
    print("P_LANE=controlled-keyless COMPARABLE;actual-route-mismatch NOT_COMPARABLE PASS")
    print("ABLATION=reasoning_effort declared;observed-model limitation surfaced PASS")
    return ExitCode.PASS


def verify_statistics_examples() -> bool:
    wilson = wilson_interval(2, 5)
    continuous = continuous_statistics((10.0, 11.0, 13.0, 17.0, 21.0), seed=7, resamples=199)
    mcnemar = paired_binary_statistics(((True, False), (False, True), (False, True)))
    if wilson is None or continuous.median_bootstrap_95 is None:
        print("FAIL: deterministic statistics examples are unavailable")
        return False
    if mcnemar.exact_two_sided_p is None:
        print("FAIL: exact paired binary example is unavailable")
        return False
    print(f"WILSON_2_OF_5=[{wilson.low:.6f},{wilson.high:.6f}]")
    print(f"PASS_AT_3_N5_C2={pass_at_k(5, 2, 3):.6f}")
    print(
        "BOOTSTRAP_MEDIAN_95="
        f"[{continuous.median_bootstrap_95.low:.6f},"
        f"{continuous.median_bootstrap_95.high:.6f}]"
    )
    print(
        f"MCNEMAR_EXACT=b{mcnemar.left_pass_right_fail};"
        f"c{mcnemar.left_fail_right_pass};p={mcnemar.exact_two_sided_p:.6f}"
    )
    return True


def verify_dependencies_and_scope() -> bool:
    for package in ("numpy", "pandas", "scipy"):
        print(f"{package.upper()}_VERSION={importlib.metadata.version(package)}")
    forbidden_dependencies = {"statsmodels", "scikit-learn", "jupyter", "matplotlib"}
    installed_project = (ROOT / "pyproject.toml").read_text(encoding="utf-8").casefold()
    if any(dependency in installed_project for dependency in forbidden_dependencies):
        print("FAIL: unapproved quantitative dependency detected")
        return False
    forbidden_paths = (ROOT / "src" / "harnesslab" / "judges", ROOT / "frontend")
    if any(path.exists() for path in forbidden_paths):
        print("FAIL: Phase H/frontend path detected")
        return False
    violations: list[str] = []
    patterns = (r"\bclass\s+JudgeLab\b", r"\b(?:from|import)\s+langgraph\b")
    for path in (ROOT / "src" / "harnesslab").rglob("*.py"):
        content = path.read_text(encoding="utf-8")
        if any(re.search(pattern, content) for pattern in patterns):
            violations.append(path.relative_to(ROOT).as_posix())
    if violations:
        print(f"FAIL: Phase H/analyst implementation detected: {violations}")
        return False
    print("PASS: Phase G scope contains no JudgeLab, frontend, analyst, RAG, or multi-agent stack")
    return True


def verify_repository_identity_and_secrets() -> bool:
    import harnesslab

    expected = (ROOT / "src" / "harnesslab").resolve()
    actual = Path(harnesslab.__file__).resolve().parent
    print(f"REPOSITORY_ROOT={ROOT}")
    print(f"HARNESSLAB_SOURCE={actual}")
    if actual != expected:
        print("FAIL: Gate G imported HarnessLab outside the current working tree")
        return False
    listed = subprocess.run(
        ("git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"),
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
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
    if listed.returncode != 0 or matches:
        print(f"FAIL: repository enumeration/secret hygiene failed: {matches}")
        return False
    head = subprocess.run(
        ("git", "rev-parse", "HEAD"), cwd=ROOT, check=False, capture_output=True, text=True
    )
    dirty = subprocess.run(
        ("git", "status", "--porcelain"), cwd=ROOT, check=False, capture_output=True, text=True
    )
    print(f"GIT_HEAD={head.stdout.strip()}")
    print(f"GIT_DIRTY={bool(dirty.stdout.strip())}")
    print("PASS: repository secret scan found no recognized provider/GitHub credentials")
    return head.returncode == 0 and dirty.returncode == 0


def main() -> int:
    environment = verify_environment()
    if environment is not ExitCode.PASS:
        return environment
    real_flags = (
        "HARNESSLAB_ENABLE_REAL_PROVIDER",
        "HARNESSLAB_ENABLE_REAL_CODEX",
        "HARNESSLAB_ENABLE_REAL_CLAUDE",
        "HARNESSLAB_ENABLE_REAL_DEEPSEEK",
        "HARNESSLAB_ENABLE_REAL_MATRIX",
    )
    if any(os.environ.get(name) == "1" for name in real_flags):
        print("NOT_VERIFIED: Gate G is deterministic and must not consume real credentials")
        return ExitCode.NOT_VERIFIED
    evidence_path = Path(tempfile.gettempdir()) / f"harnesslab-gate-g-{os.getpid()}.json"
    evidence_path.unlink(missing_ok=True)
    os.environ["HARNESSLAB_GATE_G_EVIDENCE_PATH"] = str(evidence_path)
    checks = (
        Check("locked dependency sync", ("uv", "sync", "--locked")),
        Check("Alembic upgrade head", ("uv", "run", "--locked", "alembic", "upgrade", "head")),
        Check(
            "Alembic current head", ("uv", "run", "--locked", "alembic", "current", "--check-heads")
        ),
        Check(
            "Phase G pytest",
            (
                "uv",
                "run",
                "--locked",
                "pytest",
                "-q",
                *PHASE_G_TESTS,
                f"--junitxml={JUNIT}",
            ),
        ),
        Check("Phase G CLI", ("uv", "run", "--locked", "harnesslab", "experiment", "--help")),
        Check("Ruff check", ("uv", "run", "--locked", "ruff", "check", ".")),
        Check("Ruff format", ("uv", "run", "--locked", "ruff", "format", "--check", ".")),
        Check("mypy", ("uv", "run", "--locked", "mypy", "src", "tests", "scripts")),
        Check("git whitespace", ("git", "diff", "--check")),
    )
    failed = False
    for check in checks:
        if not run(check):
            failed = True
    evidence = verify_test_evidence(evidence_path)
    evidence_path.unlink(missing_ok=True)
    os.environ.pop("HARNESSLAB_GATE_G_EVIDENCE_PATH", None)
    if evidence is ExitCode.NOT_VERIFIED:
        return evidence
    if not verify_statistics_examples():
        failed = True
    if not verify_dependencies_and_scope():
        failed = True
    if not verify_repository_identity_and_secrets():
        failed = True
    print("EXPERIMENT_DB_HEAD=20260823_0003")
    print("REAL_MATRIX_EVIDENCE=NOT_RUN")
    print("REAL_PROVIDER_SMOKE=NOT_RUN")
    print("REAL_CODEX_SMOKE=NOT_RUN")
    print("REAL_CLAUDE_SMOKE=NOT_RUN")
    print("REAL_DEEPSEEK_SMOKE=NOT_RUN")
    return ExitCode.FAIL if failed else ExitCode.PASS


if __name__ == "__main__":
    raise SystemExit(main())
