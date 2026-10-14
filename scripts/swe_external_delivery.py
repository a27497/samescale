"""Derive a campaign patch from the saved tree, preserving source modes and symlink text."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

from scripts.coding_agent_eval import load, save


def delivery(case: Path, label: str = "delivery-v2") -> None:
    destination = case / label
    destination.mkdir()
    final = case / (label + "-final")
    final.mkdir()
    links = []
    for current, dirs, names in os.walk(case / "workspace", followlinks=False):
        relative = Path(current).relative_to(case / "workspace")
        dirs[:] = [name for name in dirs if name != ".git"]
        (final / relative).mkdir(parents=True, exist_ok=True)
        for name in [*dirs, *names]:
            source = Path(current) / name
            target = final / relative / name
            if source.is_symlink():
                text = os.readlink(source)
                target.symlink_to(text)
                links.append({"path": str(relative / name), "target": text})
            elif source.is_file():
                shutil.copy2(source, target)
    scratch = case / (label + "-scratch")
    scratch.mkdir()
    try:
        with tarfile.open(case / "base.tar") as archive:
            archive.extractall(scratch, filter="data")
        subprocess.run(["git", "init", "-q", str(scratch)], check=True)
        for args in (
            ["add", "-A"],
            [
                "-c",
                "user.name=SameScale baseline",
                "-c",
                "user.email=baseline@localhost",
                "commit",
                "-q",
                "-m",
                "fixed baseline",
            ],
        ):
            subprocess.run(["git", "-C", str(scratch), *args], check=True)
        for path in scratch.iterdir():
            if path.name != ".git":
                if path.is_dir() and not path.is_symlink():
                    shutil.rmtree(path)
                else:
                    path.unlink()
        shutil.copytree(
            final, scratch, symlinks=True, copy_function=shutil.copy2, dirs_exist_ok=True
        )
        subprocess.run(["git", "-C", str(scratch), "add", "-A"], check=True)
        patch = subprocess.run(
            ["git", "-C", str(scratch), "diff", "--cached", "--binary", "--no-ext-diff"],
            capture_output=True,
            check=True,
        ).stdout
        (destination / "solution.patch").write_bytes(patch)
    finally:
        shutil.rmtree(scratch)
    save(
        case / (label + "-snapshot.json"),
        {
            "symlink_text_not_followed": links,
            "modes_preserved": True,
            "source": "saved original post-Agent workspace",
            "initial_projection_retained": "delivery/solution.patch",
            "agent_reexecuted": False,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    for identity in load(args.output / "selection.json")["task_ids"]:
        delivery(args.output / identity)
