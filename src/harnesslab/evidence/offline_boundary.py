"""Shared audit boundary for data-only evidence replay entrypoints."""

from __future__ import annotations

from typing import Any


class ReplayError(ValueError):
    """Missing, changed, unsupported or contradictory evidence: no result is released."""


def offline_guard(event: str, args: tuple[Any, ...]) -> None:
    if event.startswith(
        ("socket.", "subprocess.", "os.exec", "os.spawn", "os.posix_spawn")
    ) or event in {
        "os.system",
        "pty.spawn",
    }:
        raise ReplayError("offline boundary: network/process operation rejected")
