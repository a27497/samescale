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
    with pytest.raises(TaskPackageError, match="links and junctions are not allowed"):
        TaskPackage.load(task_path)


def test_package_rejects_junctions_without_platform_dependency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_path = copy_task(PYTHON_TASK, tmp_path)
    target = task_path / "workspace"
    original = Path.is_junction

    def reports_target_as_junction(path: Path) -> bool:
        return path == target or original(path)

    monkeypatch.setattr(Path, "is_junction", reports_target_as_junction)
    with pytest.raises(TaskPackageError, match="links and junctions are not allowed"):
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


def test_complete_verifier_tree_defines_verifier_identity(tmp_path: Path) -> None:
    task_path = copy_task(PYTHON_TASK, tmp_path)
    verifier_root = task_path / "verifier"
    entrypoint_directory = verifier_root / "entrypoints"
    entrypoint_directory.mkdir()
    (verifier_root / "verify.py").replace(entrypoint_directory / "verify.py")
    supporting_asset = verifier_root / "support" / "cases.json"
    supporting_asset.parent.mkdir()
    supporting_asset.write_text('{"revision":1}\n', encoding="utf-8")
    manifest = task_path / "task.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "entrypoint: verifier/verify.py",
            "entrypoint: verifier/entrypoints/verify.py",
        ),
        encoding="utf-8",
    )

    first = TaskPackage.load(task_path)
    supporting_asset.write_text('{"revision":2}\n', encoding="utf-8")
    second = TaskPackage.load(task_path)

    assert second.verifier_digest != first.verifier_digest
    assert second.definition.content_digest != first.definition.content_digest


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


def test_evidence_workspace_digest_precedes_verifier_side_effects(tmp_path: Path) -> None:
    task_path = copy_task(PYTHON_TASK, tmp_path)
    verifier = task_path / "verifier" / "verify.py"
    verifier.write_text(
        verifier.read_text(encoding="utf-8").replace(
            "    workspace = Path(sys.argv[1])\n",
            "    workspace = Path(sys.argv[1])\n"
            '    (workspace / ".verifier-cache").write_text("generated", encoding="utf-8")\n',
        ),
        encoding="utf-8",
    )
    package = TaskPackage.load(task_path)
    baseline_workspace = package.materialize()
    oracle_workspace = package.materialize()
    try:
        expected_baseline_digest = package.workspace_digest(baseline_workspace)
        package.apply_oracle(oracle_workspace)
        expected_oracle_digest = package.workspace_digest(oracle_workspace)
    finally:
        baseline_workspace.cleanup()
        oracle_workspace.cleanup()

    first = validate_task_package(task_path)
    second = validate_task_package(task_path)

    assert first.baseline.workspace_digest == expected_baseline_digest
    assert first.oracle.workspace_digest == expected_oracle_digest
    assert second.baseline.workspace_digest == expected_baseline_digest
    assert second.oracle.workspace_digest == expected_oracle_digest
