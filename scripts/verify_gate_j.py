from __future__ import annotations

import importlib.metadata
import json
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


ROOT = Path(__file__).resolve().parents[1]
JUNIT = ROOT / "gate-j-results.xml"
EVIDENCE = ROOT / "gate-j-evidence.json"


@dataclass(frozen=True)
class Check:
    name: str
    command: tuple[str, ...]
    timeout_seconds: int = 1200


CRITICAL_TESTS = {
    "test_only_the_six_approved_tools_are_exposed",
    "test_cli_exposes_focused_fake_only_analyst_surface",
    "test_tool_argument_models_are_strict_bounded_and_discriminated",
    "test_langgraph_stops_at_twelve_total_tool_calls",
    "test_langgraph_stops_at_eight_decision_iterations",
    "test_fabricated_evidence_reference_is_rejected",
    "test_contradictory_run_fact_is_rejected",
    "test_contradictory_numeric_fact_is_rejected",
    "test_valid_structured_fact_is_accepted_and_rendered_deterministically",
    "test_verified_fact_contract_rejects_backend_controlled_prose",
    "test_injection_like_text_cannot_manufacture_a_supported_structured_fact",
    "test_deterministic_report_json_markdown_digest_and_atomic_persistence",
    "test_production_queue_executor_manifests_report_and_ablation_are_read_and_cited",
    "test_compare_cells_reuses_approved_report_statistics_and_comparability",
    "test_no_ablation_causal_attribution_remains_hypothesis",
    "test_analysis_is_read_only_for_database_artifacts_judge_and_execution",
    "test_scope_denies_cross_experiment_runs_cells_tasks_and_ablations",
    "test_trace_is_digest_verified_normalized_and_private_reasoning_is_withheld",
    "test_task_contract_hides_verifier_oracle_content_and_returns_safe_identity",
    "test_fake_analyst_e2e_is_deterministic_bounded_and_report_safe",
    "test_repository_methods_are_read_only_and_structured_not_arbitrary_sql_or_paths",
    "test_gate_j_langgraph_dependency_is_exact_and_no_agent_expansion",
}


