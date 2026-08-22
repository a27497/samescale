from __future__ import annotations

import inspect
import shutil
import time
from pathlib import Path

import pytest
from pydantic import ValidationError

from harnesslab.tasks.fake_subject import FakeSubjectRunner
from harnesslab.tasks.models import OutcomeCategory, VerifierReport
from harnesslab.tasks.package import MaterializedTask, TaskPackage
from harnesslab.tasks.validation import validate_task_package
from harnesslab.tasks.verifier import execute_verifier, protected_file_violations

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PYTHON_TASK = REPOSITORY_ROOT / "tasks" / "micro-python-clamp" / "1.0.0"


def copy_task(source: Path, destination_root: Path) -> Path:
    destination = destination_root / source.parent.name / source.name
    destination.parent.mkdir(parents=True)
    shutil.copytree(source, destination)
    return destination


def test_partial_score_contract_is_bounded() -> None:
    package = TaskPackage.load(PYTHON_TASK)
    materialized = package.materialize()
    try:
        result = execute_verifier(package, materialized)
    finally:
        materialized.cleanup()

    assert result.category is OutcomeCategory.SUBJECT_RESULT
    assert not result.passed
    assert 0.0 < result.score < 1.0
    with pytest.raises(ValidationError, match="less than or equal to 1"):
        VerifierReport(
            schema_version=1,
            passed=True,
            score=1.01,
            checks=({"name": "invalid", "passed": True, "score": 1.0},),
            summary="invalid score",
        )


def test_malformed_verifier_output_fails_closed(tmp_path: Path) -> None:
    task_path = copy_task(PYTHON_TASK, tmp_path)
    verifier = task_path / "verifier" / "verify.py"
    verifier.write_text("print('not-json')\n", encoding="utf-8")
    package = TaskPackage.load(task_path)
    materialized = package.materialize()
    try:
        result = execute_verifier(package, materialized)
    finally:
        materialized.cleanup()

    assert result.category is OutcomeCategory.MALFORMED_OUTPUT
    assert not result.passed
    assert result.score == 0.0
    validation = validate_task_package(task_path)
    assert not validation.valid
    assert any("verifier invalid" in error for error in validation.errors)


def test_verifier_timeout_fails_closed(tmp_path: Path) -> None:
    task_path = copy_task(PYTHON_TASK, tmp_path)
    manifest = task_path / "task.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace("timeout_seconds: 15", "timeout_seconds: 1"),
        encoding="utf-8",
    )
    verifier = task_path / "verifier" / "verify.py"
    verifier.write_text("import time\ntime.sleep(5)\n", encoding="utf-8")
    package = TaskPackage.load(task_path)
    materialized = package.materialize()
    started = time.monotonic()
    try:
        result = execute_verifier(package, materialized)
    finally:
        materialized.cleanup()

    assert time.monotonic() - started < 3
    assert result.category is OutcomeCategory.TIMEOUT
    assert not result.passed
    assert result.score == 0.0


def test_tamper_and_exposed_test_deletion_cannot_create_pass() -> None:
    package = TaskPackage.load(PYTHON_TASK)
    runner = FakeSubjectRunner()
    materialized = package.materialize()
    try:
        runner.apply(materialized.workspace, edits={}, deletes=("public_check.py",))
        assert protected_file_violations(materialized) == ("public_check.py",)

        protected_result = execute_verifier(package, materialized)
        assert protected_result.category is OutcomeCategory.PROTECTED_FILE_VIOLATION
        assert not protected_result.passed

        unprotected_view = MaterializedTask(
            root=materialized.root,
            workspace=materialized.workspace,
            context=materialized.context,
            protected_digests=(),
        )
        hidden_result = execute_verifier(package, unprotected_view)
        assert hidden_result.category is OutcomeCategory.SUBJECT_RESULT
        assert not hidden_result.passed
    finally:
        materialized.cleanup()


def test_fake_subject_runner_only_receives_subject_workspace() -> None:
    parameter_names = tuple(inspect.signature(FakeSubjectRunner.apply).parameters)
    assert parameter_names == ("self", "workspace", "edits", "deletes")

    package = TaskPackage.load(PYTHON_TASK)
    materialized = package.materialize()
    try:
        changed = FakeSubjectRunner().apply(
            materialized.workspace,
            edits={
                "calculator.py": (
                    "def clamp(value: int, lower: int, upper: int) -> int:\n"
                    "    return max(lower, min(value, upper))\n"
                )
            },
        )
        result = execute_verifier(package, materialized)

        assert changed == ("calculator.py",)
        assert result.passed
        assert not (materialized.root / "verifier").exists()
        assert not (materialized.root / "oracle").exists()
    finally:
        materialized.cleanup()


def test_fake_subject_rejects_traversal() -> None:
    package = TaskPackage.load(PYTHON_TASK)
    materialized = package.materialize()
    try:
        with pytest.raises(ValueError, match="absolute or contain"):
            FakeSubjectRunner().apply(
                materialized.workspace, edits={"../oracle/calculator.py": "tamper"}
            )
    finally:
        materialized.cleanup()
