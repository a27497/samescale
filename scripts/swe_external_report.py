"""Deterministic real-pilot metrics and offline replay; never edits observed verdicts."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from harnesslab.external_evidence import service
from scripts.coding_agent_eval import digest, load, save


def row(case: Path, rates: dict[str, Any]) -> dict[str, Any]:
    events = [json.loads(line) for line in (case / "agent.stdout").read_text().splitlines()]
    completed = [e for e in events if e.get("type") == "turn.completed"]
    usage = None
    if completed and all("usage" in e for e in completed):
        usage = {
            key: sum(e["usage"][key] for e in completed)
            for key in ("input_tokens", "cached_input_tokens", "output_tokens")
        }
    finals = [
        e["item"].get("text", "")
        for e in events
        if e.get("type") == "item.completed" and e.get("item", {}).get("type") == "agent_message"
    ]
    claims = re.findall(
        r"^SAMESCALE_SELF_REPORT=(PASS|FAIL|UNKNOWN)$", finals[-1] if finals else "", re.M
    )
    self_report = claims[0] if len(claims) == 1 else "UNKNOWN"
    receipt = load(case / "acceptance.json")
    process = load(case / "agent-process.json")
    acceptance = receipt["acceptance"]
    verdict = {"VERIFIED_PASS": "PASS", "VERIFIED_FAIL": "FAIL", "NOT_VERIFIED": "NOT_VERIFIED"}[
        acceptance
    ]
    failure = (
        "TIMEOUT"
        if process["timed_out"]
        else "ENVIRONMENT_FAILURE"
        if verdict == "NOT_VERIFIED"
        else "HIDDEN_TEST_FAILURE"
        if verdict == "FAIL"
        else "NONE"
        if verdict == "PASS"
        else "UNKNOWN"
    )
    cost = None
    if usage is not None:
        cost = (
            (usage["input_tokens"] - usage["cached_input_tokens"]) * rates["input_usd_per_million"]
            + usage["cached_input_tokens"] * rates["cached_input_usd_per_million"]
            + usage["output_tokens"] * rates["output_usd_per_million"]
        ) / 1e6
    manifests = list((case / "acceptance-artifacts").rglob("manifest.json"))
    if len(manifests) != 1:
        raise ValueError("one independent physical acceptance attempt required")
    manifest = load(manifests[0])
    upstream = load(case / "upstream-parse.json")
    statuses = upstream["required_statuses"]
    if upstream["missing_required_tests"] or len(statuses) != receipt["checks"]:
        raise ValueError("official upstream parser missing/count mismatch")
    if sum(v == "PASSED" for v in statuses.values()) != receipt["passed_checks"]:
        raise ValueError("official upstream parser verdict mismatch")
    packet = (case / "export.json").read_bytes()
    if service.replay_export(packet, "sha256:" + digest(packet)) != load(
        case / "export-replay.json"
    ):
        raise ValueError("existing export replay differs")
    return {
        "task_id": case.name,
        "self_report": self_report,
        "verifier": verdict,
        "failure_type": failure,
        "false_completion": self_report == "PASS" and verdict == "FAIL",
        "checks": receipt["checks"],
        "passed_checks": receipt["passed_checks"],
        "agent_seconds": process["duration_seconds"],
        "verifier_seconds": manifest["duration_ms"] / 1000,
        "usage": usage,
        "api_equivalent_usd": round(cost, 8) if cost is not None else None,
        "actual_billed_usd": None,
        "record_identity": receipt["record_identity"],
        "receipt_digest": receipt["receipt_digest"],
        "physical_agent_attempts": 1,
        "physical_verifier_attempts": receipt["physical_attempts"],
    }


def report(output: Path, humaneval: Path) -> dict[str, Any]:
    rates = load(output / "runtime-config.json")["pricing"]
    rows = [
        row(output / identity, rates) for identity in load(output / "selection.json")["task_ids"]
    ]
    he = load(humaneval)
    costs = sum(r["api_equivalent_usd"] for r in rows)
    seconds = sum(r["agent_seconds"] for r in rows)
    input_keys = ("input_tokens", "cached_input_tokens", "output_tokens")
    usage = {key: sum(r["usage"][key] for r in rows) for key in input_keys}
    projected_usage = {key: usage[key] * 25 / 3 + he["usage"][key] * 5 / 3 for key in input_keys}
    projected_cost = costs * 25 / 3 + he["api_equivalent_usd"] * 5 / 3
    projected_seconds = seconds * 25 / 3 + sum(r["agent_seconds"] for r in he["rows"]) * 5 / 3
    self_pass = sum(r["self_report"] == "PASS" for r in rows)
    accepted = sum(r["verifier"] == "PASS" for r in rows)
    return {
        "schema_version": 1,
        "route": "EXTERNAL_CODEX_CLI_THEN_EXISTING_INTAKE_VERIFIER",
        "product_REAL_CODEX": "UNCHANGED_CLOSED",
        "swe_attempts": 3,
        "self_report_passes": self_pass,
        "verified_passes": accepted,
        "self_report_pass_rate": self_pass / 3,
        "verified_pass_rate": accepted / 3,
        "gap_percentage_points": (self_pass - accepted) * 100 / 3,
        "false_completions": sum(r["false_completion"] for r in rows),
        "failure_distribution": dict(Counter(r["failure_type"] for r in rows)),
        "usage": usage,
        "api_equivalent_usd": round(costs, 8),
        "actual_billed_usd": None,
        "agent_seconds": seconds,
        "rows": rows,
        "forecast_30": {
            "method": "25*SWE mean + 5*retained HumanEval mean; sequential one attempt",
            "usage": projected_usage,
            "agent_seconds": projected_seconds,
            "api_equivalent_usd": projected_cost,
            "uncached_api_equivalent_usd": (
                projected_usage["input_tokens"] * rates["input_usd_per_million"]
                + projected_usage["output_tokens"] * rates["output_usd_per_million"]
            )
            / 1e6,
            "remaining_tasks": 24,
            "remaining_agent_seconds": projected_seconds
            - seconds
            - sum(r["agent_seconds"] for r in he["rows"]),
            "remaining_api_equivalent_usd": projected_cost - costs - he["api_equivalent_usd"],
            "steady_state_wall_hours_range": [1.5, 2.5],
            "wall_range_excludes": [
                "uncached image downloads",
                "new environment failures",
                "engineering corrections",
            ],
            "planning_allowance_usd": 25,
            "hard_cost_cap": False,
            "actual_billing_unknown": True,
        },
        "environment": {
            "fixed_pilot_count": 3,
            "original_preflight_failed": 3,
            "original_preflight_failure_rate": 1,
            "latest_upstream_preflight_failed": 0,
            "latest_adapter_admission_failed": 0,
            "latest_failure_rate": 0,
            "nonpilot_swe_locally_admitted": 0,
            "nonpilot_swe_count": 22,
        },
        "full_stage": "NOT_RUN_AWAITING_USER_CONFIRMATION",
        "retained_humaneval_summary_sha256": digest(humaneval.read_bytes()),
    }


def inventory(root: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if ".git" in relative.parts or relative.as_posix() == "inventory.json":
            continue
        if path.is_symlink():
            import os

            result[str(relative)] = {"symlink_text": os.readlink(path)}
        elif path.is_file():
            result[str(relative)] = {
                "sha256": digest(path.read_bytes()),
                "mode": path.stat().st_mode & 0o777,
            }
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("report", "replay"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--humaneval-summary", type=Path, required=True)
    parser.add_argument("--trusted", type=Path, required=True)
    args = parser.parse_args()
    value = report(args.output, args.humaneval_summary)
    if args.command == "report":
        save(args.output / "pilot-summary.json", value)
        for root in (args.output, args.trusted):
            save(root / "inventory.json", inventory(root))
    else:
        for root in (args.output, args.trusted):
            if inventory(root) != load(root / "inventory.json"):
                raise ValueError("artifact inventory/mode/link drift")
        if value != load(args.output / "pilot-summary.json"):
            raise ValueError("saved summary differs from raw observations")
    print(json.dumps(value, indent=2))
