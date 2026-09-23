"""Export a public-safe, single-file demo from the existing S1/S2/S3 frozen evidence."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
import tempfile
from pathlib import Path
from string import Template
from typing import Any

from harnesslab.analyst.offline_replay import (
    ReplayError,
    compare_replays,
    decode,
    read_pinned,
    render_diagnosis,
    replay_bundle,
    require,
)
from harnesslab.evidence.offline_boundary import offline_guard
from harnesslab.tasks.package import sha256_bytes
from scripts.replay_d2 import replay as replay_d2
from scripts.verify_s3_regression import ARCHIVE_DIGEST, GOLDEN, INPUTS_DIGEST, extract_archive

ROOT = Path(__file__).resolve().parents[1]
S2 = "docs/evidence/s2-offline-replay-20260921"
S3 = "docs/evidence/s3-ci-regression-20260921"
S1 = "docs/evidence/s1-partial-closeout-20260921/final-status.json"
D1 = "docs/evidence/d1-config-decision-20260923/result.json"
SOURCE_PINS: dict[str, str] = {
    "docs/evidence/d1-config-decision-20260923/ACCEPTANCE_AUDIT.md": (
        "sha256:f94e191ea1cc3d4ebe681c6a835da44be6d838f95391085a4f6f0bb206411437"
    ),
    "docs/evidence/d1-config-decision-20260923/result.json": (
        "sha256:d67c20ad15e935ac4a787ed8d2ca1a8299f7f8b389fdf134971cbc9d9d7701d8"
    ),
    "docs/evidence/d2-natural-failure-20260923/freeze.json": (
        "sha256:a2a34894344177fb36407d5b5e93f5351089f67423779cfa485f7cf26bec9f0b"
    ),
    "docs/evidence/s2-offline-replay-20260921/README.md": (
        "sha256:9f5b586f9fa0ab521ea0c42fec237818caf59b7ab89a154ed1644c8b20cef70b"
    ),
    "docs/evidence/s1-partial-closeout-20260921/final-status.json": (
        "sha256:236aebfa45427db32c719207d255e9bb810077788a56145065c741333817a5a1"
    ),
    "docs/evidence/s3-ci-regression-20260921/github-offline-run.json": (
        "sha256:5c94ef405721295f452766e08f7724863b87cf13d7863d696cf16e3f85ef5820"
    ),
    "docs/evidence/s3-ci-regression-20260921/github-fast-run.json": (
        "sha256:bae08efbd4ccd079ce11edb1734810998798821dbbb6e696a76dba49a7fed064"
    ),
    "docs/evidence/s3-ci-regression-20260921/github-receipt.json": (
        "sha256:3cf02fdfcdcbbb8a75353f878bffbc8dd03f282f17b8e27ab61331204f08795b"
    ),
}


def project(root: Path = ROOT) -> dict[str, Any]:
    """Verify full private inputs first, then explicitly select shareable fields only."""
    sources = {
        p: decode(read_pinned(root / p, digest))
        for p, digest in SOURCE_PINS.items()
        if p.endswith(".json")
    }
    for p, digest in SOURCE_PINS.items():
        read_pinned(root / p, digest)
    status = sources[S1]
    require(
        status["status"] == "BLOCKED"
        and status["planned_cells"] == 16
        and status["attempted_cells"] == 2
        and status["not_run"] == 14
        and not status["ability_ranking_allowed"],
        "S1 scope drift",
    )
    d1 = sources[D1]
    require(
        d1["planned"] == 20
        and d1["attempted"] == 2
        and d1["verified_pass"] == 1
        and d1["not_verified"] == 1
        and d1["not_run"] == 18
        and d1["decision"] == "INSUFFICIENT EVIDENCE"
        and d1["metrics"]["consistency"] == "NOT_VERIFIED",
        "D1 decision scope drift",
    )
    d2 = replay_d2(root)
    with tempfile.TemporaryDirectory(prefix="s4-replay-") as temporary:
        inputs_root = Path(temporary) / "inputs"
        extract_archive(root / S2 / "representative-bundles.zip", inputs_root)
        inputs = decode(read_pinned(inputs_root / "inputs.json", INPUTS_DIGEST))
        replays = {
            side: replay_bundle(inputs_root / value["path"], value["sha256"])
            for side, value in inputs["bundles"].items()
        }
        diff = compare_replays(replays["codex"], replays["claude"])
        fresh = {f"{side}.json": data for side, data in replays.items()}
        fresh["trace-diff.json"] = diff
        for name, data in fresh.items():
            raw = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode()
            require(sha256_bytes(raw) == GOLDEN[name], "replay/golden drift")
        require(
            sha256_bytes(render_diagnosis(diff).encode()) == GOLDEN["diagnosis.md"],
            "diagnosis drift",
        )
        for name, digest in GOLDEN.items():
            read_pinned(root / S2 / name, digest)
    receipt = sources[f"{S3}/github-receipt.json"]
    for name in ("github-offline-run.json", "github-fast-run.json"):
        run = sources[f"{S3}/{name}"]
        require(
            run["headSha"] == receipt["head_sha"] and run["conclusion"] == "success",
            "CI acceptance mismatch",
        )
    require(
        receipt["regression"]["status"] == "PASS"
        and receipt["regression"]["tests_passed"] == 65
        and receipt["regression"]["identical_outputs"] == GOLDEN,
        "CI replay contract drift",
    )
    cards = []
    for side, label in (("codex", "Official Codex"), ("claude", "Claude Code")):
        run = replays[side]
        cards.append(
            {
                "label": label,
                "requested_model": run["configuration"]["requested_model"],
                "result": run["task_verification"],
                "verifier": run["verification"]["state"],
                "checks": run["verification"]["checks"],
                "passed_checks": run["verification"]["passed_checks"],
                "subject_seconds": run["duration_usage"]["subject_ms"] / 1000,
                "tool_count": run["trace"]["tool_count"],
                "changed_files": [
                    {"file": Path(change["path"]).name, "status": change["status"]}
                    for change in run["changed_files"]
                ],
                "failure_taxonomy": run["completion_failure"]["failure_taxonomy"],
                "tools": [
                    {
                        "start": tool["start_ordinal"],
                        "end": tool["end_ordinal"],
                        "tool": tool["tool"],
                        "status": tool["status"],
                    }
                    for tool in run["trace"]["tools"]
                ],
            }
        )
    return {
        "schema_version": 1,
        "kind": "PUBLIC_RECRUITER_DEMO",
        "recorded_date": "2026-09-23",
        "s1": {"status": "PARTIAL REAL BENCHMARK / BLOCKED", "attempted": 2, "planned": 16},
        "d1": {
            "status": "COMPLETE",
            "decision": d1["decision"],
            "attempted": d1["attempted"],
            "planned": d1["planned"],
            "not_run": d1["not_run"],
            "consistency": d1["metrics"]["consistency"],
            "median_latency": "NOT_VERIFIED",
            "observed_cost": "NOT_AVAILABLE",
        },
        "d2": d2,
        "cards": cards,
        "replay": {"status": "PASS", "archive_sha256": ARCHIVE_DIGEST, "outputs": GOLDEN},
        "ci": {"status": "RECORDED_PASS", "sha": receipt["head_sha"], "tests": 65},
        "new_model_calls": 0,
        "sources": {Path(p).name: digest for p, digest in SOURCE_PINS.items()},
    }


def render(data: dict[str, Any], template: str) -> str:
    def escape(value: Any) -> str:
        return html.escape(str(value))

    cards, tools = [], []
    for index, card in enumerate(data["cards"]):
        checks = "20 / 20 · independent verifier" if index == 0 else "NOT_RUN · 未执行 verifier"
        cards.append(
            f'<article class="result"><p class="eyebrow">{escape(card["label"])}</p>'
            f"<h3>{escape(card['result'])}</h3><p>{checks}</p>"
            f"<dl><dt>Subject duration</dt><dd>{card['subject_seconds']:.3f} s</dd>"
            f"<dt>工具活动</dt><dd>{card['tool_count']}</dd><dt>修改文件</dt>"
            f"<dd>{len(card['changed_files'])}</dd></dl></article>"
        )
        rows = "".join(
            "<tr>" + "".join(f"<td>{escape(value)}</td>" for value in row.values()) + "</tr>"
            for row in card["tools"]
        )
        tools.append(
            f"<details><summary>{escape(card['label'])} · "
            f"工具序列 ({card['tool_count']})</summary>"
            '<div class="table"><table><thead><tr><th>开始 ordinal</th><th>结果 ordinal</th>'
            "<th>工具</th><th>记录状态</th></tr></thead><tbody>"
            + rows
            + "</tbody></table></div></details>"
        )
    sources = "".join(
        f"<li><strong>{escape(name)}</strong><code>{escape(digest)}</code></li>"
        for name, digest in {**data["sources"], **data["replay"]["outputs"]}.items()
    )
    return Template(template).substitute(
        cards="".join(cards),
        tools="".join(tools),
        sources=sources,
        ci_sha=escape(data["ci"]["sha"]),
        d1_decision=escape(data["d1"]["decision"]),
        d2_checks=escape(
            f"{data['d2']['independent_verifier_passed']}/{data['d2']['independent_verifier_total']}"
        ),
    )


def export(output: Path, root: Path = ROOT) -> None:
    require(not output.exists(), "output must be new")
    require(
        not output.resolve().is_relative_to(root / "docs/evidence"), "immutable evidence output"
    )
    data = project(root)
    page = render(data, (root / "docs/recruiter/template.html").read_text())
    payloads = {
        "index.html": page,
        "public-evidence.json": json.dumps(data, ensure_ascii=False, indent=2) + "\n",
    }
    output.mkdir(parents=True, exist_ok=False)
    for name, value in payloads.items():
        (output / name).write_text(value)
    (output / "SHA256SUMS").write_text(
        "".join(f"{hashlib.sha256(v.encode()).hexdigest()}  {k}\n" for k, v in payloads.items())
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sys.addaudithook(offline_guard)
    try:
        export(args.output)
    except (AssertionError, ReplayError, OSError, KeyError, ValueError, TypeError):
        print("FAIL_CLOSED: invalid evidence or output; no demo published")
        return 2
    print("PASS: public-safe offline demo exported; new Provider/model/Claude/Judge calls=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
