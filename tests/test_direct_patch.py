from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from harnesslab.model_lane import patch as patch_contract
from harnesslab.model_lane.patch import (
    MAX_FILE_CONTENT_BYTES,
    MAX_PATCH_OPERATIONS,
    MAX_TOTAL_CONTENT_BYTES,
    DirectPatchError,
    DirectPatchInfrastructureError,
    apply_direct_patch,
    parse_direct_patch,
)
from harnesslab.model_lane.prompt import PromptContractError, render_direct_prompt
from harnesslab.tasks.package import TaskPackage, digest_tree

TASK_ROOT = Path(__file__).resolve().parents[1] / "tasks" / "micro-python-clamp" / "1.0.0"


def test_direct_prompt_is_deterministic_and_excludes_hidden_assets(tmp_path: Path) -> None:
    copied = tmp_path / "micro-python-clamp" / "1.0.0"
    shutil.copytree(TASK_ROOT, copied)
    (copied / "verifier" / "hidden.txt").write_text("HIDDEN_VERIFIER_SENTINEL", encoding="utf-8")
    (copied / "oracle" / "hidden.txt").write_text("HIDDEN_ORACLE_SENTINEL", encoding="utf-8")
    package = TaskPackage.load(copied)
    materialized = package.materialize(tmp_path / "materialized")
    context = tmp_path / "context"
    context.mkdir()
    (context / "requirements.txt").write_text("visible-context\n", encoding="utf-8")
    try:
        first = render_direct_prompt(
            task_instruction=package.definition.instruction,
            workspace=materialized.workspace,
            context=context,
        )
        second = render_direct_prompt(
            task_instruction=package.definition.instruction,
            workspace=materialized.workspace,
            context=context,
        )
        assert first == second
        assert first.template_version == "direct-patch-v1"
        canonical = json.dumps(
            {
                "template_version": first.template_version,
                "instructions": first.instructions,
                "input": first.input,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        assert first.prompt_hash == f"sha256:{hashlib.sha256(canonical).hexdigest()}"
        assert first.context_digest == digest_tree(context)
        assert "<<<FILE requirements.txt>>>\nvisible-context" in first.input
        assert "HIDDEN_VERIFIER_SENTINEL" not in first.input
        assert "HIDDEN_ORACLE_SENTINEL" not in first.input
        assert first.input.index("<<<FILE calculator.py>>>") < first.input.index(
            "<<<FILE public_check.py>>>"
        )
        (context / "requirements.txt").write_text("changed-context\n", encoding="utf-8")
        context_changed = render_direct_prompt(
            task_instruction=package.definition.instruction,
            workspace=materialized.workspace,
            context=context,
        )
        assert context_changed.context_digest != first.context_digest
        assert context_changed.prompt_hash != first.prompt_hash

        (materialized.workspace / "calculator.py").write_text("changed\n", encoding="utf-8")
        workspace_changed = render_direct_prompt(
            task_instruction=package.definition.instruction,
            workspace=materialized.workspace,
            context=context,
        )
        assert workspace_changed.workspace_digest != first.workspace_digest
        assert workspace_changed.prompt_hash != context_changed.prompt_hash
    finally:
        materialized.cleanup()


@pytest.mark.parametrize(
    "public_output",
    [
        pytest.param('```json\n{"schema_version":1,"operations":[]}\n```', id="wrapping"),
        pytest.param(
            '{"schema_version":1,"operations":[{"op":"write","path":"../escape","content":"x"}]}',
            id="traversal",
        ),
        pytest.param(
            '{"schema_version":1,"operations":[{"op":"write","path":"/absolute","content":"x"}]}',
            id="absolute",
        ),
        pytest.param(
            '{"schema_version":1,"operations":[{"op":"delete","path":"missing.txt"}]}',
            id="invalid-delete",
        ),
    ],
)
def test_direct_patch_rejects_wrapping_traversal_absolute_and_invalid_delete(
    public_output: str, tmp_path: Path
) -> None:
    if "missing.txt" not in public_output:
        with pytest.raises(DirectPatchError):
            parse_direct_patch(public_output)
        return
    patch = parse_direct_patch(public_output)
    (tmp_path / "workspace").mkdir()
    with pytest.raises(DirectPatchError):
        apply_direct_patch(tmp_path / "workspace", patch, protected_digests=())


def test_direct_patch_rejects_protected_file_and_symlink_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = TaskPackage.load(TASK_ROOT)
    materialized = package.materialize(tmp_path / "materialized")
    try:
        protected_patch = parse_direct_patch(
            json.dumps(
                {
                    "schema_version": 1,
                    "operations": [
                        {"op": "write", "path": "public_check.py", "content": "tampered"}
                    ],
                },
                separators=(",", ":"),
            )
        )
        with pytest.raises(DirectPatchError, match="protected"):
            apply_direct_patch(
                materialized.workspace,
                protected_patch,
                protected_digests=materialized.protected_digests,
            )

        link = materialized.workspace / "link"
        link.mkdir()
        original_is_symlink = Path.is_symlink
        monkeypatch.setattr(
            Path,
            "is_symlink",
            lambda path: path == link or original_is_symlink(path),
        )
        with pytest.raises(DirectPatchError, match="link or junction"):
            patch_contract._assert_no_symlink_path(
                materialized.workspace,
                link / "escape.txt",
            )
        assert not (link / "escape.txt").exists()
    finally:
        materialized.cleanup()


def test_direct_patch_applies_complete_write_and_changes_workspace_identity(
    tmp_path: Path,
) -> None:
    package = TaskPackage.load(TASK_ROOT)
    materialized = package.materialize(tmp_path / "materialized")
    before = digest_tree(materialized.workspace)
    patch = parse_direct_patch(
        json.dumps(
            {
                "schema_version": 1,
                "operations": [
                    {
                        "op": "write",
                        "path": "calculator.py",
                        "content": (
                            "def clamp(value: int, lower: int, upper: int) -> int:\n"
                            "    return max(lower, min(value, upper))\n"
                        ),
                    }
                ],
            },
            separators=(",", ":"),
        )
    )
    try:
        after = apply_direct_patch(
            materialized.workspace,
            patch,
            protected_digests=materialized.protected_digests,
        )
        assert after != before
        assert after == digest_tree(materialized.workspace)
    finally:
        materialized.cleanup()


def test_direct_patch_applies_delete_and_updates_workspace_identity(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    deleted = workspace / "delete-me.txt"
    deleted.write_text("remove me", encoding="utf-8")
    before = digest_tree(workspace)
    patch = parse_direct_patch(
        '{"schema_version":1,"operations":[{"op":"delete","path":"delete-me.txt"}]}'
    )

    after = apply_direct_patch(workspace, patch, protected_digests=())

    assert not deleted.exists()
    assert after == digest_tree(workspace)
    assert after != before


def test_direct_patch_failure_is_atomic_when_protected_identity_is_stale(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    protected = workspace / "protected.txt"
    protected.write_text("original", encoding="utf-8")
    before = digest_tree(workspace)
    patch = parse_direct_patch(
        '{"schema_version":1,"operations":['
        '{"op":"write","path":"new.txt","content":"would be partial"}]}'
    )

    with pytest.raises(DirectPatchError, match="protected task file identity changed"):
        apply_direct_patch(
            workspace,
            patch,
            protected_digests=(("protected.txt", "sha256:" + "0" * 64),),
        )

    assert digest_tree(workspace) == before
    assert protected.read_text(encoding="utf-8") == "original"
    assert not (workspace / "new.txt").exists()


def test_direct_patch_rejects_workspace_changed_since_prompt_without_mutation(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "original.txt").write_text("original", encoding="utf-8")
    before = digest_tree(workspace)
    patch = parse_direct_patch(
        '{"schema_version":1,"operations":[{"op":"write","path":"new.txt","content":"new"}]}'
    )

    with pytest.raises(DirectPatchInfrastructureError, match="rendered prompt"):
        apply_direct_patch(
            workspace,
            patch,
            protected_digests=(),
            expected_input_digest="sha256:" + "0" * 64,
        )

    assert digest_tree(workspace) == before
    assert not (workspace / "new.txt").exists()


def test_direct_patch_staging_creation_failure_is_infrastructure_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    patch = parse_direct_patch(
        '{"schema_version":1,"operations":[{"op":"write","path":"new.txt","content":"new"}]}'
    )

    def fail_mkdtemp(*args: object, **kwargs: object) -> str:
        raise OSError("synthetic staging failure")

    monkeypatch.setattr("harnesslab.model_lane.patch.tempfile.mkdtemp", fail_mkdtemp)
    with pytest.raises(DirectPatchInfrastructureError, match="staging directory"):
        apply_direct_patch(workspace, patch, protected_digests=())


def test_direct_patch_preserves_original_when_commit_and_rollback_both_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "original.txt").write_text("irreplaceable", encoding="utf-8")
    patch = parse_direct_patch(
        '{"schema_version":1,"operations":[{"op":"write","path":"new.txt","content":"new"}]}'
    )
    real_replace = Path.replace

    def fail_commit_and_rollback(source: Path, target: Path) -> Path:
        if source.name in {"candidate", "original"}:
            raise OSError("synthetic rename failure")
        return real_replace(source, target)

    monkeypatch.setattr(Path, "replace", fail_commit_and_rollback)
    with pytest.raises(DirectPatchError, match="original preserved"):
        apply_direct_patch(workspace, patch, protected_digests=())

    preserved = list(tmp_path.glob(".workspace-direct-patch-*/original"))
    assert len(preserved) == 1
    assert (preserved[0] / "original.txt").read_text(encoding="utf-8") == "irreplaceable"
    monkeypatch.undo()
    real_replace(preserved[0], workspace)
    shutil.rmtree(preserved[0].parent)


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(
            {
                "schema_version": 1,
                "operations": [
                    {"op": "write", "path": f"file-{index}.txt", "content": "x"}
                    for index in range(MAX_PATCH_OPERATIONS + 1)
                ],
            },
            id="operation-count",
        ),
        pytest.param(
            {
                "schema_version": 1,
                "operations": [
                    {
                        "op": "write",
                        "path": "large.txt",
                        "content": "x" * (MAX_FILE_CONTENT_BYTES + 1),
                    }
                ],
            },
            id="per-file-content",
        ),
        pytest.param(
            {
                "schema_version": 1,
                "operations": [
                    {
                        "op": "write",
                        "path": f"large-{index}.txt",
                        "content": "x" * (MAX_TOTAL_CONTENT_BYTES // 4 + 1),
                    }
                    for index in range(4)
                ],
            },
            id="total-content",
        ),
    ],
)
def test_direct_patch_rejects_contract_bounds(payload: dict[str, object]) -> None:
    with pytest.raises(DirectPatchError):
        parse_direct_patch(json.dumps(payload, separators=(",", ":")))


@pytest.mark.parametrize(
    "path",
    [
        pytest.param("x" * 256, id="oversized-component"),
        pytest.param("ambiguous.txt.", id="trailing-dot"),
        pytest.param("ambiguous.txt ", id="trailing-space"),
    ],
)
def test_direct_patch_rejects_nonportable_path_aliases(path: str) -> None:
    with pytest.raises(DirectPatchError):
        parse_direct_patch(
            json.dumps(
                {
                    "schema_version": 1,
                    "operations": [{"op": "write", "path": path, "content": "x"}],
                },
                separators=(",", ":"),
            )
        )


def test_direct_prompt_rejects_oversized_total(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with pytest.raises(PromptContractError, match="total size"):
        render_direct_prompt(
            task_instruction="x" * 1_000_001,
            workspace=workspace,
            context=None,
        )


@pytest.mark.parametrize("path", ["PUBLIC_CHECK.py", "public_check.py/child"])
def test_direct_patch_rejects_casefolded_protected_and_non_directory_parent(
    tmp_path: Path, path: str
) -> None:
    package = TaskPackage.load(TASK_ROOT)
    materialized = package.materialize(tmp_path / "materialized")
    patch = parse_direct_patch(
        json.dumps(
            {
                "schema_version": 1,
                "operations": [{"op": "write", "path": path, "content": "x"}],
            },
            separators=(",", ":"),
        )
    )
    try:
        with pytest.raises(DirectPatchError):
            apply_direct_patch(
                materialized.workspace,
                patch,
                protected_digests=materialized.protected_digests,
            )
    finally:
        materialized.cleanup()


def test_direct_patch_rejects_overlapping_operation_paths() -> None:
    with pytest.raises(DirectPatchError):
        parse_direct_patch(
            '{"schema_version":1,"operations":['
            '{"op":"write","path":"a","content":"x"},'
            '{"op":"write","path":"a/b","content":"y"}]}'
        )


def test_direct_patch_rejects_duplicate_json_keys() -> None:
    with pytest.raises(DirectPatchError, match="duplicate object key"):
        parse_direct_patch(
            '{"schema_version":1,'
            '"operations":[{"op":"write","path":"first.txt","content":"x"}],'
            '"operations":[{"op":"write","path":"second.txt","content":"y"}]}'
        )


def test_direct_prompt_rejects_junction_like_subject_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    junction = workspace / "external"
    junction.mkdir()
    (junction / "secret.txt").write_text("must not serialize", encoding="utf-8")
    original = Path.is_junction
    monkeypatch.setattr(
        Path,
        "is_junction",
        lambda path: path == junction or original(path),
    )

    with pytest.raises(PromptContractError, match="unsafe"):
        render_direct_prompt(task_instruction="safe task", workspace=workspace, context=None)
