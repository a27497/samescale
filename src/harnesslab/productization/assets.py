"""Trusted source/build resources, shared by the launcher and wheel build hook."""

from __future__ import annotations

from pathlib import Path


def distribution_root() -> Path:
    source = Path(__file__).resolve().parents[3]
    if (source / "src/harnesslab/__init__.py").is_file():
        return source
    return Path(__file__).resolve().parent / "distribution"
