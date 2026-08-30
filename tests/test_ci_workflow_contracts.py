from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import yaml

from harnesslab.release.final_verifier import EXPECTED_WORKFLOW

ROOT = Path(__file__).resolve().parents[1]
FAST_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
FULL_WORKFLOW = ROOT / ".github" / "workflows" / "full-ci.yml"


def _load_verifier(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / f"scripts/{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


verify_gate_c = _load_verifier("verify_gate_c")
verify_gate_d = _load_verifier("verify_gate_d")
verify_gate_g = _load_verifier("verify_gate_g")


def _workflow(path: Path) -> dict[str, Any]:
    loaded = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert isinstance(loaded, dict)
    return loaded


def _check_names(checks: tuple[Any, ...]) -> tuple[str, ...]:
    return tuple(check.name for check in checks)


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


def test_gate_g_secret_scan_requires_a_token_boundary() -> None:
    false_positive = b"task-package-frozen-workspace-v1"
    provider_credential = b'credential="sk-' + (b"a" * 24) + b'"'
    github_credential = b'token="ghp_' + (b"b" * 24) + b'"'

    assert not any(pattern.search(false_positive) for pattern in verify_gate_g.SECRET_PATTERNS)
    assert any(pattern.search(provider_credential) for pattern in verify_gate_g.SECRET_PATTERNS)
    assert any(pattern.search(github_credential) for pattern in verify_gate_g.SECRET_PATTERNS)


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


def test_full_workflow_is_keyless_and_fast_ci_preserves_legacy_gate_status() -> None:
    fast = _workflow(FAST_WORKFLOW)
    full_text = FULL_WORKFLOW.read_text(encoding="utf-8")

    assert fast["jobs"]["gates"]["name"] == "gates"
    assert "verify_tier_a_verifier_robustness_v2.py" in full_text
    assert "freeze_model_chat_v3.py" in full_text
    assert "freeze_model_chat_v3r1.py" in full_text
    assert "HARNESSLAB_ENABLE_REAL" not in full_text
    assert "--allow-real" not in full_text
