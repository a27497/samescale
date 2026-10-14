"""Run in the separately locked upstream SWE-bench tooling environment, never the Subject."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    # Upstream dependencies stay outside SameScale's locked product environment.
    from swebench.harness.grading import get_eval_report, get_logs_eval
    from swebench.harness.test_spec.test_spec import make_test_spec

    mode, path = sys.argv[1:3]
    row = json.loads(Path(path).read_text())
    spec = make_test_spec(row, namespace="swebench", arch="x86_64")
    if mode == "spec":
        print(
            json.dumps(
                {
                    "eval_script": spec.eval_script,
                    "instance_id": spec.instance_id,
                    "image": spec.instance_image_key,
                }
            )
        )
        return
    if mode == "parse":
        from swebench.harness.log_parsers import MAP_REPO_TO_PARSER

        statuses = MAP_REPO_TO_PARSER[row["repo"]](Path(sys.argv[3]).read_text(), spec)
        required = json.loads(row["FAIL_TO_PASS"]) + json.loads(row["PASS_TO_PASS"])
        print(
            json.dumps(
                {
                    "required_statuses": {name: statuses.get(name) for name in required},
                    "parsed_tests": len(statuses),
                    "missing_required_tests": [name for name in required if name not in statuses],
                }
            )
        )
        return
    log, variant = sys.argv[3:5]
    statuses, found = get_logs_eval(spec, log)
    prediction = {
        "instance_id": row["instance_id"],
        "model_name_or_path": "KEYLESS_CONTROL",
        "model_patch": row["patch"] if variant == "gold" else "",
    }
    report = get_eval_report(spec, prediction, log, include_tests_status=True)
    f2p = json.loads(row["FAIL_TO_PASS"])
    p2p = json.loads(row["PASS_TO_PASS"])

    def passed(name: str) -> bool:
        return statuses.get(name) == "PASSED"

    def failed(name: str) -> bool:
        return statuses.get(name) in {"FAILED", "ERROR"}

    print(
        json.dumps(
            {
                "found": found,
                "parsed_tests": len(statuses),
                "report": report,
                "expected_f2p": len(f2p),
                "expected_p2p": len(p2p),
                "all_f2p_pass": all(passed(x) for x in f2p),
                "all_f2p_fail": all(failed(x) for x in f2p),
                "all_p2p_pass": all(passed(x) for x in p2p),
                "missing_required_tests": [x for x in f2p + p2p if x not in statuses],
            }
        )
    )


if __name__ == "__main__":
    main()
