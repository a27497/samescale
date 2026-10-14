"""Offline mixed-campaign projection, with immutable predecessor and receipt checks."""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from harnesslab.external_evidence import service
from scripts.coding_agent_eval import digest, facts, load
from scripts.swe_external_report import inventory


def summary(root: Path, swe_pilot: Path, human_pilot: Path) -> dict[str, Any]:
    selection = load(root / "selection.json")
    expected = selection["tasks"]
    origins = (
        load(root / "origin-paths.json")
        if (root / "origin-paths.json").exists()
        else {
            "full": str(root.absolute()),
            "swe": str(swe_pilot.absolute()),
            "human": str(human_pilot.absolute()),
        }
    )
    values: dict[str, dict[str, Any]] = {}
    for pilot, group in ((swe_pilot, "SWE-bench"), (human_pilot, "HumanEval")):
        for original in load(pilot / "pilot-summary.json")["rows"]:
            identity = original["task_id"]
            case = (
                pilot / identity
                if group == "SWE-bench"
                else pilot / "cases" / identity.replace("/", "_")
            )
            values[identity] = {
                **original,
                "group": group,
                "retained": True,
                "environment": "PASS",
                "evidence_path": str(
                    Path(origins["swe"]) / identity
                    if group == "SWE-bench"
                    else Path(origins["human"]) / "cases" / identity.replace("/", "_")
                ),
            }
    for path in sorted((root / "results").glob("*.json")):
        value = load(path)
        identity = value["task_id"]
        if identity in values:
            raise ValueError("retained observation must not be replaced")
        successor = root / "results-successors" / path.name
        if successor.exists():
            replacement = load(successor)
            if (
                value["physical_agent_attempts"] != 0
                or value["api_equivalent_usd"] != 0
                or replacement["supersedes_projection_sha256"] != digest(path.read_bytes())
                or replacement["physical_agent_attempts"] != 1
            ):
                raise ValueError("invalid environment correction or repeated Agent")
            value = replacement
        values[identity] = value
    budget_stopped = (root / "STOP_BUDGET.json").exists()
    if budget_stopped:
        for identity in set(expected) - set(values):
            values[identity] = {
                "task_id": identity,
                "group": "HumanEval" if identity.startswith("HumanEval/") else "SWE-bench",
                "retained": False,
                "environment": "NOT_RUN",
                "self_report": "NOT_RUN",
                "verifier": "NOT_RUN",
                "failure_type": "UNKNOWN",
                "false_completion": False,
                "agent_seconds": None,
                "verifier_seconds": None,
                "api_equivalent_usd": 0,
                "physical_agent_attempts": 0,
                "evidence_path": str(root / "STOP_BUDGET.json"),
                "not_run_reason": "OBSERVED_BUDGET_STOP",
            }
    if len(expected) != 30 or set(values) != set(expected):
        raise ValueError("all fixed thirty observations required; no replacement or exclusion")
    rows = []
    for identity in expected:
        value = dict(values[identity])
        case = Path(value["evidence_path"])
        for key, actual_root in (("full", root), ("swe", swe_pilot), ("human", human_pilot)):
            if case.is_relative_to(Path(origins[key])):
                case = actual_root / case.relative_to(Path(origins[key]))
                break
        if value.get("agent_seconds") is not None:
            events = [json.loads(s) for s in (case / "agent.stdout").read_text().splitlines()]
            messages = [
                e["item"].get("text", "")
                for e in events
                if e.get("type") == "item.completed"
                and e.get("item", {}).get("type") == "agent_message"
            ]
            claims = re.findall(
                r"^SAMESCALE_SELF_REPORT=(PASS|FAIL|UNKNOWN)$",
                messages[-1] if messages else "",
                re.M,
            )
            claim = claims[0] if len(claims) == 1 else "UNKNOWN"
            if value["self_report"] != claim:
                raise ValueError("raw final self-report disagreement")
        if value["retained"] and value["group"] == "HumanEval":
            raw = facts(case, load(human_pilot / "config.json"))
            if any(value[key] != observed for key, observed in raw.items()):
                raise ValueError("retained HumanEval raw evidence differs")
        if value.get("setup_seconds", 0) is not None and value.get("setup_seconds", 0) < 0:
            value["setup_seconds"] = None
            value["setup_measurement_note"] = "invalid resume-derived timing; original retained"
        if (case / "acceptance.json").exists():
            receipt = load(case / "acceptance.json")
            verdict = {
                "VERIFIED_PASS": "PASS",
                "VERIFIED_FAIL": "FAIL",
                "NOT_VERIFIED": "NOT_VERIFIED",
            }[receipt["acceptance"]]
            if verdict != value["verifier"]:
                raise ValueError("receipt/row disagreement")
            if (value["checks"], value["passed_checks"]) != (
                receipt["checks"],
                receipt["passed_checks"],
            ):
                raise ValueError("receipt check-count disagreement")
            packet = (case / "export.json").read_bytes()
            if service.replay_export(packet, "sha256:" + digest(packet)) != load(
                case / "export-replay.json"
            ):
                raise ValueError("export replay disagreement")
            value["receipt_digest"] = receipt["receipt_digest"]
        if not value["retained"] and value.get("physical_agent_attempts") == 1:
            meter = load(case / "meter/receipt.json")
            if abs(meter["api_equivalent_usd"] - value["api_equivalent_usd"]) > 1e-8:
                raise ValueError("meter/row fee disagreement")
        rows.append(value)
    groups = {}
    for group in ("All", "SWE-bench", "HumanEval"):
        subset = rows if group == "All" else [r for r in rows if r["group"] == group]
        n = len(subset)
        self_pass = sum(r["self_report"] == "PASS" for r in subset)
        independent = sum(r["verifier"] == "PASS" for r in subset)
        executed = sum(r.get("agent_seconds") is not None for r in subset)
        groups[group] = {
            "selected": n,
            "self_report_passes": self_pass,
            "independent_passes": independent,
            "agent_attempts": executed,
            "executed_independent_pass_rate": independent / executed if executed else None,
            "self_report_pass_rate": self_pass / n,
            "independent_pass_rate": independent / n,
            "gap_percentage_points": (self_pass - independent) * 100 / n,
            "environment_failures": sum(r["environment"] == "FAIL" for r in subset),
            "self_report_distribution": dict(Counter(r["self_report"] for r in subset)),
            "independent_distribution": dict(Counter(r["verifier"] for r in subset)),
            "failure_distribution": dict(Counter(r["failure_type"] for r in subset)),
            "false_completions": sum(r["false_completion"] for r in subset),
            "api_equivalent_usd": round(sum(r["api_equivalent_usd"] for r in subset), 8),
            "agent_seconds": round(sum(r.get("agent_seconds") or 0 for r in subset), 3),
            "verifier_seconds": round(sum(r.get("verifier_seconds") or 0 for r in subset), 3),
            "usage": {
                key: sum((r.get("usage") or {}).get(key, 0) for r in subset)
                for key in (
                    "input_tokens",
                    "cached_input_tokens",
                    "cache_write_input_tokens",
                    "output_tokens",
                )
            },
        }
    return {
        "schema_version": 1,
        "status": "PARTIAL_BUDGET_STOP" if budget_stopped else "COMPLETE_FIXED_30",
        "product_REAL_CODEX": "UNCHANGED_CLOSED",
        "budget_limit_usd": 20,
        "budget_stopped": budget_stopped,
        "actual_billed_usd": None,
        "retained_summary_sha256": {
            "SWE-bench": digest((swe_pilot / "pilot-summary.json").read_bytes()),
            "HumanEval": digest((human_pilot / "pilot-summary.json").read_bytes()),
        },
        "groups": groups,
        "rows": rows,
    }