def run(check: Check) -> bool:
    print(f"\n=== {check.name} ===", flush=True)
    print("COMMAND:", subprocess.list2cmdline(check.command), flush=True)
    try:
        result = subprocess.run(
            check.command,
            cwd=ROOT,
            check=False,
            timeout=check.timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        print(f"FAIL: command exceeded {check.timeout_seconds}s")
        return False
    print(f"{'PASS' if result.returncode == 0 else 'FAIL'}: exit={result.returncode}")
    return result.returncode == 0


def verify_environment() -> ExitCode:
    missing = [tool for tool in ("uv", "git") if shutil.which(tool) is None]
    if missing:
        print(f"NOT_VERIFIED: required Gate J tools unavailable: {missing}")
        return ExitCode.NOT_VERIFIED
    if not os.environ.get("DATABASE_URL"):
        print("NOT_VERIFIED: DATABASE_URL is required for persisted Phase J evidence")
        return ExitCode.NOT_VERIFIED
    if importlib.metadata.version("langgraph") != "1.2.11":
        print("NOT_VERIFIED: langgraph 1.2.11 is not installed")
        return ExitCode.NOT_VERIFIED
    return ExitCode.PASS


def verify_test_evidence() -> ExitCode:
    if not JUNIT.is_file():
        print("NOT_VERIFIED: Gate J JUnit evidence is unavailable")
        return ExitCode.NOT_VERIFIED
    cases = ET.parse(JUNIT).getroot().findall(".//testcase")
    if not cases:
        print("NOT_VERIFIED: Gate J collected zero tests")
        return ExitCode.NOT_VERIFIED
    skipped = [
        case.attrib.get("name", "unknown") for case in cases if case.find("skipped") is not None
    ]
    if skipped:
        print(f"NOT_VERIFIED: Gate J skipped critical evidence: {skipped}")
        return ExitCode.NOT_VERIFIED
    names = {case.attrib.get("name", "") for case in cases}
    missing = CRITICAL_TESTS - names
    if missing:
        print(f"NOT_VERIFIED: Gate J is missing critical tests: {sorted(missing)}")
        return ExitCode.NOT_VERIFIED
    if not EVIDENCE.is_file():
        print("NOT_VERIFIED: Gate J production evidence summary is unavailable")
        return ExitCode.NOT_VERIFIED
    try:
        evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        print("NOT_VERIFIED: Gate J evidence summary is unreadable")
        return ExitCode.NOT_VERIFIED
    required = {
        "ablation_id": "reasoning-effort",
        "decision_iterations": 2,
        "no_ablation_hypotheses": 1,
        "read_only_database": True,
        "read_only_source_artifacts": True,
        "tool_calls": 6,
    }
    if any(evidence.get(key) != value for key, value in required.items()):
        print(f"NOT_VERIFIED: Gate J evidence summary is incomplete: {evidence}")
        return ExitCode.NOT_VERIFIED
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", str(evidence.get("report_digest"))):
        print("NOT_VERIFIED: Gate J report digest is absent")
        return ExitCode.NOT_VERIFIED
    print(f"PASS: {len(cases)} Gate J tests recorded; critical set present; zero skipped")
    print("LANGGRAPH=1.2.11 StateGraph direct bounded local graph PASS")
    print(
        "ANALYST_TOOLS=query_runs,compare_cells,inspect_trace,inspect_failure,"
        "get_task_contract,get_ablation PASS"
    )
    print("BOUNDS=8 decision iterations; 12 total tool calls; safe structured termination PASS")
    print("READ_ONLY=source DB+artifacts+Judge+execution snapshots unchanged PASS")
    print("FACT_BINDING=structured exact-value assertions validated against catalog tool data PASS")
    print("CONTRADICTIONS=run status/outcome and numeric statistic mismatches rejected PASS")
    print("CITATIONS=fabricated refs rejected; deterministic logical identities PASS")
    print("FACT_HYPOTHESIS=causal no-ablation output remains HYPOTHESIS PASS")
    print("CONTROLLED_ABLATION=production queue/executor/manifest/report evidence cited PASS")
    print("FAKE_ANALYST=keyless deterministic JSON+Markdown+digest PASS")
    print("PROMPT_INJECTION=untrusted evidence cannot expand tools or support fake facts PASS")
    return ExitCode.PASS


def verify_scope_and_safety() -> bool:
    analyst_root = ROOT / "src/harnesslab/analyst"
    source = "\n".join(path.read_text(encoding="utf-8") for path in analyst_root.glob("*.py"))
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")
    graph = (analyst_root / "graph.py").read_text(encoding="utf-8")
    if '"langgraph==1.2.11"' not in pyproject:
        print("FAIL: langgraph dependency is not exact")
        return False
    if 'name = "langgraph"\nversion = "1.2.11"' not in lock:
        print("FAIL: uv.lock does not pin langgraph 1.2.11")
        return False
    if "StateGraph" not in graph or "create_react_agent" in source:
        print("FAIL: Phase J does not use the required explicit StateGraph")
        return False
    forbidden_runtime = (
        "DirectModelRunner",
        "ExperimentRunExecutor",
        "enqueue_plan",
        "request_cancellation",
        "subprocess",
        "httpx",
        "requests.",
        "import playwright",
        "import selenium",
        "vectorstore",
        "retriever",
        "redis",
        "celery",
        "kafka",
        "rocketmq",
        "kubernetes",
        "multi_agent",
    )
    found = [token for token in forbidden_runtime if token.lower() in source.lower()]
    if found:
        print(f"FAIL: forbidden Analyst runtime expansion detected: {found}")
        return False
    decision_backend = (analyst_root / "real_backend.py").read_text(encoding="utf-8")
    host_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in analyst_root.glob("*.py")
        if path.name != "real_backend.py"
    )
    if "ProviderAdapter" in host_source or "adapter_for_profile" not in decision_backend:
        print("FAIL: Analyst provider access must remain in its explicit existing-adapter backend")
        return False
    migrations = tuple((ROOT / "alembic/versions").glob("*analyst*"))
    if tuple(path.name for path in migrations) != ("20260908_0007_analyst_session.py",):
        print("FAIL: expected only the bounded Analyst session migration")
        return False
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    lineage = ScriptDirectory.from_config(config)
    analyst_revision = lineage.get_revision("20260908_0007")
    if (
        lineage.get_heads() != ["20260908_0007"]
        or analyst_revision is None
        or analyst_revision.down_revision != "20260904_0006"
    ):
        print("FAIL: Analyst migration must extend the single authoritative Phase M head")
        return False
    print(
        "SCOPE=six evidence tools; explicit backend; review-only session API; "
        "no execution tools PASS"
    )
    print("REAL_ANALYST_PROVIDER=NOT_RUN")
    print("REAL_SUBJECT_PROVIDER=NOT_RUN_DURING_ANALYSIS")
    print("REAL_HARNESS=NOT_RUN_DURING_ANALYSIS")
    print("REAL_JUDGE=NOT_RUN_DURING_ANALYSIS")
    return True


def main() -> int:
    environment = verify_environment()
    if environment is not ExitCode.PASS:
        return environment
    JUNIT.unlink(missing_ok=True)
    EVIDENCE.unlink(missing_ok=True)
    os.environ["HARNESSLAB_GATE_J_EVIDENCE_PATH"] = str(EVIDENCE)
    checks = (
        Check(
            "Gate J focused unit and production-path tests",
            (
                "uv",
                "run",
                "--locked",
                "pytest",
                "tests/test_analyst_contracts.py",
                "tests/test_analyst_e2e.py",
                f"--junitxml={JUNIT}",
                "-q",
            ),
        ),
        Check("Ruff lint", ("uv", "run", "--locked", "ruff", "check", ".")),
        Check("Ruff format", ("uv", "run", "--locked", "ruff", "format", "--check", ".")),
        Check("Mypy", ("uv", "run", "--locked", "mypy", "src", "tests", "scripts")),
        Check("Git whitespace", ("git", "diff", "--check")),
    )
    for check in checks:
        if not run(check):
            return ExitCode.FAIL
    evidence = verify_test_evidence()
    if evidence is not ExitCode.PASS:
        return evidence
    if not verify_scope_and_safety():
        return ExitCode.FAIL
    print("\nPHASE_J_IMPLEMENTED_AND_CI_VERIFIED=LOCAL_GATE_PASS")
    return ExitCode.PASS


if __name__ == "__main__":
    raise SystemExit(main())
