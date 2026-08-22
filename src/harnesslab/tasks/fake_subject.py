from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

from harnesslab.tasks.models import validate_relative_path
from harnesslab.tasks.package import TaskPackageError, resolve_package_path


class FakeSubjectRunner:
    """Apply deterministic test-owned edits to subject-visible workspace files only."""

    def apply(
        self,
        workspace: Path,
        edits: Mapping[str, str],
        deletes: Iterable[str] = (),
    ) -> tuple[str, ...]:
        if not workspace.is_dir():
            raise TaskPackageError("subject workspace does not exist")
        changed: list[str] = []
        for relative in sorted(edits):
            safe = validate_relative_path(relative)
            target = resolve_package_path(workspace, safe)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(edits[relative], encoding="utf-8", newline="\n")
            changed.append(safe)
        for relative in sorted(deletes):
            safe = validate_relative_path(relative)
            target = resolve_package_path(workspace, safe)
            if target.is_dir():
                raise TaskPackageError("FakeSubjectRunner deletes files only")
            target.unlink(missing_ok=True)
            changed.append(safe)
        return tuple(changed)
