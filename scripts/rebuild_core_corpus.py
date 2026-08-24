from __future__ import annotations

import json
from pathlib import Path

from harnesslab.release.contracts import build_corpus_manifest

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    manifest = build_corpus_manifest(ROOT)
    destination = ROOT / "release/core-corpus.json"
    destination.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"CORE_CORPUS_REBUILT={manifest.digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