def csv_bytes(value: dict[str, Any]) -> bytes:
    fields = [
        "task_id",
        "group",
        "retained",
        "environment",
        "self_report",
        "verifier",
        "failure_type",
        "false_completion",
        "agent_seconds",
        "verifier_seconds",
        "setup_seconds",
        "api_equivalent_usd",
        "evidence_path",
        "receipt_digest",
    ]
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fields, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(value["rows"])
    return stream.getvalue().encode()


def publish(root: Path, observed: dict[str, Any]) -> None:
    encoded = (json.dumps(observed, indent=2, sort_keys=True) + "\n").encode()
    for name, data in (("full-summary.json", encoded), ("results.csv", csv_bytes(observed))):
        path = root / name
        if path.exists() and path.read_bytes() != data:
            raise ValueError("never overwrite a different published report")
        path.write_bytes(data)
    path = root / "inventory.json"
    path.write_text(json.dumps(inventory(root), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("report", "replay"))
    for name in ("root", "swe-pilot", "human-pilot"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    origin_file = args.root / "origin-paths.json"
    if args.command == "report" and not origin_file.exists():
        origin_file.write_text(
            json.dumps(
                {
                    "full": str(args.root.absolute()),
                    "swe": str(args.swe_pilot.absolute()),
                    "human": str(args.human_pilot.absolute()),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
    observed = summary(args.root, args.swe_pilot, args.human_pilot)
    encoded = (json.dumps(observed, indent=2, sort_keys=True) + "\n").encode()
    if args.command == "report":
        publish(args.root, observed)
    else:
        if (
            encoded != (args.root / "full-summary.json").read_bytes()
            or csv_bytes(observed) != (args.root / "results.csv").read_bytes()
        ):
            raise ValueError("report drift")
        if inventory(args.root) != load(args.root / "inventory.json"):
            raise ValueError("file/mode/symlink drift")
    print(json.dumps(observed["groups"], indent=2))
