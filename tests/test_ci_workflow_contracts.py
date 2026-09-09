from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from typing import Any

import yaml

from harnesslab.release.final_verifier import EXPECTED_WORKFLOW

ROOT = Path(__file__).resolve().parents[1]
FAST_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
FULL_WORKFLOW = ROOT / ".github" / "workflows" / "full-ci.yml"
SELF_HOSTED_FAST_WORKFLOW = ROOT / ".github" / "workflows" / "self-hosted-ci.yml"
SELF_HOSTED_FULL_WORKFLOW = ROOT / ".github" / "workflows" / "self-hosted-full-ci.yml"


def _load_verifier(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / f"scripts/{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


verify_gate_c = _load_verifier("verify_gate_c")
verify_gate_d = _load_verifier("verify_gate_d")
verify_gate_e = _load_verifier("verify_gate_e")
verify_gate_f = _load_verifier("verify_gate_f")
verify_gate_g = _load_verifier("verify_gate_g")


def _workflow(path: Path) -> dict[str, Any]:
    loaded = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert isinstance(loaded, dict)
    return loaded


def _check_names(checks: tuple[Any, ...]) -> tuple[str, ...]:
    return tuple(check.name for check in checks)


def test_gate_c_d_and_h_critical_test_names_resolve_in_selected_suites() -> None:
    for gate in ("C", "D", "H"):
        verifier = _load_verifier(f"verify_gate_{gate.lower()}")
        defined = {
            node.name
            for path in getattr(verifier, f"PHASE_{gate}_TESTS")
            for node in ast.parse((ROOT / path).read_text()).body
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        }
        required = {name.split("[", 1)[0] for name in verifier.CRITICAL_TESTS}
        assert required <= defined, f"Gate {gate} references absent tests: {required - defined}"


def test_gate_c_standalone_keeps_prerequisites_and_leaf_keeps_own_evidence() -> None:
    standalone = verify_gate_c.build_checks(leaf_only=False)
    leaf = verify_gate_c.build_checks(leaf_only=True)

    assert "Gate A regression" in _check_names(standalone)
    assert "Gate B regression" in _check_names(standalone)
    assert "Gate A regression" not in _check_names(leaf)
    assert "Gate B regression" not in _check_names(leaf)
    phase = next(check for check in leaf if check.name == "Phase C pytest")
    assert set(verify_gate_c.PHASE_C_TESTS) <= set(phase.command)
    assert verify_gate_c.CRITICAL_TESTS
    assert {"Ruff check", "Ruff format", "mypy", "git whitespace"} <= set(_check_names(leaf))


def test_gate_d_standalone_keeps_prerequisites_and_leaf_keeps_own_evidence() -> None:
    standalone = verify_gate_d.build_checks(leaf_only=False)
    leaf = verify_gate_d.build_checks(leaf_only=True)

    assert "Gate C regression (includes Gate A and Gate B)" in _check_names(standalone)
    assert "Gate C regression (includes Gate A and Gate B)" not in _check_names(leaf)
    phase = next(check for check in leaf if check.name == "Phase D pytest")
    assert set(verify_gate_d.PHASE_D_TESTS) <= set(phase.command)
    assert verify_gate_d.CRITICAL_TESTS
    assert {"Ruff check", "Ruff format", "mypy", "git whitespace"} <= set(_check_names(leaf))


def test_leaf_mode_requires_explicit_github_actions_context(monkeypatch: Any) -> None:
    for module in (verify_gate_c, verify_gate_d):
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.delenv(module.CI_LEAF_MODE_ENV, raising=False)
        assert not module.ci_leaf_mode_authorized()

        monkeypatch.setenv("CI", "true")
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        monkeypatch.setenv(module.CI_LEAF_MODE_ENV, "1")
        assert module.ci_leaf_mode_authorized()


def test_repository_secret_scanners_require_a_token_boundary() -> None:
    false_positive = b"task-package-frozen-workspace-v1"
    provider_credential = b'credential="sk-' + (b"a" * 24) + b'"'
    github_credential = b'token="ghp_' + (b"b" * 24) + b'"'

    for module in (verify_gate_d, verify_gate_e, verify_gate_f, verify_gate_g):
        assert not any(pattern.search(false_positive) for pattern in module.SECRET_PATTERNS)
        assert any(pattern.search(provider_credential) for pattern in module.SECRET_PATTERNS)
    for module in (verify_gate_e, verify_gate_f, verify_gate_g):
        assert any(pattern.search(github_credential) for pattern in module.SECRET_PATTERNS)


def test_fast_and_full_workflow_triggers_and_concurrency_are_bounded() -> None:
    fast = _workflow(FAST_WORKFLOW)
    full = _workflow(FULL_WORKFLOW)

    assert set(fast["on"]) == {"push", "pull_request"}
    assert set(full["on"]) == {"workflow_dispatch"}
    assert full["name"] == EXPECTED_WORKFLOW
    for workflow in (fast, full):
        concurrency = workflow["concurrency"]
        assert concurrency["group"] == "harnesslab-ci-${{ github.workflow }}-${{ github.ref }}"
        assert concurrency["cancel-in-progress"] == "true"


def test_full_workflow_runs_isolated_parallel_gates_without_nested_regressions() -> None:
    workflow = _workflow(FULL_WORKFLOW)
    gate_job = workflow["jobs"]["gates"]
    entries = gate_job["strategy"]["matrix"]["include"]
    commands = {entry["gate"]: entry["command"] for entry in entries}

    assert set(commands) == set("ABCDEFGHIJK")
    assert commands["C"].endswith("scripts/verify_gate_c.py --leaf-only")
    assert commands["D"].endswith("scripts/verify_gate_d.py --leaf-only")
    assert all(
        "--leaf-only" not in command for gate, command in commands.items() if gate not in "CD"
    )
    assert "needs" not in gate_job
    assert gate_job["strategy"]["fail-fast"] == "false"
    assert gate_job["services"]["postgres"]
    assert gate_job["env"]["HARNESSLAB_CI_LEAF_MODE"] == "1"
    prepared = {entry["gate"] for entry in entries if entry.get("prepare_database") == "true"}
    assert prepared == {"I", "J"}
    assert any("actions/checkout@" in step.get("uses", "") for step in gate_job["steps"])
    assert any(
        step.get("name") == "Bootstrap isolated gate database"
        and step.get("if") == "${{ matrix.prepare_database == true }}"
        and step.get("run") == "uv run --locked alembic upgrade head"
        for step in gate_job["steps"]
    )
    assert any(
        step.get("name") == "Run authoritative Gate ${{ matrix.gate }} verification"
        for step in gate_job["steps"]
    )

    fresh = workflow["jobs"]["fresh-setup"]
    assert set(fresh["needs"]) == {"qualification", "gates"}
    assert "--actions-reproduction" in FULL_WORKFLOW.read_text(encoding="utf-8")


def test_v6_canary_control_runs_in_fast_and_full_release_ci() -> None:
    fast_text = FAST_WORKFLOW.read_text(encoding="utf-8")
    full = _workflow(FULL_WORKFLOW)
    qualifications = full["jobs"]["qualification"]["strategy"]["matrix"]["include"]
    v6 = next(item for item in qualifications if item["id"] == "v6-canary-control")

    assert "tests/test_kb3_v6_canary.py" in fast_text
    assert "tests/test_kb3_v6_canary.py" in v6["command"]
    assert "tests/test_kb3_v6_integration.py" in fast_text
    assert "tests/test_kb3_v6_integration.py" in v6["command"]
    assert "tests/test_kb3_v6_throughput_r2.py" in fast_text
    assert "tests/test_kb3_v6_throughput_r2.py" in v6["command"]
    assert "tests/test_kb3_v6.py" in v6["command"]
    assert v6["prepare_database"] == "true"
    qualification_steps = full["jobs"]["qualification"]["steps"]
    assert any(
        step.get("name") == "Bootstrap qualification database"
        and step.get("if") == "${{ matrix.prepare_database == true }}"
        and step.get("run") == "uv run --locked alembic upgrade head"
        for step in qualification_steps
    )


def test_full_workflow_is_keyless_and_fast_ci_preserves_legacy_gate_status() -> None:
    fast = _workflow(FAST_WORKFLOW)
    full_text = FULL_WORKFLOW.read_text(encoding="utf-8")

    assert fast["jobs"]["gates"]["name"] == "gates"
    assert "verify_tier_a_verifier_robustness_v2.py" in full_text
    assert "freeze_model_chat_v3.py" in full_text
    assert "freeze_model_chat_v3r1.py" in full_text
    assert "HARNESSLAB_ENABLE_REAL" not in full_text
    assert "--allow-real" not in full_text


def test_self_hosted_workflows_are_manual_only_and_repository_read_only() -> None:
    for path in (SELF_HOSTED_FAST_WORKFLOW, SELF_HOSTED_FULL_WORKFLOW):
        workflow = _workflow(path)
        assert set(workflow["on"]) == {"workflow_dispatch", "workflow_call"}
        assert workflow["permissions"] == {"contents": "read"}
        assert workflow["concurrency"]["cancel-in-progress"] == "false"
        for job in workflow["jobs"].values():
            assert job["runs-on"] == ["self-hosted", "linux", "x64", "harnesslab-tokyo"]


def test_self_hosted_full_release_preserves_matrix_contract_and_caps_parallelism() -> None:
    hosted = _workflow(FULL_WORKFLOW)
    self_hosted = _workflow(SELF_HOSTED_FULL_WORKFLOW)

    for job_name in ("qualification", "gates"):
        hosted_job = hosted["jobs"][job_name]
        self_hosted_job = self_hosted["jobs"][job_name]
        assert self_hosted_job["strategy"]["matrix"] == hosted_job["strategy"]["matrix"]
        assert self_hosted_job["strategy"]["fail-fast"] == "false"
        assert self_hosted_job["strategy"]["max-parallel"] == "3"
        assert "services" not in self_hosted_job
        steps = self_hosted_job["steps"]
        assert any(step.get("run") == "scripts/ci_job_postgres.sh start" for step in steps)
        assert any(
            step.get("run") == "scripts/ci_job_postgres.sh cleanup-current"
            and step.get("if") == "${{ always() }}"
            for step in steps
        )

    fresh = self_hosted["jobs"]["fresh-setup"]
    assert set(fresh["needs"]) == {"qualification", "gates"}
    assert "--actions-reproduction" in SELF_HOSTED_FULL_WORKFLOW.read_text(encoding="utf-8")
    assert "SELF_HOSTED_FRESH_SETUP=PASS" in SELF_HOSTED_FULL_WORKFLOW.read_text(encoding="utf-8")


def test_self_hosted_fast_ci_preserves_hosted_fast_commands_without_fixed_port() -> None:
    hosted = _workflow(FAST_WORKFLOW)["jobs"]["gates"]
    self_hosted = _workflow(SELF_HOSTED_FAST_WORKFLOW)["jobs"]["gates"]
    hosted_runs = {step.get("name"): step.get("run") for step in hosted["steps"] if "run" in step}
    self_hosted_runs = {
        step.get("name"): step.get("run") for step in self_hosted["steps"] if "run" in step
    }
    for name in (
        "Install pinned Python",
        "Sync locked dependencies",
        "Upgrade test database",
        "Lint, format, type, and whitespace checks",
        "Run bounded deterministic core regressions",
    ):
        assert self_hosted_runs[name] == hosted_runs[name]
    assert "services" not in self_hosted
    assert any(
        step.get("name") == "Install Java 21"
        and step.get("with") == {"distribution": "temurin", "java-version": "21"}
        for step in self_hosted["steps"]
    )
    assert any(
        step.get("name") == "Install Node 24"
        and step.get("with") == {"node-version": "24", "package-manager-cache": "false"}
        for step in self_hosted["steps"]
    )
    assert "5432:5432" not in SELF_HOSTED_FAST_WORKFLOW.read_text(encoding="utf-8")
    assert "5432:5432" not in SELF_HOSTED_FULL_WORKFLOW.read_text(encoding="utf-8")


def test_ci_postgres_helper_uses_job_identity_dynamic_port_and_targeted_cleanup() -> None:
    helper = (ROOT / "scripts" / "ci_job_postgres.sh").read_text(encoding="utf-8")
    for identity in (
        "GITHUB_REPOSITORY",
        "GITHUB_RUN_ID",
        "GITHUB_RUN_ATTEMPT",
        "GITHUB_JOB",
        "RUNNER_NAME",
    ):
        assert identity in helper
    assert "--publish 127.0.0.1::5432" in helper
    assert "docker system prune" not in helper
    assert "docker container prune" not in helper
    assert "docker network prune" not in helper
    assert "label=${LABEL_PREFIX}.repository=${GITHUB_REPOSITORY}" in helper
    assert "label=${LABEL_PREFIX}.runner=${RUNNER_NAME}" in helper


def test_registered_full_release_workflow_bootstraps_same_ref_tokyo_workflows() -> None:
    workflow = _workflow(FULL_WORKFLOW)
    dispatch = workflow["on"]["workflow_dispatch"]
    execution_target = dispatch["inputs"]["execution_target"]

    assert execution_target["required"] == "true"
    assert execution_target["default"] == "hosted"
    assert execution_target["type"] == "choice"
    assert execution_target["options"] == ["hosted", "tokyo-fast", "tokyo-full"]

    for job_name in ("qualification", "gates", "fresh-setup"):
        assert workflow["jobs"][job_name]["if"] == "${{ inputs.execution_target == 'hosted' }}"
    assert workflow["jobs"]["tokyo-fast"] == {
        "name": "Tokyo self-hosted Fast CI",
        "if": "${{ inputs.execution_target == 'tokyo-fast' }}",
        "uses": "./.github/workflows/self-hosted-ci.yml",
    }
    assert workflow["jobs"]["tokyo-full"] == {
        "name": "Tokyo self-hosted Full Release CI",
        "if": "${{ inputs.execution_target == 'tokyo-full' }}",
        "uses": "./.github/workflows/self-hosted-full-ci.yml",
    }


def test_fast_ci_checks_frontend_and_dto_without_full_release_gates() -> None:
    for path in (FAST_WORKFLOW, SELF_HOSTED_FAST_WORKFLOW):
        job = _workflow(path)["jobs"]["gates"]
        steps = job["steps"]
        frontend = next(
            (step for step in steps if step.get("name") == "Check frontend contracts"), None
        )
        assert frontend is not None, "Fast CI leaves frontend/DTO changes unchecked"
        assert frontend["working-directory"] == "frontend"
        assert "if" not in frontend  # Includes frontend, backend DTO, and shared contract changes.
        assert frontend["run"].splitlines() == [
            "npm ci --no-audit --no-fund",
            "npm run type-check",
            "npm run test -- tests/workbench.spec.ts tests/registry.spec.ts "
            "tests/diagnosis.spec.ts tests/analyst.spec.ts",
        ]
        assert "continue-on-error" not in frontend
        assert any("actions/setup-node@" in step.get("uses", "") for step in steps)
        commands = "\n".join(step.get("run", "") for step in steps)
        assert "verify_gate_" not in commands
        assert "tests/test_experiment_queue.py" in commands
        assert "tests/test_experiment_tool_metrics.py" in commands
        assert "tests/test_analyst_sessions.py" in commands
        assert (
            "tests/test_workbench_api.py::"
            "test_frontend_dtos_contain_no_absolute_path_credential_or_private_sentinel"
        ) in commands
