from __future__ import annotations

import shutil
import tarfile
from pathlib import Path

from scripts.swe_external_delivery import delivery


def test_saved_delivery_preserves_executable_and_symlink_without_following(tmp_path: Path) -> None:
    case = tmp_path / "case"
    workspace = case / "workspace"
    workspace.mkdir(parents=True)
    executable = workspace / "tool.sh"
    executable.write_text("#!/bin/sh\nexit 0\n")
    executable.chmod(0o755)
    (workspace / "alias").symlink_to("tool.sh")
    (workspace / "code.py").write_text("value = 0\n")
    with tarfile.open(case / "base.tar", "w") as archive:
        for path in workspace.iterdir():
            archive.add(path, arcname=path.name)
    (workspace / "code.py").write_text("value = 1\n")
    delivery(case)
    patch = (case / "delivery-v2/solution.patch").read_text()
    assert "+value = 1" in patch and "-value = 0" in patch
    assert "alias" not in patch and "tool.sh" not in patch
    saved = case / "delivery-v2-final"
    assert (saved / "tool.sh").stat().st_mode & 0o777 == 0o755
    assert (saved / "alias").is_symlink() and (saved / "alias").readlink() == Path("tool.sh")
    # A reviewed final snapshot never reads an arbitrary symlink's referenced content.
    external = tmp_path / "private"
    external.write_text("outside content")
    (workspace / "external-link").symlink_to(external)
    delivery(case, label="delivery-next")
    assert "outside content" not in (case / "delivery-next/solution.patch").read_text()
    shutil.rmtree(case)
