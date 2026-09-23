"""Build a fail-closed D1 report from frozen controls and original trial bundles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from harnesslab.comparability.models import canonical_digest
from harnesslab.tasks.package import digest_tree, sha256_bytes

ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / "docs/evidence/d1-config-decision-20260923"
ARTIFACTS = Path("/home/dev/artifacts/samescale-d1-20260923")
RESULT = FREEZE / "result.json"


def read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    assert isinstance(value, dict)
    return value


def sealed(value: dict[str, Any]) -> None:
    assert value["identity"] == canonical_digest(
        {key: item for key, item in value.items() if key != "identity"}
    )


def verified_trial(
    index: int, cell: dict[str, Any], phase: dict[str, Any], task: dict[str, Any]
) -> dict[str, Any]:
    folder = ARTIFACTS / f"campaign-{index:02d}"
    receipt = read(folder / "receipt.json")
    sealed(receipt)
    assert receipt["index"] == index
    assert receipt["cell_identity"] == cell["identity"]
    assert receipt["execution_id"] == phase["cells"][index]["execution_id"]
    assert receipt["backend_dispatches"] == 1 and receipt["consumed"] is True
    inventory = read(folder / "sha256.json")
    for relative, digest in inventory.items():
        path = (folder / relative).resolve()
        assert path.is_relative_to(folder.resolve())
        assert sha256_bytes(path.read_bytes()) == digest
    bundle = Path(receipt["artifact_directory"]).resolve()
    assert bundle.is_relative_to(folder.resolve())
    assert digest_tree(bundle) == receipt["artifact_digest"]
    original = read(bundle / "manifest.json")
    assert original["outcome"] == receipt["outcome"]
    assert original["workspace_input_digest"] == task["task"]["workspace_digest"]
    assert original["normalized_trace_digest"] == sha256_bytes(
        (bundle / "trace/normalized.json").read_bytes()
    )
    return {
        "index": index,
        "task_id": cell["task_id"],
        "config": cell["config"],
        "trial": cell["trial"],
        "state": receipt["outcome"],
        "verified_success": receipt["task_success"],
        "subject_duration_ms": receipt["subject_duration_ms"],
        "verifier_checks": receipt["verifier_checks"],
        "verifier_passed_checks": receipt["verifier_passed_checks"],
        "usage": receipt["usage"],
        "cost_usd": "NOT_AVAILABLE",
        "continue_allowed": receipt["continue_allowed"],
        "stop_reasons": receipt["stop_reasons"],
        "receipt_sha256": sha256_bytes((folder / "receipt.json").read_bytes()),
        "bundle_digest": receipt["artifact_digest"],
    }


def build() -> dict[str, Any]:
    plan = read(FREEZE / "campaign.json")
    phase = read(FREEZE / "phase-authorization.json")
    sealed(plan)
    sealed(phase)
    assert phase["campaign_identity"] == plan["identity"]
    assert len(plan["cells"]) == len(phase["cells"]) == 20
    assert plan["trials_per_cell"] == 5 and len(plan["tasks"]) == 2
    tasks = {entry["task"]["task_id"]: entry for entry in plan["tasks"]}
    rows = []
    stopped = False
    for index, cell in enumerate(plan["cells"]):
        sealed(cell)
        folder = ARTIFACTS / f"campaign-{index:02d}"
        if folder.exists():
            assert not stopped, "Run created after frozen stop"
            row = verified_trial(index, cell, phase, tasks[cell["task_id"]])
            stopped = not row["continue_allowed"]
        else:
            assert stopped, "Missing run before frozen stop"
            row = {
                "index": index,
                "task_id": cell["task_id"],
                "config": cell["config"],
                "trial": cell["trial"],
                "state": "NOT_RUN",
                "verified_success": None,
                "cost_usd": "NOT_AVAILABLE",
            }
        rows.append(row)
    assert rows[0]["state"] == "verified_pass"
    assert rows[1]["state"] == "harness_error" and rows[1]["continue_allowed"] is False
    assert all(row["state"] == "NOT_RUN" for row in rows[2:])
    cleanup = read(ARTIFACTS / "post-stop-cleanup.json")
    assert cleanup["status"] == "PASS" and cleanup["files_deleted"] == 0
    for name, digest in cleanup["preserved_sha256"].items():
        assert sha256_bytes((ARTIFACTS / "campaign-01" / name).read_bytes()) == digest
    return {
        "schema_version": 1,
        "campaign_identity": plan["identity"],
        "phase_status": "BLOCKED_BEFORE_D1_ACCEPTANCE",
        "planned": 20,
        "attempted": 2,
        "verified_pass": 1,
        "verified_fail": 0,
        "not_verified": 1,
        "not_run": 18,
        "rows": rows,
        "metrics": {
            "verified_success": "1 VERIFIED_PASS / 20 planned; 1 NOT_VERIFIED; 18 NOT_RUN",
            "consistency": "NOT_VERIFIED",
            "median_latency": "NOT_VERIFIED; one completed verified trial observed at 224.417 s",
            "steps_per_verified_success": "NOT_VERIFIED; no frozen cross-Harness step unit",
            "observed_cost_per_verified_success": "NOT_AVAILABLE",
        },
        "failure_attribution": {
            "observed_boundary": "EVALUATION_CONTRACT: 600-second subject timeout",
            "root_cause": "UNKNOWN",
            "model_capability_failure": "NOT_ESTABLISHED",
            "harness_failure": "NOT_ESTABLISHED",
            "tool_failure": "NOT_ESTABLISHED",
            "workspace_contract_failure": "NOT_VERIFIED",
            "independent_verifier": "NOT_RUN",
            "original_cleanup": "FAIL: empty scratch directories remained",
            "post_stop_cleanup": (
                "PASS: empty scratch directories removed; original evidence unchanged"
            ),
        },
        "decision": "INSUFFICIENT EVIDENCE",
        "decision_scope": plan["claim_scope"],
        "d2_status": "NOT_STARTED_D1_BLOCKED",
        "post_stop_cleanup_sha256": sha256_bytes(
            (ARTIFACTS / "post-stop-cleanup.json").read_bytes()
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = build()
    rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.check:
        assert RESULT.read_text() == rendered
    else:
        with RESULT.open("x") as stream:
            stream.write(rendered)
    print("D1_REPORT_PASS", result["attempted"], result["not_run"], result["decision"])


if __name__ == "__main__":
    main()
