"""Conservative excerpt helper, followed by explicit operator review; never loads hidden assets."""

from __future__ import annotations

import re


def public_failure_lines(output: str) -> str:
    # Whitelist rendered observations. Drop stack frames and ALL source/context/assertion lines.
    # A test name is an identifier, not its implementation. Unknown formats provide no excerpt.
    lines = []
    for line in output.splitlines():
        stripped = line.strip()
        if (
            re.fullmatch(r"FAILED [A-Za-z0-9_./:\[\]-]+(?: - AssertionError)?", stripped)
            or re.fullmatch(
                r"(?:E\s+)?(?:AssertionError|TimeoutError|ImportError|ModuleNotFoundError)",
                stripped,
            )
            or re.fullmatch(r"E\s+At index \d+ diff: .{1,2000}", stripped)
        ):
            lines.append(stripped)
    return "\n".join(dict.fromkeys(lines))
