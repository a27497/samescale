"""One-use D1 freeze generator. Run from the historical qualified S1 checkout."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from uuid import uuid4

from scripts.s1_mini_benchmark import ROOT, check_seal, seal, write

from harnesslab.tasks.package import TaskPackage, sha256_bytes
from harnesslab.tasks.quality import TaskIdentity

HERE = Path(__file__).resolve().parent
PARENT = ROOT / "docs/evidence/s1-completion-freeze-20260921/campaign.json"
TASK_IDS = [
    "lecturelens-analysis-progress-stream-reconnect",
    "lecturelens-embedded-subtitle-language-metadata",
]
EXTRA_RUNTIME = (
    "scripts/s1_claude_controls.py",
    "scripts/s1_credentials.py",
    "scripts/s1_official_codex.py",
    "scripts/s1_official_custom_tools.py",
    "scripts/s1_protocol_repair.py",
    "docs/evidence/s1-completion-final-20260921/execute_campaign.py",
    "docs/evidence/s1-official-custom-tools-20260921/readback.py",
)


def main() -> None:
    parent = json.loads(PARENT.read_text())
    check_seal(parent)
    tasks = [t for t in parent["tasks"] if t["task"]["task_id"] in TASK_IDS]
    assert len(tasks) == 2
    for task in tasks:
        package = TaskPackage.load(Path(task["package_path"]))
        assert TaskIdentity.from_package(package).model_dump(mode="json") == task["task"]
        assert package.oracle_digest == task["oracle_digest"]
        assert task["qualification"]["qualification"] == "DETERMINISTIC_QUALIFIED"
    originals = {
        (c["task_id"], c["config"]): c
        for c in parent["cells"]
        if c["task_id"] in TASK_IDS
    }
    assert len(originals) == 4
    cells = []
    for trial in range(1, 6):
        for task_index, task_id in enumerate(TASK_IDS):
            order = ("codex", "claude") if (trial + task_index) % 2 else ("claude", "codex")
            for side in order:
                original = originals[task_id, side]
                cells.append(
                    seal(
                        {
                            **{
                                k: copy.deepcopy(v)
                                for k, v in original.items()
                                if k != "identity"
                            },
                            "trial": trial,
                            "d1_namespace": "d1-config-decision-20260923",
                            "parent_cell_identity": original["identity"],
                        }
                    )
                )
    implementation_files = dict(parent["implementation_files"])
    for rel in EXTRA_RUNTIME:
        implementation_files[rel] = sha256_bytes((ROOT / rel).read_bytes())
    for rel, digest in implementation_files.items():
        assert sha256_bytes((ROOT / rel).read_bytes()) == digest
    plan = seal(
        dict(
            kind="D1_CONFIGURATION_DECISION_20_RUNS",
            schema_version=1,
            comparison_type="AI_CODING_CONFIGURATION_COMPARISON",
            execution_authorized=False,
            task_ids=TASK_IDS,
            tasks=tasks,
            configs=parent["configs"],
            cells=cells,
            trials_per_cell=5,
            operator_retries=0,
            resume=False,
            fallback=False,
            judge=False,
            skill="none",
            context="none",
            concurrency=1,
            subject_timeout_seconds=600,
            verifier_timeout_seconds=300,
            declared_output_tokens_per_run=6000,
            session_output_token_hard_cap_enforced=False,
            aggregate_declared_output_tokens=120000,
            maximum_subject_seconds=12000,
            maximum_verifier_seconds=6000,
            cost_hard_cap="NOT_AVAILABLE",
            stop_policy="continue_verified_failure;stop_infra_protocol_auth_control_evidence_or_cleanup_failure",
            failure_taxonomy=[
                "MODEL", "HARNESS", "TOOL", "ENVIRONMENT",
                "WORKSPACE_CONTRACT", "EVALUATION_CONTRACT", "UNKNOWN",
            ],
            success_criteria="independent_frozen_verifier_verified_pass_only",
            metrics=[
                "verified_success", "consistency", "median_latency",
                "steps_per_verified_success", "observed_cost_per_verified_success",
                "failure_attribution",
            ],
            decision_values=[
                "KEEP CURRENT", "SWITCH SUPPORTED BY CURRENT EVIDENCE",
                "INSUFFICIENT EVIDENCE", "INVALID COMPARISON",
            ],
            claim_scope="these_two_tasks_environment_versions_budgets_and_configs_only",
            parent_campaign_identity=parent["identity"],
            parent_campaign_sha256=sha256_bytes(PARENT.read_bytes()),
            implementation_files=implementation_files,
            operator_sha256=sha256_bytes((HERE / "operator.py").read_bytes()),
        )
    )
    assert len(plan["cells"]) == 20
    phase = seal(
        dict(
            kind="D1_PHASE_AUTHORIZATION",
            campaign_identity=plan["identity"],
            source=(
                "User request: D1 2 configs x 2 real tasks x 5 trials; subsequent explicit "
                "selection of historical S1 Official Codex and Claude Code on LectureLens B and A"
            ),
            execution_authorized=True,
            subject_sessions=20,
            attempt_each=1,
            operator_retry=0,
            resume=False,
            fallback=False,
            judge=False,
            unknown_cost_and_session_token_hard_caps_acknowledged=True,
            cells=[
                dict(
                    cell_identity=c["identity"],
                    execution_id=uuid4().hex,
                    authorization_id=uuid4().hex,
                )
                for c in cells
            ],
        )
    )
    write(HERE / "campaign.json", plan)
    write(HERE / "phase-authorization.json", phase)
    print(json.dumps({"status": "FROZEN", "campaign": plan["identity"], "cells": 20}))


if __name__ == "__main__":
    main()
