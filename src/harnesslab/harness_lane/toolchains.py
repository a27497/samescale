from __future__ import annotations

import re

from harnesslab.contracts.task import ExpectedToolContract

_VERSION_PATTERNS = {
    "python": re.compile(r"\bPython\s+(\d+(?:\.\d+)+)\b"),
    "java": re.compile(r'\bversion\s+"(\d+(?:\.\d+)*)'),
    "javac": re.compile(r"\bjavac\s+(\d+(?:\.\d+)*)\b"),
    "node": re.compile(r"\bv(\d+(?:\.\d+)+)\b"),
    "sqlite": re.compile(r"\b(\d+(?:\.\d+)+)\b"),
}


def extract_tool_version(tool: str, output: str) -> str:
    """Extract the numeric runtime/compiler version from canonical version output."""

    pattern = _VERSION_PATTERNS.get(tool)
    if pattern is None:
        raise ValueError(f"unsupported H-Lane expected tool: {tool}")
    match = pattern.search(output)
    if match is None:
        raise ValueError(f"unable to parse {tool} version output")
    return match.group(1)


def version_satisfies(declared: str, actual: str) -> bool:
    """Match the complete declared numeric prefix (major or major/minor today)."""

    try:
        expected_parts = tuple(int(part) for part in declared.split("."))
        actual_parts = tuple(int(part) for part in actual.split("."))
    except ValueError:
        return False
    return bool(expected_parts) and actual_parts[: len(expected_parts)] == expected_parts


def unsatisfied_tools(
    requirements: tuple[ExpectedToolContract, ...], actual_versions: dict[str, str]
) -> tuple[str, ...]:
    return tuple(
        f"{requirement.name} expected {requirement.version}, found "
        f"{actual_versions.get(requirement.name, 'missing')}"
        for requirement in requirements
        if not version_satisfies(requirement.version, actual_versions.get(requirement.name, ""))
    )
