"""Authorized fixed full campaign, with append-only per-task results and live $20 stop."""

from __future__ import annotations

import argparse
import asyncio
import base64
import gzip
import json
import time
import traceback
from pathlib import Path
from typing import Any

from scripts.coding_agent_eval import digest, load, save
from scripts.swe_external_acceptance import accept, prepare
from scripts.swe_external_pilot import agents
from scripts.swe_external_report import row
from scripts.swe_mixed_eval import bridge, check_inputs

INPUT = Path("/home/dev/.local/state/samescale-eval/swe-mixed-20261014")
ROOT = Path("/home/dev/.local/state/samescale-eval/swe-full-20261014")
PILOT = Path("/home/dev/.local/state/samescale-eval/swe-external-pilot-20261014")
HUMANEVAL = Path("/home/dev/.local/state/samescale-eval/pilot-20261014-v3")
VENDOR = Path(
    "/home/dev/.local/lib/node_modules/@openai/codex/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl"
)
AUTH = Path("/home/dev/.codex/auth.json")
LIMIT = 20.0


def retained() -> list[dict[str, Any]]:
    hashes = (
        (PILOT, "9b46f2e9b738440ab9a80b4833934e8041dc1f104bddb011194bbc467319d6d2"),
        (HUMANEVAL, "fe14209cb3760190da9119d2b9a66a27f0fe0a3ab3d2f97002e2be6183a992ee"),
    )
    for path, expected in hashes:
        if digest((path / "pilot-summary.json").read_bytes()) != expected:
            raise ValueError("immutable retained-six observation drift")
    swe = load(PILOT / "pilot-summary.json")["rows"]
    he = load(HUMANEVAL / "pilot-summary.json")["rows"]
    return [
        {
            **r,
            "group": "SWE-bench",
            "retained": True,
            "environment": "PASS",
            "evidence_path": str(PILOT / r["task_id"]),
        }
        for r in swe
    ] + [
        {
            **r,
            "group": "HumanEval",
            "retained": True,
            "environment": "PASS",
            "evidence_path": str(HUMANEVAL / "cases" / r["task_id"].replace("/", "_")),
        }
        for r in he
    ]


def consumed() -> float:
    values = retained() + [
        load(p)
        for directory in ("results", "results-successors")
        for p in (ROOT / directory).glob("*.json")
    ]
    if any(v["api_equivalent_usd"] is None for v in values):
        raise RuntimeError("unknown API usage: no further paid dispatch")
    return float(sum(v["api_equivalent_usd"] for v in values))


def save_result(value: dict[str, Any]) -> None:
    save(ROOT / "results" / (value["task_id"].replace("/", "_") + ".json"), value)
    print(json.dumps(value), flush=True)


def environment_failure(identity: str, trusted: Path, elapsed: float, exc: Exception) -> None:
    save(
        trusted / "environment-error.json",
        {
            "exception": type(exc).__name__,
            "message": str(exc)[:4000],
            "traceback": traceback.format_exc(),
            "stage": "PRE_AGENT_ADMISSION",
            "agent_started": False,
        },
    )
    save_result(
        {
            "task_id": identity,
            "group": "SWE-bench",
            "retained": False,
            "environment": "FAIL",
            "self_report": "NOT_RUN",
            "verifier": "NOT_RUN",
            "failure_type": "ENVIRONMENT_FAILURE",
            "false_completion": False,
            "agent_seconds": None,
            "verifier_seconds": None,
            "setup_seconds": elapsed,
            "api_equivalent_usd": 0,
            "usage": None,
            "actual_billed_usd": None,
            "evidence_path": str(trusted),
            "physical_agent_attempts": 0,
            "checks": 0,
            "passed_checks": 0,
        }
    )


