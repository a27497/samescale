"""Hash inventories and Python audit protection for frozen evidence."""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path
from typing import Any


class FrozenEvidenceError(RuntimeError):
    pass


def snapshot_tree(root: Path) -> dict[str, dict[str, Any]]:
    """Record bytes and relative identities; reject links rather than follow substitutes."""
    if not root.is_dir():
        raise FrozenEvidenceError("protected evidence directory is missing")
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise FrozenEvidenceError("protected evidence contains a symlink")
        if path.is_file():
            data = path.read_bytes()
            result[path.relative_to(root).as_posix()] = {
                "size": len(data),
                "sha256": "sha256:" + hashlib.sha256(data).hexdigest(),
            }
    return result


class FrozenEvidenceGuard:
    """Fail Python writes/deletes immediately; suite snapshots also cover subprocesses."""

    def __init__(self, roots: tuple[Path, ...]) -> None:
        self.roots = tuple(root.resolve() for root in roots)
        self.active = True

    def _protected(self, raw: object) -> bool:
        if not isinstance(raw, (str, bytes, os.PathLike)):
            return False
        path = Path(os.fsdecode(raw)).absolute()
        resolved = path.resolve()
        return any(
            path == r or r in path.parents or resolved == r or r in resolved.parents
            for r in self.roots
        )

    def audit(self, event: str, args: tuple[Any, ...]) -> None:
        if not self.active:
            return
        paths: tuple[object, ...] = ()
        if event == "open":
            mode, flags = args[1:3]
            write = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                isinstance(flags, int)
                and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            )
            if write:
                paths = (args[0],)
        elif event in {
            "os.remove",
            "os.rmdir",
            "os.mkdir",
            "os.chmod",
            "os.truncate",
            "shutil.rmtree",
        }:
            paths = (args[0],)
        elif event in {"os.rename", "os.link"}:
            paths = args[:2]
        elif event == "os.symlink":
            paths = (args[1],)
        if any(self._protected(p) for p in paths):
            raise FrozenEvidenceError("test attempted to mutate frozen/public-demo evidence")

    def install(self) -> None:
        sys.addaudithook(self.audit)
