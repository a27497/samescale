"""Shard the unchanged core inventory by module; keep expensive shared fixtures together."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / ".github/ci-core-selectors.json"
DTO = (
    "tests/test_workbench_api.py::"
    "test_frontend_dtos_contain_no_absolute_path_credential_or_private_sentinel"
)


def full_groups() -> list[list[str]]:
    groups: list[list[str]] = json.loads((ROOT / ".github/ci-core-shards.json").read_text())
    inventory: list[str] = json.loads(CORE.read_text())
    flattened = [selector for group in groups for selector in group]
    if (
        len(groups) != 4
        or any(not group for group in groups)
        or (len(flattened) != len(set(flattened)) or set(flattened) != set(inventory))
    ):
        raise ValueError("Incomplete, overlapping or missing full-regression groups")
    return [*groups[:-1], [*groups[-1], "tests/test_ci_routing.py"]]


def owns(node: str, selector: str) -> bool:
    return node == selector or node.startswith((selector + "::", selector + "["))


def shard(nodes: list[str], index: int, count: int) -> list[str]:
    groups = full_groups()
    if count != len(groups) or not 0 <= index < count or not nodes or len(nodes) != len(set(nodes)):
        raise ValueError("Invalid/empty/duplicate collection or shard")
    owners = {}
    for node in nodes:
        matched = [i for i, group in enumerate(groups) if any(owns(node, s) for s in group)]
        if len(matched) != 1:
            raise ValueError("Unassigned or overlapping collected node")
        owners[node] = matched[0]
    return [node for node in nodes if owners[node] == index]


def collected(stdout: str) -> list[str]:
    nodes = [line for line in stdout.splitlines() if line.startswith("tests/") and "::" in line]
    summary = re.search(r"(\d+) tests? collected", stdout)
    if not nodes or len(nodes) != len(set(nodes)) or not summary or int(summary[1]) != len(nodes):
        raise ValueError("Missing, duplicate or incomplete pytest collection")
    return nodes


def verify_junit(path: Path, expected: int) -> None:
    cases = ET.parse(path).getroot().findall(".//testcase")
    if (
        expected < 1
        or len(cases) != expected
        or any(
            case.find(tag) is not None for case in cases for tag in ("skipped", "failure", "error")
        )
    ):
        raise ValueError("Zero, missing, skipped or nonpassing regression tests")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("full", "boundary"), required=True)
    parser.add_argument("--index", type=int, required=True)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--junit", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "full":
        selectors = [s for group in full_groups() for s in group]
    else:
        if (args.index, args.count) != (0, 1):
            raise ValueError("Boundary is exactly one job")
        selectors = [DTO]
    command = [sys.executable, "-m", "pytest"]
    observation = subprocess.run(
        [*command, "--collect-only", "-q", *selectors], cwd=ROOT, capture_output=True, text=True
    )
    if observation.returncode:
        print(observation.stdout + observation.stderr)
        return observation.returncode
    nodes = collected(observation.stdout)
    selected = shard(nodes, args.index, args.count) if args.mode == "full" else nodes
    if not selected:
        raise ValueError("Empty shard")
    print(
        "CI_COLLECTION_RECEIPT="
        + json.dumps(
            {
                "mode": args.mode,
                "index": args.index,
                "count": args.count,
                "collection_total": len(nodes),
                "collection_sha256": hashlib.sha256("\n".join(nodes).encode()).hexdigest(),
                "selected_count": len(selected),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    result = subprocess.run(
        [*command, "-q", *selected, "--durations=20", f"--junitxml={args.junit}"], cwd=ROOT
    )
    if result.returncode:
        return result.returncode
    verify_junit(args.junit, len(selected))
    print("CI_SHARD_PASS=" + json.dumps({"index": args.index, "tests": len(selected)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
