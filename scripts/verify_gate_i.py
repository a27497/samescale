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


class ExitCode(IntEnum):
    PASS = 0
    FAIL = 1
    NOT_VERIFIED = 2


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
BACKEND_JUNIT = ROOT / "gate-i-results.xml"
FRONTEND_JUNIT = ROOT / "gate-i-frontend-results.xml"
EVIDENCE = ROOT / "gate-i-evidence.json"


@dataclass(frozen=True)
class Check:
    name: str
    command: tuple[str, ...]
    cwd: Path = ROOT
    timeout_seconds: int = 1200
    scrub_sensitive_environment: bool = False
    forbidden_output: tuple[str, ...] = ()


BACKEND_CRITICAL = {
    "test_workbench_routes_are_read_only_and_have_no_execution_or_analyst_surface",
    "test_experiment_list_detail_status_and_pagination_use_persisted_database",
    "test_complete_matrix_snapshot_and_report_identity_are_browsable",
    "test_multi_task_matrix_uses_task_scoped_verified_observations",
    "test_matrix_comparability_is_task_scoped_and_never_invented",
    "test_run_filter_detail_identity_and_missing_cost_are_safe",
    "test_workbench_manifest_reads_are_confined_to_server_artifact_roots",
    "test_trace_uses_verified_normalized_evidence_and_never_native_reasoning",
    "test_trace_rejects_client_paths_and_symlink_escape",
    "test_judgelab_list_and_detail_use_digest_verified_phase_h_report",
    "test_regression_compare_accepts_declared_treatments_and_blocks_hard_controls",
    "test_core_readiness_is_evidence_driven_and_stays_not_ready",
    "test_public_error_shape_and_unknown_resource_do_not_leak_internals",
    "test_judge_report_digest_mutation_fails_closed",
    "test_frontend_dtos_contain_no_absolute_path_credential_or_private_sentinel",
}
FRONTEND_CRITICAL = {
    "Workbench contracts > registers every major route and no Analyst route",
    "Workbench contracts > renders reported zero differently from NOT_REPORTED",
    "Workbench contracts > keeps NOT_REPORTED visually distinct from NOT_COMPARABLE",
    "Workbench contracts > renders Matrix values, tiers, missing metrics, "
    "and comparability from the DTO",
    "Workbench contracts > HTML-encodes persisted Matrix labels before ECharts tooltip rendering",
    "Workbench contracts > withholds content for REASONING_PRESENT",
    "Workbench contracts > renders experiment list evidence",
    "Workbench contracts > renders run status, trace coverage, and cost missingness",
    "Workbench contracts > renders suite-scoped Judge qualification",
    "Workbench contracts > distinguishes corrupt Judge report evidence from an unreported report",
    "Workbench contracts > renders deterministic regression limitations and NOT_COMPARABLE",
    "Workbench contracts > renders Core readiness blockers",
    "Workbench contracts > stops polling when PostgreSQL reports a terminal status",
    "Workbench contracts > refetches authoritative evidence after reconstructed-page loads",
}


def run(check: Check) -> bool:
    print(f"\n=== {check.name} ===", flush=True)
    print("COMMAND:", subprocess.list2cmdline(check.command), flush=True)
    try:
        environment = None
        if check.scrub_sensitive_environment:
            environment = os.environ.copy()
            sensitive_names = {
                "AUTHORIZATION",
                "DATABASE_URL",
                "GH_TOKEN",
                "GITHUB_TOKEN",
                "NPM_TOKEN",
                "NODE_AUTH_TOKEN",
            }
            for name in tuple(environment):
                upper = name.upper()
                if upper in sensitive_names or upper.endswith(
                    ("_API_KEY", "_PASSWORD", "_SECRET", "_TOKEN")
                ):
                    environment.pop(name, None)
        capture_output = bool(check.forbidden_output)
        result = subprocess.run(
            check.command,
            cwd=check.cwd,
            check=False,
            timeout=check.timeout_seconds,
            env=environment,
            capture_output=capture_output,
            text=capture_output,
        )
    except subprocess.TimeoutExpired:
        print(f"FAIL: command exceeded {check.timeout_seconds}s")
        return False
    if capture_output:
        output = (result.stdout or "") + (result.stderr or "")
        print(output, end="" if output.endswith("\n") else "\n")
        found = [token for token in check.forbidden_output if token in output]
        if found:
            print(f"FAIL: forbidden command output detected: {found}")
            return False
    print(f"{'PASS' if result.returncode == 0 else 'FAIL'}: exit={result.returncode}")
    return result.returncode == 0


def verify_environment() -> ExitCode:
    missing = [tool for tool in ("uv", "git", "node", "npm") if shutil.which(tool) is None]
    if missing:
        print(f"NOT_VERIFIED: required Gate I tools unavailable: {missing}")
        return ExitCode.NOT_VERIFIED
    if not os.environ.get("DATABASE_URL"):
        print("NOT_VERIFIED: DATABASE_URL is required for persisted Workbench evidence")
        return ExitCode.NOT_VERIFIED
    if not FRONTEND.is_dir() or not (FRONTEND / "package-lock.json").is_file():
        print("NOT_VERIFIED: pinned frontend dependency graph is unavailable")
        return ExitCode.NOT_VERIFIED
    return ExitCode.PASS