async def swe(
    identity: str,
    *,
    reuse_prepared: bool = False,
    resume_saved: bool = False,
    trusted_override: Path | None = None,
    result_directory: Path | None = None,
) -> None:
    trusted = trusted_override or ROOT / "environments" / identity
    started = time.monotonic()
    if not reuse_prepared:
        try:
            await prepare(
                INPUT, trusted, task_ids=[identity], full_adapter=True, no_build_isolation=True
            )
        except Exception as exc:
            if not trusted.exists():
                trusted.mkdir(parents=True)
            environment_failure(identity, trusted, time.monotonic() - started, exc)
            return
    setup_seconds = None if (reuse_prepared or resume_saved) else time.monotonic() - started
    output = ROOT / "agents" / identity
    output.parent.mkdir(exist_ok=True)
    case = output / identity
    if not resume_saved:
        await agents(INPUT, output, VENDOR, AUTH, task_ids=[identity], budget=(consumed(), LIMIT))
    else:
        process = load(case / "agent-process.json")
        if process["exit_code"] != 0 or process["timed_out"]:
            raise ValueError("saved attempt not complete")
        events = [json.loads(s) for s in (case / "agent.stdout").read_text().splitlines()]
        turn = [e["usage"] for e in events if e.get("type") == "turn.completed"][-1]
        meter = load(case / "meter/receipt.json")
        if any(
            turn[k] > meter["usage"][k]
            for k in ("input_tokens", "cached_input_tokens", "output_tokens")
        ):
            raise ValueError("saved meter undercoverage")
        save(
            case / "meter-reconciliation-v2.json",
            {
                "turn_usage": turn,
                "response_usage": meter["usage"],
                "budget_counts_all_reported_responses": True,
                "agent_reexecuted": False,
                "prior_error_retained": True,
            },
        )
    if not (case / "acceptance.json").exists():
        await accept(INPUT, trusted, output, task_ids=[identity])
    receipt = load(case / "acceptance.json")
    logs = list((case / "acceptance-artifacts").rglob("stderr.txt"))
    if len(logs) != 1:
        raise ValueError("one acceptance physical attempt required")
    encoded = logs[0].read_text()
    prefix = "SAMESCALE_RAW_LOG_GZIP_BASE64="
    lines = [s for s in encoded.splitlines() if s.startswith(prefix)]
    if len(lines) == 1:
        actual = gzip.decompress(base64.b64decode(lines[0][len(prefix) :]))
        (case / "actual-test-output.txt").write_bytes(actual)
    if receipt["acceptance"] == "NOT_VERIFIED":
        process = load(case / "agent-process.json")
        meter = load(case / "meter/receipt.json")
        events = [json.loads(s) for s in (case / "agent.stdout").read_text().splitlines()]
        messages = [
            e["item"].get("text", "")
            for e in events
            if e.get("type") == "item.completed"
            and e.get("item", {}).get("type") == "agent_message"
        ]
        import re

        claims = re.findall(
            r"^SAMESCALE_SELF_REPORT=(PASS|FAIL|UNKNOWN)$", messages[-1] if messages else "", re.M
        )
        result = {
            "task_id": identity,
            "self_report": claims[0] if len(claims) == 1 else "UNKNOWN",
            "verifier": "NOT_VERIFIED",
            "failure_type": "TIMEOUT" if process["timed_out"] else "ENVIRONMENT_FAILURE",
            "false_completion": False,
            "checks": 0,
            "passed_checks": 0,
            "agent_seconds": process["duration_seconds"],
            "verifier_seconds": None,
            "usage": meter["usage"],
            "api_equivalent_usd": meter["api_equivalent_usd"],
            "actual_billed_usd": None,
            "physical_agent_attempts": 1,
            "record_identity": receipt["record_identity"],
        }
    else:
        parsed = bridge(
            INPUT / "tooling/venv/bin/python",
            "parse",
            str(INPUT / "hidden" / (identity + ".json")),
            str(case / "actual-test-output.txt"),
        )
        save(case / "upstream-parse.json", parsed)
        result = row(case, load(output / "runtime-config.json")["pricing"])
        meter = load(case / "meter/receipt.json")
        result["api_equivalent_usd"] = round(meter["api_equivalent_usd"], 8)
        result["usage"] = meter["usage"]
    value = {
        **result,
        "group": "SWE-bench",
        "retained": False,
        "environment": "PASS",
        "setup_seconds": setup_seconds,
        "evidence_path": str(case),
    }
    if result_directory:
        previous = ROOT / "results" / (identity + ".json")
        original = load(previous)
        if original["physical_agent_attempts"] != 0:
            raise ValueError("never rerun an executed Agent")
        value["supersedes_projection_sha256"] = (
            __import__("hashlib").sha256(previous.read_bytes()).hexdigest()
        )
        value["environment_correction_evidence"] = str(trusted)
        result_directory.mkdir(exist_ok=True)
        save(result_directory / (identity + ".json"), value)
        print(json.dumps(value), flush=True)
    else:
        save_result(value)
    if meter["stopped_budget"] or meter["stopped_meter_error"]:
        save(
            ROOT / ("STOP_BUDGET.json" if meter["stopped_budget"] else "STOP_METER_ERROR.json"),
            {"observed_api_equivalent_usd": consumed(), "limit_usd": LIMIT},
        )
        raise RuntimeError("budget/meter stop: no subsequent Agent dispatch")


