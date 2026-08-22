from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from harnesslab.cli import app
from harnesslab.tasks.models import OutcomeCategory
from harnesslab.tasks.validation import validate_task_package

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TASKS = (
    REPOSITORY_ROOT / "tasks" / "micro-python-clamp" / "1.0.0",
    REPOSITORY_ROOT / "tasks" / "micro-java-clamp" / "1.0.0",
    REPOSITORY_ROOT / "tasks" / "micro-typescript-clamp" / "1.0.0",
)


def copy_task(source: Path, destination_root: Path) -> Path:
    destination = destination_root / source.parent.name / source.name
    destination.parent.mkdir(parents=True)
    shutil.copytree(source, destination)
    return destination


def test_three_fixture_polarity_and_hidden_asset_isolation() -> None:
    results = [validate_task_package(path) for path in TASKS]

    assert {result.task_id for result in results} == {
        "micro-python-clamp",
        "micro-java-clamp",
        "micro-typescript-clamp",
    }
    for result in results:
        assert result.valid
        assert result.baseline.result.category is OutcomeCategory.SUBJECT_RESULT
        assert not result.baseline.result.passed
        assert result.oracle.result.category is OutcomeCategory.SUBJECT_RESULT
        assert result.oracle.result.passed
        assert result.oracle.result.score == 1.0
        assert result.baseline.workspace_digest != result.oracle.workspace_digest


def test_cli_validates_all_three_fixtures_without_hidden_content() -> None:
    runner = CliRunner()
    for task_path in TASKS:
        result = runner.invoke(app, ["task", "validate", str(task_path)])

        assert result.exit_code == 0, result.stdout
        assert "baseline: passed=False" in result.stdout
        assert "oracle: passed=True" in result.stdout
        assert "validation: PASS" in result.stdout
        assert "def clamp" not in result.stdout
        assert "HiddenVerifier" not in result.stdout


def test_polarity_validation_rejects_baseline_pass_and_oracle_fail(tmp_path: Path) -> None:
    baseline_passes = copy_task(TASKS[0], tmp_path / "baseline-passes")
    shutil.copyfile(
        baseline_passes / "oracle" / "calculator.py",
        baseline_passes / "workspace" / "calculator.py",
    )
    baseline_result = validate_task_package(baseline_passes)
    assert not baseline_result.valid
    assert "untouched baseline unexpectedly passed" in baseline_result.errors

    oracle_fails = copy_task(TASKS[0], tmp_path / "oracle-fails")
    shutil.copyfile(
        oracle_fails / "workspace" / "calculator.py",
        oracle_fails / "oracle" / "calculator.py",
    )
    oracle_result = validate_task_package(oracle_fails)
    assert not oracle_result.valid
    assert "oracle overlay did not pass" in oracle_result.errors


def test_digest_reproducibility_check_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("harnesslab.tasks.validation.digest_tree", lambda _: "sha256:" + "0" * 64)

    result = validate_task_package(TASKS[0])

    assert not result.valid
    assert "task digest is not reproducible" in result.errors