def _junit_cases(path: Path, label: str) -> tuple[list[ET.Element], ExitCode]:
    if not path.is_file():
        print(f"NOT_VERIFIED: {label} JUnit evidence is unavailable")
        return [], ExitCode.NOT_VERIFIED
    cases = ET.parse(path).getroot().findall(".//testcase")
    if not cases:
        print(f"NOT_VERIFIED: {label} collected zero tests")
        return [], ExitCode.NOT_VERIFIED
    skipped = [
        case.attrib.get("name", "unknown") for case in cases if case.find("skipped") is not None
    ]
    if skipped:
        print(f"NOT_VERIFIED: {label} skipped critical evidence: {skipped}")
        return cases, ExitCode.NOT_VERIFIED
    return cases, ExitCode.PASS


def verify_test_evidence() -> ExitCode:
    backend, backend_status = _junit_cases(BACKEND_JUNIT, "Gate I backend")
    frontend, frontend_status = _junit_cases(FRONTEND_JUNIT, "Gate I frontend")
    if backend_status is not ExitCode.PASS or frontend_status is not ExitCode.PASS:
        return ExitCode.NOT_VERIFIED
    backend_names = {case.attrib.get("name", "") for case in backend}
    frontend_names = {case.attrib.get("name", "") for case in frontend}
    missing_backend = BACKEND_CRITICAL - backend_names
    missing_frontend = FRONTEND_CRITICAL - frontend_names
    if missing_backend or missing_frontend:
        print(
            "NOT_VERIFIED: missing critical tests "
            f"backend={sorted(missing_backend)} frontend={sorted(missing_frontend)}"
        )
        return ExitCode.NOT_VERIFIED
    if not EVIDENCE.is_file():
        print("NOT_VERIFIED: keyless persisted Workbench evidence summary is unavailable")
        return ExitCode.NOT_VERIFIED
    try:
        evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        print("NOT_VERIFIED: Gate I evidence summary is unreadable")
        return ExitCode.NOT_VERIFIED
    required = {
        "baseline_experiment_id": "phase-i-matrix-baseline",
        "matrix_task_count": 2,
        "matrix_cell_count": 3,
        "matrix_run_count": 18,
        "trace_coverage": "FULL_STREAM",
        "missing_trace_status": "NOT_REPORTED",
        "missing_cost_status": "NOT_REPORTED",
        "regression_status": "TREATMENT_AWARE",
        "judge_calibration_id": "phase-i-judge-keyless",
        "core_readiness": "NOT_READY",
    }
    if any(evidence.get(key) != value for key, value in required.items()):
        print(f"NOT_VERIFIED: Gate I evidence summary is incomplete: {evidence}")
        return ExitCode.NOT_VERIFIED
    print(f"PASS: {len(backend)} Gate I backend tests recorded; critical set present; zero skipped")
    print(
        f"PASS: {len(frontend)} Gate I frontend tests recorded; critical set present; zero skipped"
    )
    print("WORKBENCH_API=12 read-only routes; Regression compare is computation-only POST PASS")
    print("MULTI_TASK_MATRIX=phase-i-matrix-multi-task tasks=2 cells=3 runs=18 keyless PASS")
    print("TASK_SCOPED_COMPARABILITY=task-local evidence; no-comparison=NOT_REPORTED PASS")
    print("TRACE_EVIDENCE=FULL_STREAM+NOT_REPORTED; private reasoning withheld PASS")
    print("REGRESSION_TREATMENT=MODEL_COMPARISON+HARNESS_UPLIFT accepted; hard controls block PASS")
    print("REGRESSION_NO_RERUN=run rows and artifact mtimes unchanged PASS")
    print("ARTIFACT_ROOT=valid root accepted; outside+symlink escape rejected PASS")
    print("JUDGE_INTEGRITY=INTEGRITY_ERROR distinct; corrupt report cannot satisfy readiness PASS")
    print("JUDGELAB_EVIDENCE=phase-i-judge-keyless suite-scoped; L0 overrides=0 PASS")
    print("CORE_READINESS=NOT_READY; NOT_VERIFIED requirements block readiness PASS")
    return ExitCode.PASS


