"""Reconcile already accepted release evidence without any external execution."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from harnesslab.release.reconciliation import build_candidate, verify_candidate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.check:
        verify_candidate(root)
    else:
        manifest, claims = build_candidate(root)
        for name, value in (
            ("release-evidence.json", manifest),
            ("resume-claim-evidence.json", claims),
        ):
            (root / "release" / name).write_text(
                json.dumps(value.model_dump(mode="json"), indent=2) + "\n"
            )
    print(
        "KC_STABLE_EVIDENCE=VERIFIED CORE_RELEASE_READY=FALSE "
        "TAG_CREATION_AUTHORIZED=FALSE REAL_CALLS=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
