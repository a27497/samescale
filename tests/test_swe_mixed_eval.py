from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def mixed() -> ModuleType:
    spec = importlib.util.spec_from_file_location("mixed", ROOT / "scripts/swe_mixed_eval.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_selection_balances_repos_and_has_distinct_pilot(mixed: ModuleType) -> None:
    config = mixed.load(ROOT / "evaluation/coding-agent/mixed-config.json")
    rows = [
        {
            "instance_id": f"{repo}-{i}",
            "repo": repo,
            "base_commit": "a" * 40,
            "patch": "patch",
            "test_patch": "tests",
            "problem_statement": "issue",
            "FAIL_TO_PASS": '["f"]',
        }
        for repo in config["repositories"]
        for i in range(10)
    ]
    selected, pilot = mixed.selection(rows, config)
    assert (selected, pilot) == mixed.selection(list(reversed(rows)), config)
    assert len(selected) == 25 and len(pilot) == 3
    assert len({row["repo"] for row in selected if row["instance_id"] in pilot}) == 3
    for repo in config["repositories"]:
        assert sum(row["repo"] == repo for row in selected) == 5
    with pytest.raises(ValueError, match="duplicate"):
        mixed.selection([*rows, rows[0]], config)
    with pytest.raises(ValueError, match="no silent replacement"):
        mixed.selection(rows[:2], config)


def test_gate_has_no_environment_override(
    mixed: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HARNESSLAB_ENABLE_REAL_CODEX", "1")
    monkeypatch.setenv("HARNESSLAB_REAL_CODEX_ENABLED", "true")
    result = mixed.gate()
    assert result["status"] == "BLOCKED" and result["code"] == "REAL_EXECUTION_BLOCKED"
    assert result["model_calls"] == 0 and result["credential_access"] == "NONE"


def test_zero_or_missing_checks_and_gold_failure_refuse(mixed: ModuleType) -> None:
    base = {
        "found": True,
        "parsed_tests": 2,
        "expected_f2p": 1,
        "all_f2p_fail": True,
        "all_p2p_pass": True,
        "missing_required_tests": [],
    }
    gold = {
        "found": True,
        "parsed_tests": 2,
        "all_f2p_pass": True,
        "all_p2p_pass": True,
        "missing_required_tests": [],
        "report": {"x": {"resolved": True}},
    }
    assert mixed.control_success(base, gold, "x")
    assert not mixed.control_success({**base, "parsed_tests": 0}, gold, "x")
    assert not mixed.control_success({**base, "missing_required_tests": ["f"]}, gold, "x")
    assert not mixed.control_success(base, {**gold, "all_p2p_pass": False}, "x")
    assert not mixed.control_success({**base, "all_f2p_fail": False}, gold, "x")


def test_cli_preserves_venv_interpreter_symlink(
    mixed: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys

    binary = tmp_path / "venv/bin/python"
    binary.parent.mkdir(parents=True)
    binary.symlink_to(sys.executable)
    captured: list[Path] = []
    monkeypatch.setattr(
        mixed,
        "preflight",
        lambda root, python, label, instance_id, reporting: captured.append(python),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["mixed", "preflight", "--root", str(tmp_path), "--upstream-python", str(binary)],
    )
    mixed.main()
    assert captured == [binary]


def test_upstream_stderr_markers_surround_stdout_tests(mixed: ModuleType, tmp_path: Path) -> None:
    import shlex

    producer = tmp_path / "upstream.sh"
    producer.write_text("printf 'START\\n' >&2\nprintf 'PASSED test_one\\n'\nprintf 'END\\n' >&2\n")
    command = mixed.merged_shell_command("bash " + shlex.quote(str(producer)))
    result = mixed.run_capture(["bash", "-c", command], tmp_path / "control", timeout=5)
    assert result["exit_code"] == 0
    assert (tmp_path / "control.stdout").read_text() == "START\nPASSED test_one\nEND\n"
    assert (tmp_path / "control.stderr").read_bytes() == b""
