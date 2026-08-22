from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from harnesslab.tasks.package import TaskPackage, TaskPackageError, digest_tree
from harnesslab.tasks.validation import validate_task_package

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PYTHON_TASK = REPOSITORY_ROOT / "tasks" / "micro-python-clamp" / "1.0.0"
TYPESCRIPT_TASK = REPOSITORY_ROOT / "tasks" / "micro-typescript-clamp" / "1.0.0"


def copy_task(source: Path, destination_root: Path) -> Path:
    destination = destination_root / source.parent.name / source.name
    destination.parent.mkdir(parents=True)
    shutil.copytree(source, destination)
    return destination


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        ("workspace_path: ../workspace", "absolute or contain"),
        ("workspace_path: /tmp/workspace", "absolute or contain"),
        ("workspace_path: C:/workspace", "workspace must be under"),
    ],
)
def test_manifest_rejects_unsafe_paths(tmp_path: Path, replacement: str, message: str) -> None:
    task_path = copy_task(PYTHON_TASK, tmp_path)
    manifest = task_path / "task.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace("workspace_path: workspace", replacement),
        encoding="utf-8",
    )

    with pytest.raises(TaskPackageError, match=message):
        TaskPackage.load(task_path)


def test_manifest_rejects_unknown_and_duplicate_fields(tmp_path: Path) -> None:
    task_path = copy_task(PYTHON_TASK, tmp_path)
    manifest = task_path / "task.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8") + "unknown_phase_b_field: true\n",
        encoding="utf-8",
    )
    with pytest.raises(TaskPackageError, match="extra_forbidden"):
        TaskPackage.load(task_path)

    task_path = copy_task(PYTHON_TASK, tmp_path / "duplicate")
    manifest = task_path / "task.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8") + "id: duplicate-id\n", encoding="utf-8"
    )
    with pytest.raises(TaskPackageError, match="duplicate key"):
        TaskPackage.load(task_path)


def test_package_rejects_symlinks_without_platform_dependency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_path = copy_task(PYTHON_TASK, tmp_path)
    target = task_path / "workspace" / "calculator.py"
    original = Path.is_symlink

    def reports_target_as_symlink(path: Path) -> bool:
        return path == target or original(path)

    monkeypatch.setattr(Path, "is_symlink", reports_target_as_symlink)
    with pytest.raises(TaskPackageError, match="symlinks are not allowed"):
        TaskPackage.load(task_path)


def test_digest_is_stable_and_content_sensitive(tmp_path: Path) -> None:
    task_path = copy_task(PYTHON_TASK, tmp_path)
    first = TaskPackage.load(task_path)
    second = TaskPackage.load(task_path)

    assert first.definition.content_digest == second.definition.content_digest
    assert first.definition.content_digest == digest_tree(task_path)

    source = task_path / "workspace" / "calculator.py"
    source.write_text(
        source.read_text(encoding="utf-8") + "\n# meaningful mutation\n", encoding="utf-8"
    )
    mutated = TaskPackage.load(task_path)

    assert mutated.definition.content_digest != first.definition.content_digest
    assert mutated.definition.workspace.digest != first.definition.workspace.digest


def test_fresh_materialization_isolated_and_hides_trusted_assets(tmp_path: Path) -> None:
    package = TaskPackage.load(TYPESCRIPT_TASK)
    first = package.materialize(tmp_path)
    second = package.materialize(tmp_path)
    try:
        assert first.root != second.root
        assert first.context is not None
        assert second.context is not None
        assert not (first.root / "verifier").exists()
        assert not (first.root / "oracle").exists()

        first_source = first.workspace / "range.ts"
        first_source.write_text("// subject mutation\n", encoding="utf-8")

        assert "subject mutation" not in (second.workspace / "range.ts").read_text(encoding="utf-8")
    finally:
        first.cleanup()
        second.cleanup()


def test_evidence_manifest_is_frozen_and_deterministic() -> None:
    validation = validate_task_package(PYTHON_TASK)
    evidence = validation.baseline

    assert evidence.canonical_json() == evidence.canonical_json()
    assert evidence.task_digest != evidence.workspace_digest
    assert len(evidence.verifier.digest) == 71
    with pytest.raises(ValidationError, match="frozen"):
        evidence.task_id = "changed"  # type: ignore[misc]