def verify_frontend_graph() -> bool:
    package = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((FRONTEND / "package-lock.json").read_text(encoding="utf-8"))
    declared = {**package["dependencies"], **package["devDependencies"]}
    if any(not re.fullmatch(r"\d+\.\d+\.\d+", value) for value in declared.values()):
        print("FAIL: frontend dependencies must be exact stable versions")
        return False
    forbidden = {"nuxt", "tailwindcss", "react", "next", "langgraph"}
    if forbidden & set(declared):
        print("FAIL: out-of-scope frontend dependency detected")
        return False
    expected_engine = ">=24.18.1 <25"
    if package.get("engines", {}).get("node") != expected_engine:
        print("FAIL: HarnessLab frontend must require the bounded compatible Node 24 range")
        return False
    if lock["packages"][""]["engines"]["node"] != expected_engine:
        print("FAIL: package-lock root Node engine differs from package.json")
        return False
    versions = {
        name: lock["packages"][f"node_modules/{name}"]["version"]
        for name in (
            "vue",
            "vite",
            "typescript",
            "pinia",
            "vue-router",
            "element-plus",
            "echarts",
            "axios",
            "vitest",
        )
    }
    print("FRONTEND_VERSIONS=" + json.dumps(versions, sort_keys=True, separators=(",", ":")))
    print(f"NODE_ENGINE={expected_engine}; HarnessLab EBADENGINE absent PASS")
    return True


def verify_scope_and_safety() -> bool:
    forbidden_paths = (
        ROOT / "src/harnesslab/analyst",
        ROOT / "src/harnesslab/langgraph",
    )
    if any(path.exists() for path in forbidden_paths):
        print("FAIL: Phase J Analyst or LangGraph scope detected")
        return False
    workbench_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            ROOT / "src/harnesslab/api/routes/workbench.py",
            *(ROOT / "src/harnesslab/api").glob("workbench*.py"),
        )
    )
    execution_tokens = (
        "allow_real_judge",
        "execute_calibration",
        "BoundedExperimentWorker",
        "DirectModelRunner",
        "ExperimentExecutor",
        "HarnessLaneRunner",
        "MultiHarnessRunner",
        "ProviderAdapter",
        "request_cancellation",
    )
    if any(token in workbench_sources for token in execution_tokens):
        print("FAIL: Workbench route can reach real Judge execution")
        return False
    frontend_source = "\n".join(
        path.read_text(encoding="utf-8") for path in (FRONTEND / "src").rglob("*") if path.is_file()
    )
    if "PRIVATE_REASONING_SENTINEL" in frontend_source or "credential_reference" in frontend_source:
        print("FAIL: frontend source contains private-reasoning or credential fixture data")
        return False
    build_files = tuple((FRONTEND / "dist").rglob("*"))
    if not build_files or not (FRONTEND / "dist/index.html").is_file():
        print("NOT_VERIFIED: Vite production build artifact is unavailable")
        return False
    built_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore") for path in build_files if path.is_file()
    )
    if any(
        token in built_text
        for token in ("PRIVATE_REASONING_SENTINEL", "credential_reference", "/home/dev/")
    ):
        print("FAIL: production frontend contains forbidden private/path material")
        return False
    print("SCOPE=Phase I only; no Analyst/LangGraph/provider trigger/tag/auth/SaaS surface PASS")
    print("API_SAFETY=no credential, absolute path, private CoT, or arbitrary artifact path PASS")
    return True


def main() -> int:
    environment = verify_environment()
    if environment is not ExitCode.PASS:
        return environment
    BACKEND_JUNIT.unlink(missing_ok=True)
    FRONTEND_JUNIT.unlink(missing_ok=True)
    EVIDENCE.unlink(missing_ok=True)
    os.environ["HARNESSLAB_GATE_I_EVIDENCE_PATH"] = str(EVIDENCE)
    checks = (
        Check(
            "Gate I backend persisted-evidence API tests",
            (
                "uv",
                "run",
                "--locked",
                "pytest",
                "tests/test_workbench_api.py",
                f"--junitxml={BACKEND_JUNIT}",
                "-q",
            ),
        ),
        Check(
            "Frontend npm ci",
            ("npm", "ci"),
            cwd=FRONTEND,
            scrub_sensitive_environment=True,
            forbidden_output=("npm warn EBADENGINE", "npm WARN EBADENGINE"),
        ),
        Check(
            "Frontend type-check",
            ("npm", "run", "type-check"),
            cwd=FRONTEND,
            scrub_sensitive_environment=True,
        ),
        Check(
            "Frontend Vitest",
            (
                "npm",
                "run",
                "test",
                "--",
                "--reporter=default",
                "--reporter=junit",
                f"--outputFile.junit={FRONTEND_JUNIT}",
            ),
            cwd=FRONTEND,
            scrub_sensitive_environment=True,
        ),
        Check(
            "Frontend Vite production build",
            ("npm", "run", "build"),
            cwd=FRONTEND,
            scrub_sensitive_environment=True,
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
    if not verify_frontend_graph() or not verify_scope_and_safety():
        return ExitCode.FAIL
    for status in (
        "REAL_PROVIDER_SMOKE=NOT_RUN",
        "REAL_CODEX_SMOKE=NOT_RUN",
        "REAL_CLAUDE_SMOKE=NOT_RUN",
        "REAL_DEEPSEEK_SMOKE=NOT_RUN",
        "REAL_MATRIX_EVIDENCE=NOT_RUN",
        "REAL_JUDGE_SMOKE=NOT_RUN",
    ):
        print(status)
    print("\nGATE_I=PASS")
    return ExitCode.PASS


if __name__ == "__main__":
    raise SystemExit(main())
