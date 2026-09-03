"""Freeze/check the exact accepted candidates using original persisted files only."""

from __future__ import annotations

import argparse
from pathlib import Path

from harnesslab.evidence.reader import EvidenceReadError, trusted_artifact_path
from harnesslab.release.badcases import (
    CANONICAL,
    RECEIPT,
    SELECTED,
    SUPERSEDED_KB42_INPUTS,
    accepted_source,
    build_badcases,
    encoded,
    freeze_receipt,
    read_object,
    require,
    verify_frozen_badcases,
)
from harnesslab.release.models import BadCasePlan
from harnesslab.sandbox.artifacts import sha256_file
from harnesslab.tasks.package import digest_tree
from scripts.analyze_formal_matrix_final import _load_jsonl
from scripts.analyze_kb4_discordant_pairs import inspect_member


def audit_originals(root: Path, evidence_root: Path) -> BadCasePlan:
    source = accepted_source(root)
    timeout = read_object(root / "release/kb4-gpt-codex-timeout-sensitivity.json")
    slots = {s["slot_id"]: s for s in timeout["slots"]}
    rows = {
        r["slot_id"]: r
        for r in _load_jsonl(root / "release/core-real-matrix-v6-analysis-dataset.jsonl")
    }
    selected = {c["candidate_id"]: c for c in source["badcase_candidates"]}
    plan = build_badcases(root)
    for candidate_id, badcase in zip(SELECTED, plan.slots, strict=True):
        slot_id = selected[candidate_id]["slot_id"]
        try:
            member = inspect_member(
                slots[slot_id],
                rows[slot_id],
                root,
                evidence_root,
                timeout["provenance"]["sources_sha256"],
                {},
            )
        except EvidenceReadError as exc:
            reference = source["members"][slot_id]["manifest_reference"]
            raise EvidenceReadError(
                f"{candidate_id}: required evidence at {reference}: {exc}"
            ) from exc
        require(member == source["members"][slot_id], f"selected evidence drift: {candidate_id}")
        require(member["complete_bundle_verified"], f"incomplete selected bundle: {candidate_id}")
        detail = badcase.frozen_evidence
        assert detail is not None
        for bindings, is_tree in ((detail.file_digests, False), (detail.tree_digests, True)):
            for reference, expected in bindings.items():
                path = (
                    evidence_root / reference.removeprefix("evidence:")
                    if reference.startswith("evidence:")
                    else root / reference
                )
                path = trusted_artifact_path(path, (root, evidence_root))
                actual = digest_tree(path) if is_tree else sha256_file(path)
                require(actual == expected, f"bound artifact drift: {reference}")
    return plan


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--evidence-root",
        type=Path,
        default=Path("/home/dev/harnesslab-evidence/core-real-matrix-v6"),
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = args.repo_root.resolve()
    try:
        plan = audit_originals(root, args.evidence_root.resolve())
        payload = encoded(plan.model_dump(mode="json"))
        if not args.check:
            initial_freeze = sha256_file(root / CANONICAL) == SUPERSEDED_KB42_INPUTS[CANONICAL]
            require(
                initial_freeze or (root / CANONICAL).read_text() == payload,
                "refusing to replace drifted frozen BadCases",
            )
            if initial_freeze:
                require(not (root / RECEIPT).exists(), "freeze receipt already exists")
                (root / CANONICAL).write_text(payload)
                (root / RECEIPT).write_text(encoded(freeze_receipt(plan)))
        verify_frozen_badcases(root)
    except (OSError, ValueError, EvidenceReadError) as exc:
        raise SystemExit(f"BLOCKED_BADCASE_FREEZE_INTEGRITY: {exc}") from exc
    print("READY_FOR_FINAL_ATTRIBUTION_REPORT")
    print("3 original failure bundles verified; no subjects or verifiers executed")


if __name__ == "__main__":
    main()
