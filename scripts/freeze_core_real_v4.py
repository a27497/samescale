from __future__ import annotations

import json
from pathlib import Path

from harnesslab.release.models import CoreCorpusManifest, RealEvidencePlan, RealSmokePlan

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "release"


def _load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected an object in {path}")
    return value


def _write(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=False, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    robustness = _load(RELEASE / "tier-a-verifier-robustness-v2.json")
    corpus = CoreCorpusManifest.model_validate(
        {
            "schema_version": 1,
            "corpus_id": "harnesslab-core-18-v1",
            "tasks": robustness["tasks"],
        }
    )
    corpus_path = RELEASE / "core-corpus-v4.json"
    _write(corpus_path, corpus.model_dump(mode="json"))

    source_plan = _load(RELEASE / "core-real-evidence-plan-v3.json")
    source_plan.update(
        {
            "plan_id": "core-real-evidence-v4",
            "supersedes_plan_id": "core-real-evidence-v3",
            "experiment_id": "core-real-matrix-v4",
            "corpus_reference": "release/core-corpus-v4.json",
            "corpus_digest": corpus.digest,
            "unresolved_authorization_items": [
                "CANARY_PREFLIGHT must pass before the bounded 7-subject plus 1-Judge canary.",
                (
                    "FULL_MATRIX_PREFLIGHT requires immutable pricing and separate "
                    "630-subject plus 63-Judge budget authorization."
                ),
                "No full Matrix execution is authorized by this frozen plan.",
            ],
        }
    )
    plan = RealEvidencePlan.model_validate(source_plan)
    plan_path = RELEASE / "core-real-evidence-plan-v4.json"
    _write(plan_path, plan.model_dump(mode="json"))

    source_smoke = _load(RELEASE / "core-real-smoke-plan-v3.json")
    source_smoke.update(
        {
            "schema_version": 4,
            "plan_id": "core-real-smoke-v4",
            "release_plan_reference": "release/core-real-evidence-plan-v4.json",
            "release_plan_digest": plan.digest,
        }
    )
    task = next(item for item in corpus.tasks if item.task_id == "core-python-deduplicate")
    calls = source_smoke.get("calls")
    if not isinstance(calls, list):
        raise ValueError("v3 smoke calls are unavailable")
    for call in calls:
        if not isinstance(call, dict):
            raise ValueError("v3 smoke call is invalid")
        if call.get("lane") in {"M", "H"}:
            call["task_digest"] = task.task_digest
    smoke = RealSmokePlan.model_validate(source_smoke)
    _write(RELEASE / "core-real-smoke-plan-v4.json", smoke.model_dump(mode="json"))

    print(f"SUCCESSOR_EXPERIMENT_ID={plan.experiment_id}")
    print(f"SUCCESSOR_PLAN_DIGEST={plan.digest}")
    print(f"CANARY_PLAN_DIGEST={smoke.digest}")
    print(f"TASK_VERSION={task.version}")


if __name__ == "__main__":
    main()
