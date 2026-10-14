"""One-command external SWE pilot only. Full stage requires a future confirmed invocation."""

from __future__ import annotations

import argparse
import asyncio
import shutil
from pathlib import Path

from scripts.coding_agent_eval import REPO, SPEC, load, save
from scripts.swe_external_acceptance import accept, prepare
from scripts.swe_external_pilot import agents
from scripts.swe_external_report import inventory, report
from scripts.swe_mixed_eval import bridge


async def pilot(args: argparse.Namespace) -> None:
    for path in (args.output, args.trusted):
        if path.exists() or path.resolve().is_relative_to(REPO):
            raise ValueError("use new separate external evidence roots")
    await prepare(args.root, args.trusted)
    await agents(args.root, args.output, args.codex_vendor, args.auth_file)
    await accept(args.root, args.trusted, args.output)
    for identity in load(args.output / "selection.json")["task_ids"]:
        case = args.output / identity
        logs = list((case / "acceptance-artifacts").rglob("stderr.txt"))
        if len(logs) != 1:
            raise ValueError("one saved acceptance log required")
        parsed = bridge(
            args.upstream_python,
            "parse",
            str(args.root / "hidden" / (identity + ".json")),
            str(logs[0]),
        )
        save(case / "upstream-parse.json", parsed)
    sources = args.output / "executed-protocol"
    for name in (
        "swe_external_campaign.py",
        "swe_external_pilot.py",
        "swe_external_delivery.py",
        "swe_external_acceptance.py",
        "swe_external_report.py",
        "coding_agent_eval.py",
        "swe_mixed_eval.py",
    ):
        target = sources / "scripts" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / "scripts" / name, target)
    for name in ("swe_bridge.py", "swe_payload_verifier.py", "mixed-config.json", "config.json"):
        target = sources / "evaluation/coding-agent" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SPEC / name, target)
    save(args.output / "pilot-summary.json", report(args.output, args.humaneval_summary))
    for path in (args.output, args.trusted):
        save(path / "inventory.json", inventory(path))
    print("Pilot complete. STOP: report the saved summary and await full-stage confirmation.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "root",
        "output",
        "trusted",
        "codex-vendor",
        "auth-file",
        "upstream-python",
        "humaneval-summary",
    ):
        parser.add_argument("--" + name, type=lambda s: Path(s).absolute(), required=True)
    asyncio.run(pilot(parser.parse_args()))
