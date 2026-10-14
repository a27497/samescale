"""Complete intake/verification of an already finished HumanEval CLI; never rerun Agent."""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

from harnesslab.external_evidence import service
from harnesslab.external_evidence.models import EvidencePolicy
from harnesslab.external_evidence.verification import verify_workspace
from harnesslab.tasks.package import digest_tree
from scripts.coding_agent_eval import digest, load, save


async def finish(case: Path, identity: str) -> dict[str, Any]:
    final = case / "final-reviewed"
    shutil.copytree(
        case / "final",
        final,
        symlinks=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    old = EvidencePolicy.model_validate_json((case / "evidence-policy.json").read_bytes())
    source = old.sources[0].model_copy(
        update={"workspace": final, "workspace_digest": digest_tree(final)}
    )
    policy = old.model_copy(update={"sources": (source,)})
    save(case / "evidence-reviewed-policy.json", policy.model_dump(mode="json"))
    (case / "evidence-reviewed-policy.json").chmod(0o600)
    os.environ["HARNESSLAB_EXTERNAL_EVIDENCE_POLICY"] = str(case / "evidence-reviewed-policy.json")
    os.environ["HARNESSLAB_LOCAL_TASK_POLICY"] = str(case / "trusted/task-policy.json")
    policy = service.load_policy()
    item = service.ingest(policy, source.source_id)
    save(case / "intake.json", item)
    receipt = await verify_workspace(policy, item["identity"])
    save(case / "acceptance.json", receipt)
    packet = service.export_record(policy, item["identity"])
    (case / "export.json").write_bytes(packet)
    save(case / "export-replay.json", service.replay_export(packet, "sha256:" + digest(packet)))
    save(
        case / "snapshot-review.json",
        {
            "raw_final_preserved": True,
            "excluded_generated_cache_extensions": [".pyc", ".pyo"],
            "excluded_cache_directory": "__pycache__",
            "solution_sha256": digest((final / "solution.py").read_bytes()),
            "agent_reexecuted": False,
        },
    )
    events = [json.loads(s) for s in (case / "agent.stdout").read_text().splitlines()]
    msgs = [
        e["item"].get("text", "")
        for e in events
        if e.get("type") == "item.completed" and e.get("item", {}).get("type") == "agent_message"
    ]
    claims = re.findall(
        r"^SAMESCALE_SELF_REPORT=(PASS|FAIL|UNKNOWN)$", msgs[-1] if msgs else "", re.M
    )
    claim = claims[0] if len(claims) == 1 else "UNKNOWN"
    manifest_path = next((case / "acceptance-artifacts").rglob("manifest.json"))
    manifest = load(manifest_path)
    verdict = {"VERIFIED_PASS": "PASS", "VERIFIED_FAIL": "FAIL", "NOT_VERIFIED": "NOT_VERIFIED"}[
        receipt["acceptance"]
    ]
    failure = (
        load(manifest_path.parent / "stdout.txt")["checks"][0]["detail"]
        if verdict != "NOT_VERIFIED"
        else "ENVIRONMENT_FAILURE"
    )
    meter = load(case / "meter/receipt.json")
    process = load(case / "agent-process.json")
    return {
        "task_id": identity,
        "group": "HumanEval",
        "retained": False,
        "environment": "PASS",
        "self_report": claim,
        "verifier": verdict,
        "failure_type": failure,
        "false_completion": claim == "PASS" and verdict == "FAIL",
        "checks": receipt["checks"],
        "passed_checks": receipt["passed_checks"],
        "agent_seconds": process["duration_seconds"],
        "verifier_seconds": manifest["duration_ms"] / 1000,
        "usage": meter["usage"],
        "api_equivalent_usd": round(meter["api_equivalent_usd"], 8),
        "actual_billed_usd": None,
        "record_identity": receipt["record_identity"],
        "receipt_digest": receipt["receipt_digest"],
        "physical_agent_attempts": 1,
        "physical_verifier_attempts": receipt["physical_attempts"],
        "evidence_path": str(case),
    }
