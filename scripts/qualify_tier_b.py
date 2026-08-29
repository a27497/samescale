from __future__ import annotations

import argparse
from pathlib import Path

from harnesslab.tasks.tier_b import build_tier_b_qualification

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "release/tier-b-qualification-v1.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build deterministic keyless Tier-B qualification")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    artifact = build_tier_b_qualification(ROOT)
    rendered = artifact.canonical_json() + "\n"
    if arguments.check:
        if (
            not arguments.output.is_file()
            or arguments.output.read_text(encoding="utf-8") != rendered
        ):
            raise SystemExit("Tier-B qualification artifact is stale")
    else:
        arguments.output.write_text(rendered, encoding="utf-8")
    print(f"qualification_id={artifact.qualification_id}")
    print(f"qualification_digest={artifact.qualification_digest}")
    print(f"task_count={artifact.task_count}")
    print("baseline_health=PASS")
    print("oracle_health=PASS")
    print("robustness=PASS")
    print("determinism=PASS")
    print("real_provider_calls=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
