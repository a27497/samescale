from __future__ import annotations

from pathlib import Path

from harnesslab.evaluation_suites import build_m8a_preregistration_bundle

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "evaluation_suites/m8a/keyless-candidate-preregistration-v1.json"


def main() -> int:
    bundle = build_m8a_preregistration_bundle(ROOT)
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    DESTINATION.write_text(bundle.canonical_json(), encoding="utf-8")
    print(f"M8A_PREREGISTRATION_FROZEN={bundle.bundle_digest}")
    print(f"M8A_PREREGISTRATION_PATH={DESTINATION.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
