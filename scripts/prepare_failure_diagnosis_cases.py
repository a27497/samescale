"""Prepare only public excerpts for the two already-fixed cases; never reads oracle/test patches."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from harnesslab.failure_diagnosis.models import EvidenceExcerpt, EvidenceKind, PublicEvidence
from harnesslab.failure_diagnosis.public_output import public_failure_lines
from harnesslab.failure_diagnosis.service import canonical, sha256
from harnesslab.failure_diagnosis.storage import load_input


def prepare(case: Path, output: Path, source_file: str, failure_log: Path) -> None:
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    receipt = case / "acceptance.json"
    pin = sha256(receipt.read_bytes())
    parsed = json.loads((case / "upstream-parse.json").read_text())
    statuses = sorted(parsed["required_statuses"].items())
    actual = json.loads(receipt.read_bytes())
    names = [name for name, status in statuses if status == "FAILED"]
    ordinals = [r["ordinal"] for r in actual["check_results"] if not r["passed"]]
    if len(names) != len(ordinals):
        raise ValueError("parsed failed counts do not match receipt")
    failed = [(n, "; ".join(names)) for n in ordinals]
    prompt = (case / "prompt.txt").read_text().split("\nIssue:\n", 1)[1]
    patch = (case / "delivery-v2/solution.patch").read_text()
    segment = next(
        section
        for section in patch.split("diff --git ")
        if section.startswith(f"a/{source_file} b/{source_file}\n")
    )
    final = None
    for line in (case / "agent.stdout").read_text().splitlines():
        value = json.loads(line)
        if (
            value.get("type") == "item.completed"
            and value.get("item", {}).get("type") == "agent_message"
        ):
            final = value["item"]["text"]
    if final is None:
        raise ValueError("missing final self-report")
    observations = public_failure_lines(failure_log.read_text())
    excerpts = [
        EvidenceExcerpt(
            id="task-1", kind=EvidenceKind.TASK, reference="prompt.txt:Issue", text=prompt
        ),
        EvidenceExcerpt(
            id="diff-1",
            kind=EvidenceKind.DIFF,
            reference=f"solution.patch:{source_file}",
            text="diff --git " + segment,
        ),
        EvidenceExcerpt(
            id="self-report-1",
            kind=EvidenceKind.SELF_REPORT,
            reference="agent.stdout:final-agent-message",
            text=final,
        ),
    ]
    for n, name in failed:
        excerpts.append(
            EvidenceExcerpt(
                id=f"check-{n}",
                kind=EvidenceKind.CHECK,
                reference=f"check:{n}",
                text=f"FAILED {name}\n" + observations,
            )
        )
    packet = PublicEvidence(public_only_reviewed=True, excerpts=tuple(excerpts))
    (output / "public-packet.json").write_bytes(canonical(packet.model_dump(mode="json")))
    item = load_input(receipt, pin, output / "public-packet.json")
    (output / "input-binding.json").write_bytes(canonical(item.model_dump(mode="json")))
    print(
        json.dumps(
            {
                "receipt": str(receipt),
                "receipt_sha256": pin,
                "public_packet": str(output / "public-packet.json"),
            },
            ensure_ascii=False,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.evidence_root
    sympy = root / "swe-external-pilot-20261014/sympy__sympy-20916"
    sphinx = root / "swe-full-20261014/agents/sphinx-doc__sphinx-7748/sphinx-doc__sphinx-7748"
    prepare(
        sympy,
        args.output / "sympy-20916",
        "sympy/printing/conventions.py",
        sympy
        / "acceptance-artifacts/external-191fddec0003499a9e58312feaaf0080-verifier/stderr.txt",
    )
    prepare(
        sphinx,
        args.output / "sphinx-7748",
        "sphinx/ext/autodoc/__init__.py",
        sphinx / "actual-test-output.txt",
    )


if __name__ == "__main__":
    main()
