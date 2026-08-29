from __future__ import annotations

import json
from pathlib import Path

from harnesslab.release.contracts import build_corpus_manifest

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "release/tier-a-verifier-robustness-v2.json"


def main() -> int:
    corpus = build_corpus_manifest(ROOT, task_version="1.0.2")
    payload = corpus.model_dump(mode="json")
    payload["corpus_id"] = "harnesslab-tier-a-verifier-robustness-v2"
    payload["qualification"] = "TIER_A_VERIFIER_ROBUSTNESS_V2"
    DESTINATION.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"TIER_A_ROBUSTNESS_V2_CORPUS={DESTINATION}")
    print(f"TIER_A_ROBUSTNESS_V2_TASKS={len(corpus.tasks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