async def main(
    ids: list[str], reuse_prepared: bool, resume_saved: bool, human_controls: bool = False
) -> None:
    check_inputs(INPUT)
    (ROOT / "results").mkdir(exist_ok=True)
    for identity in ids:
        if (ROOT / "results" / (identity + ".json")).exists():
            continue
        if consumed() >= LIMIT:
            save(
                ROOT / "STOP_BUDGET.json",
                {"observed_api_equivalent_usd": consumed(), "limit_usd": LIMIT},
            )
            return
        await swe(identity, reuse_prepared=reuse_prepared, resume_saved=resume_saved)
    if human_controls:
        from scripts.humaneval_full import human

        for identity in load(INPUT / "config.json")["humaneval_task_ids"][3:]:
            if (ROOT / "results" / (identity.replace("/", "_") + ".json")).exists():
                continue
            if consumed() >= LIMIT:
                save(
                    ROOT / "STOP_BUDGET.json",
                    {"observed_api_equivalent_usd": consumed(), "limit_usd": LIMIT},
                )
                return
            value = await human(
                ROOT, HUMANEVAL, identity, VENDOR, AUTH, initial=consumed(), limit=LIMIT
            )
            save_result(value)
    print("Requested fixed batch finished; selected membership unchanged.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids", nargs="+")
    parser.add_argument("--all", action="store_true")
    for name, default in (
        ("input-root", INPUT),
        ("output", ROOT),
        ("swe-pilot", PILOT),
        ("human-pilot", HUMANEVAL),
        ("codex-vendor", VENDOR),
        ("auth-file", AUTH),
    ):
        parser.add_argument("--" + name, type=lambda s: Path(s).absolute(), default=default)
    parser.add_argument("--limit-usd", type=float, default=20)
    parser.add_argument("--reuse-prepared", action="store_true")
    parser.add_argument("--resume-saved-agent", action="store_true")
    parser.add_argument("--human-controls", action="store_true")
    args = parser.parse_args()
    INPUT, ROOT, PILOT, HUMANEVAL = args.input_root, args.output, args.swe_pilot, args.human_pilot
    VENDOR, AUTH, LIMIT = args.codex_vendor, args.auth_file, args.limit_usd
    from scripts.coding_agent_eval import REPO

    if ROOT.resolve().is_relative_to(REPO) or not 0 < LIMIT <= 20:
        raise ValueError("external evidence root and positive limit <= $20 required")
    if args.all:
        config = load(INPUT / "config.json")
        identities = [r["instance_id"] for r in config["tasks"]]
        frozen = {
            "tasks": identities + config["humaneval_task_ids"],
            "retained_swe": config["pilot_task_ids"],
            "retained_humaneval": config["humaneval_task_ids"][:3],
            "api_equivalent_limit_usd": LIMIT,
            "budget_includes_retained_results": True,
            "execution_route": "EXTERNAL_CODEX_CLI",
            "REAL_CODEX": "UNCHANGED_CLOSED",
        }
        ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
        if (ROOT / "selection.json").exists():
            if load(ROOT / "selection.json") != frozen:
                raise ValueError("fixed selection/configuration drift")
        else:
            save(ROOT / "selection.json", frozen)
        origins = {"full": str(ROOT), "swe": str(PILOT), "human": str(HUMANEVAL)}
        if (ROOT / "origin-paths.json").exists():
            if load(ROOT / "origin-paths.json") != origins:
                raise ValueError("execution roots differ from frozen originals")
        else:
            save(ROOT / "origin-paths.json", origins)
        args.ids = [s for s in identities if s not in config["pilot_task_ids"]]
        args.human_controls = True
    if not args.ids:
        parser.error("use --all or --ids")
    asyncio.run(main(args.ids, args.reuse_prepared, args.resume_saved_agent, args.human_controls))
    if args.all:
        from scripts.swe_full_report import publish, summary

        publish(ROOT, summary(ROOT, PILOT, HUMANEVAL))
