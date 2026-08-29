from __future__ import annotations

import json
import os
from pathlib import Path

from harnesslab.experiment.methodology import load_evaluation_methodology
from harnesslab.registry.model_chat import MODEL_CHAT_V2_PLAN_DIGEST, model_chat_v2_builder_request
from harnesslab.registry.models import PreflightStatus
from harnesslab.registry.seeds import build_registry_catalog
from harnesslab.registry.service import build_experiment_snapshot

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = Path.home() / ".local/state/harnesslab/portfolio-alibaba-model-chat-v2"
V1_PLAN = (
    Path.home()
    / ".local/state/harnesslab/portfolio-alibaba-breadth-v1"
    / "portfolio-alibaba-model-chat-v1-keyless-plan.json"
)
V1_CANONICAL_DIGEST = "sha256:a2cfdb6817cbbf9bc4f3fa9878c657e5e97a508a14288495ce6cf5f00c38dcc6"


def main() -> None:
    if not V1_PLAN.is_file():
        raise SystemExit("rejected v1 provenance artifact is missing")
    environment = dict(os.environ)
    catalog = build_registry_catalog(
        ROOT, environment, task_corpus_path=Path("release/core-corpus.json")
    )
    methodology = load_evaluation_methodology(ROOT / "release/evaluation-methodology-v2.json")
    request = model_chat_v2_builder_request(catalog, methodology)
    snapshot = build_experiment_snapshot(
        request,
        ROOT,
        environment,
        task_corpus_path=Path("release/core-corpus.json"),
    )
    if snapshot.plan.digest != MODEL_CHAT_V2_PLAN_DIGEST:
        raise SystemExit("frozen Model Chat v2 plan identity drifted")
    if snapshot.preflight.status is PreflightStatus.BLOCKED:
        reasons = ",".join(
            check.reason_code
            for check in snapshot.preflight.checks
            if check.status.value == "BLOCKED"
        )
        raise SystemExit(f"model-chat v2 preflight blocked: {reasons}")

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    plan_path = OUTPUT_ROOT / "portfolio-alibaba-model-chat-v2-keyless-plan.json"
    plan_path.write_text(
        json.dumps(snapshot.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    rejection = {
        "schema_version": 1,
        "plan_id": "portfolio-alibaba-model-chat-v1",
        "plan_digest": V1_CANONICAL_DIGEST,
        "status": "REJECTED_CONTROL_IDENTITY_MISMATCH",
        "real_calls": 0,
        "db_rows": 0,
        "reason_codes": [
            "NEVER_ENQUEUED",
            "FROZEN_PROVIDER_PROFILE_IDENTITY_MISMATCH",
            "FROZEN_HARNESS_CONFIG_IDENTITY_MISMATCH",
            "CURRENT_RUNTIME_RESOLUTION_REJECTED",
        ],
        "superseded_by": "portfolio-alibaba-model-chat-v2",
    }
    rejection_path = OUTPUT_ROOT / "model-chat-v1-rejection.json"
    rejection_path.write_text(
        json.dumps(rejection, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"MODEL_CHAT_V2_PLAN={plan_path}")
    print(f"MODEL_CHAT_V2_PLAN_DIGEST={snapshot.plan.digest}")
    print(f"MODEL_CHAT_V2_SLOTS={len(snapshot.plan.run_slots)}")
    print(f"MODEL_CHAT_V2_BLOCKS={len(snapshot.plan.schedule_blocks)}")
    print(f"MODEL_CHAT_V2_PREFLIGHT={snapshot.preflight.status.value}")
    print(f"MODEL_CHAT_V1_REJECTION={rejection_path}")
    print("REAL_PROVIDER_CALLS=0")
    print("DATABASE_ROWS_CREATED=0")


if __name__ == "__main__":
    main()
