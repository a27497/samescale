"""Derive trusted test commands from pinned upstream TestSpec; membership stays fixed."""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any

from scripts.swe_mixed_eval import bridge


def test_command_for(root: Path, row: dict[str, Any]) -> list[str]:
    if row["repo"] == "astropy/astropy":
        reporting = [] if row["version"] in {"1.3", "2.0", "3.0"} else ["--show-capture=no"]
        required: list[str] = json.loads(row["FAIL_TO_PASS"]) + json.loads(row["PASS_TO_PASS"])
        return [
            "python",
            "-m",
            "pytest",
            "-v",
            "-o",
            "console_output_style=classic",
            "-rA",
            "--color=no",
            "--tb=short",
            *reporting,
            *required,
        ]
    spec = bridge(
        root / "tooling/venv/bin/python",
        "spec",
        str(root / "hidden" / (row["instance_id"] + ".json")),
    )
    command = (
        spec["eval_script"]
        .split(": '>>>>> Start Test Output'", 1)[1]
        .split(": '>>>>> End Test Output'", 1)[0]
        .strip()
    )
    if row["repo"] == "sphinx-doc/sphinx":
        args = shlex.split(command)
        return [
            "python",
            "-m",
            "pytest",
            "-rA",
            "--color=no",
            "--tb=short",
            "--show-capture=no",
            *args[args.index("--") + 1 :],
        ]
    if row["repo"] == "sympy/sympy":
        command = command.replace("bin/test ", "python bin/test ", 1)
        return ["bash", "-c", command]
    if row["repo"] in {"psf/requests", "pytest-dev/pytest"}:
        args = shlex.split(command)
        if args[0] != "pytest":
            raise ValueError("unexpected trusted pytest command")
        return [
            "python",
            "-m",
            "pytest",
            "--color=no",
            "--tb=short",
            "--show-capture=no",
            *args[1:],
        ]
    raise ValueError("unselected repository")
