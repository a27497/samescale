"""Write a bounded, SHA-bound Actions receipt for the offline regression gate."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

EVIDENCE_FILES = ("pytest.txt", "pytest.xml", "replay-a.txt", "replay-b.txt")


def record(output: Path, head_sha: str, summary_path: Path) -> int:
    result_path = output / "result.json"
    try:
        result = json.loads(result_path.read_text())
        if not isinstance(result, dict):
            raise ValueError("regression result is not an object")
        files = {name: output / name for name in EVIDENCE_FILES}
        if any(not path.is_file() for path in files.values()):
            raise ValueError("regression evidence file missing")
        cases = ET.parse(files["pytest.xml"]).getroot().findall(".//testcase")
        if not cases or any(list(case) for case in cases):
            raise ValueError("JUnit contains zero, failed, errored, or skipped tests")
        if result.get("status") != "PASS" or result.get("tests_passed") != len(cases):
            raise ValueError("regression receipt and JUnit do not agree on a passing result")
        receipt = {
            "head_sha": head_sha,
            "regression": result,
            "junit_cases": len(cases),
            "evidence_sha256": {
                name: "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
                for name, path in files.items()
            },
        }
        rendered = json.dumps(receipt, sort_keys=True)
        print("S3_GITHUB_RECEIPT=" + rendered, flush=True)
        with summary_path.open("a") as summary:
            summary.write("## Offline regression\n\n```json\n")
            summary.write(json.dumps(receipt, indent=2) + "\n```\n")
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError) as exc:
        print(f"S3_RECORDING_FAILED={type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: record_s3_ci.py OUTPUT_DIRECTORY")
    raise SystemExit(
        record(
            Path(sys.argv[1]),
            os.environ["GITHUB_SHA"],
            Path(os.environ["GITHUB_STEP_SUMMARY"]),
        )
    )
