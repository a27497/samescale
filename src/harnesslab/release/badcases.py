"""Bounded, read-only construction and checking of the three K-B4.3 BadCases."""

# Preserve complete reader-facing evidence sentences, as in the V6 reports.
# ruff: noqa: E501

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from harnesslab.release.models import BadCasePlan, BadCaseSlot
from harnesslab.sandbox.artifacts import sha256_file

ACCEPTED_COMMIT = "b3c36154871225d8af1cf4247258b129f8698f1c"
SOURCE = "release/kb4-discordant-pair-attribution.json"
CANONICAL = "release/badcases.json"
RECEIPT = "release/kb4-badcase-freeze.json"
SELECTED = (
    "kb4-candidate-ab5922b348dbc889",
    "kb4-candidate-93e0206579a4fa92",
    "kb4-candidate-4d16e08b5834b3fb",
)
SOURCE_DIGESTS = {
    SOURCE: "sha256:6ab0d87c64dbee112fd17e7c46c6c8374d4aa8a5fbf9e2e31af0a93395b754ff",
    "release/kb4-discordant-pair-attribution.md": "sha256:0ca41a034fb6f9f9ffdeec1c4b19490df471ed7b8642bc6aade11e02cefcb7f9",
    "release/kb4-gpt-codex-timeout-sensitivity.json": "sha256:f7f981dab4026941e08a51f1166250fa49edf88c608c9719b6db57fa29239962",
    "release/kb4-gpt-codex-timeout-sensitivity.md": "sha256:4d2895b925f7af6fe0522f1923e6a1f9c302e7d7645483ee0f5c84cf8cf0d229",
}
# K-B4.2 describes these files at its accepted commit. Their historical hashes remain
# immutable; only these two live documents were superseded by the original freeze.
SUPERSEDED_KB42_INPUTS = {
    CANONICAL: "sha256:f6da6f36ca1ce2cce002765398000ab51d42eaa8da8a22ed45cf201e5dd4f817",
    "docs/BADCASES.md": "sha256:965d01a29510f8dcceed95a526f98183bba4afffc72fa17afd11ef4c321daa80",
}
# Phase L.2 repaired current Diagnosis metrics and the Real Agent batch updated
# Analyst docs after the freeze. These blobs remain bound at ACCEPTED_COMMIT;
# they do not describe today's implementation.
# Keep this separate from the original receipt's superseded inputs. SOURCE_DIGESTS
# pins the entire provenance document first, including in distributions without Git.
POST_FREEZE_SOURCE_UPDATES = {
    # L1 adds optional retry/status diagnostics; K-B4.2 still describes the model
    # at ACCEPTED_COMMIT, whose original blob matches this provenance digest.
    "src/harnesslab/harness_lane/models.py": "sha256:dd97691e94bb3571323777f045a8d03d112a0a6ca4504f2b4e05ccbfebd06e7e",
    "src/harnesslab/diagnosis/service.py": "sha256:84b6fb001654e38cccc690da53711e96030376967fb3e02c0965e01245d6b524",
    "docs/ANALYST.md": "sha256:d793cfbd1f0a2aad650161058fe874ddded30a7399475b26626327b1413eac39",
    "src/harnesslab/experiment/report.py": "sha256:08dc01e91774aef45844a5f0b4bda438ec28c985b5f630c54c7f1ff8e94e677c",
    "src/harnesslab/model_lane/providers.py": "sha256:2e48de8c5ffac889b01a2de53818982d85d0f37be29e93ff796f8afbc804dc3d",
    "src/harnesslab/registry/seeds.py": "sha256:54155fad2988c0ba86777156b19ef2842e4b4ad09cfa16bcd9aa63b1535ef330",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_object(path: Path) -> dict[str, Any]:
    value: dict[str, Any] = json.loads(path.read_text())
    return value


def encoded(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def accepted_source(root: Path) -> dict[str, Any]:
    for reference, digest in SOURCE_DIGESTS.items():
        require(sha256_file(root / reference) == digest, f"frozen source drift: {reference}")
    source = read_object(root / SOURCE)
    historical_inputs = SUPERSEDED_KB42_INPUTS | POST_FREEZE_SOURCE_UPDATES
    for reference, binding in source["provenance"]["sources"].items():
        if reference.startswith("evidence:"):
            continue  # Original external files are checked separately by the freeze CLI.
        if reference in historical_inputs:
            require(
                binding["sha256"] == historical_inputs[reference],
                "historical K-B4.2 input identity drift",
            )
        else:
            require(
                sha256_file(root / reference) == binding["sha256"],
                f"K-B4.2 repository source drift: {reference}",
            )
    return source


def build_badcases(root: Path) -> BadCasePlan:
    source = accepted_source(root)
    candidates = {c["candidate_id"]: c for c in source["badcase_candidates"]}
    dataset = {
        row["slot_id"]: row
        for row in map(
            json.loads,
            (root / "release/core-real-matrix-v6-analysis-dataset.jsonl").read_text().splitlines(),
        )
    }
    slots = []
    for index, candidate_id in enumerate(SELECTED, 1):
        c = candidates[candidate_id]
        m = source["members"][c["slot_id"]]
        row = dataset[c["slot_id"]]
        require(
            c["eligible_for_final_freeze_review"]
            and c["suitability"] == "READY_FOR_REVIEW"
            and m["complete_bundle_verified"]
            and m["verifier"]["status"] == "FAILED"
            and row["primary_status"] == "failed_subject"
            and row["effective_outcome"] == "capability_fail",
            f"ineligible selected candidate: {candidate_id}",
        )
        run_ref = "run:" + row["run_id"]  # Logical experiment run, not physical -a1 attempt.
        task_ref = f"task:{m['task_id']}@{m['task_version']}#{m['task_digest']}"
        trace_digest = m["manifest_facts"]["normalized_trace_digest"]
        package_prefix = row["task_package_path"] + "/"
        run_prefix = m["manifest_reference"].removesuffix("manifest.json")
        files = {
            ref: binding["sha256"]
            for ref, binding in source["provenance"]["sources"].items()
            if ref.startswith((run_prefix, package_prefix))
        }
        trees = {
            m[part]["binding"]["reference"]: m[part]["binding"]["expected_digest"]
            for part in ("workspace", "verifier")
        }
        trace_facts = tuple(
            "TRACE_EVENT_TYPE:" + kind for kind in sorted(m["trace"].get("event_type_counts", {}))
        )
        java = m["failure_class"] == "No Modification"
        hypotheses = []
        limitations = [
            "A factual verifier failure does not establish a causal mechanism. Root cause is null.",
            "No Harness-uplift or formal reasoning-effort effect is established; formal eligibility remains false.",
            "The three cases cover two failure signatures; the Python cases are related observations.",
        ]
        if java:
            observed = (
                "The workspace is unchanged. The deterministic verifier fails normalizes, "
                "preserves-order, duplicate-rejected, and invalid-rejected; input-unchanged passes."
            )
            tools: tuple[str, ...] = (
                "Four trace events: thread start, turn start, public agent message, turn completion; no commands or file edits.",
                "The public workspace-unavailable statement is unverified self-report; no runtime cause is established.",
            )
            lesson = (
                "Check that the required implementation changed and inspect deterministic verifier results before declaring completion. "
                "This is an engineering safeguard, not a verified remedy for the unknown cause."
            )
        else:
            observed = (
                "The deterministic verifier fails empty-key-rejected (score 0.8); first-records, "
                "identical-retry-idempotent, conflict-rejected, and conflict-preserves-original pass. "
                "The digest-bound events.py implementation stores an empty key and returns True."
            )
            tools = (
                (
                    "The bound trace contains file changes and public commands with assertions accepting empty keys.",
                    "A git command exits 128; that incidental tool fact does not supersede the verifier-backed Test Failure.",
                    "Issued assertion and byte-compile syntax does not prove every shell subcommand ran or passed.",
                )
                if trace_digest
                else ()
            )
            hypothesis = next(
                f for f in source["findings"] if f["level"] == "ATTRIBUTION_HYPOTHESIS"
            )
            hypotheses.append(
                {
                    "classification": "ATTRIBUTION_HYPOTHESIS",
                    "statement": hypothesis["statement"],
                    "verify_or_falsify": hypothesis["verify_or_falsify"],
                    "evidence_refs": hypothesis["evidence_refs"],
                }
            )
            limitations.append(
                "The public instruction specifies non-empty-key behavior without expressly requiring empty-key rejection; "
                "the frozen verifier does require rejection. This limitation does not alter the frozen score."
            )
            lesson = (
                "Review public contract and boundary-case checks together before interpreting the failure. "
                "Explicit empty-key expectations are a proposed engineering clarification, not a proven causal remedy; "
                "the frozen task and verifier remain unchanged."
            )
        if not trace_digest:
            limitations.append(
                "Direct has no normalized agent trace. No command, edit sequence, or private reasoning is reconstructed; "
                "the factual explanation uses verifier output and the final source diff."
            )
        comparisons = []
        for pair in c["comparisons"]:
            comparisons.append(
                {
                    "comparison_id": pair["comparison_id"],
                    "pair_id": pair["pair_id"],
                    "status": pair["comparability"]["status"],
                    "reason_codes": [r["code"] for r in pair["comparability"]["reasons"]],
                    "both_member_bundles_verified": pair["both_member_bundles_verified"],
                }
            )
            if not pair["both_member_bundles_verified"]:
                limitations.append(
                    "The failure bundle is intact, but the passing comparison member has a tree-integrity limitation. "
                    "Frozen comparability is retained; complete paired-trajectory audit and causal attribution are not claimed."
                )
        refs = [
            run_ref,
            "cell:" + m["cell_id"],
            task_ref,
            "verifier:" + row["verifier_identity"],
            "manifest:" + m["manifest_digest"],
            SOURCE,
            *files,
            *trees,
        ]
        if trace_digest:
            refs.append(f"trace:{row['run_id']}#{trace_digest}")
        slots.append(
            BadCaseSlot.model_validate(
                {
                    "slot_id": f"badcase-{index}",
                    "status": "VERIFIED",
                    "task_identity": task_ref,
                    "run_identity": run_ref,
                    "cell_identity": "cell:" + m["cell_id"],
                    "evidence_refs": sorted(set(refs)),
                    "observed_failure": observed,
                    "safe_trace_facts": trace_facts,
                    "verifier_result": "capability_fail:verified_fail",
                    "attribution_classification": "OBSERVED_FACT",
                    "root_cause": None,
                    "mitigation_lesson": lesson,
                    "harnesslab_detection": (
                        "HarnessLab binds the failed_subject/capability_fail run to its manifest, verifies artifact digests, "
                        "and retains individual deterministic checks, source differences, and available safe trace facts. "
                        "This exposes unchanged implementation or an empty-key boundary failure hidden by aggregate pass rates."
                    ),
                    "placeholder": None,
                    "hypotheses": hypotheses,
                    "limitations": limitations,
                    "frozen_evidence": {
                        "candidate_id": candidate_id,
                        "experiment_id": source["provenance"]["experiment_id"],
                        "experiment_slot_id": m["slot_id"],
                        "repeat_index": m["repeat_index"],
                        "effective_source": m["effective_source"],
                        "execution_run_identity": "run:" + m["effective_run_id"],
                        "primary_run_identity": "run:" + m["primary"]["run_id"],
                        "recovery_run_identity": "run:" + m["recovery"]["run_id"]
                        if m["recovery"]
                        else None,
                        "manifest_digest": m["manifest_digest"],
                        "profile_identity": m["manifest_facts"]["plan_profile_identity"],
                        "harness_config_identity": m["manifest_facts"][
                            "plan_harness_config_identity"
                        ],
                        "failure_class": m["failure_class"],
                        "verifier_report": m["verifier"]["report"],
                        "trace_status": m["trace"]["status"],
                        "normalized_trace_digest": trace_digest,
                        "safe_tool_facts": tools,
                        "source_diffs": [d["unified_diff"] for d in m["workspace"]["source_diffs"]],
                        "file_digests": files,
                        "tree_digests": trees,
                        "comparisons": comparisons,
                    },
                }
            )
        )
    return BadCasePlan(slots=tuple(slots))


def freeze_receipt(plan: BadCasePlan) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "phase": "K-B4.3",
        "accepted_source_commit": ACCEPTED_COMMIT,
        "status": "READY_FOR_FINAL_ATTRIBUTION_REPORT",
        "source_digests": SOURCE_DIGESTS,
        "superseded_kb42_inputs": SUPERSEDED_KB42_INPUTS,
        "canonical_reference": CANONICAL,
        "canonical_model_digest": plan.digest,
        "selected": [
            {
                "slot_id": s.slot_id,
                "candidate_id": s.frozen_evidence.candidate_id,
                "manifest_digest": s.frozen_evidence.manifest_digest,
            }
            for s in plan.slots
            if s.frozen_evidence is not None
        ],
        "integrity": "All three required original failure bundles independently revalidated before freeze; file/tree digests are in the canonical records.",
        "portable_check_scope": "Schema, exact accepted selection, frozen source bindings, canonical bytes and receipt. Original external files require the CLI --check with the persisted evidence root.",
        "distinct_failure_signatures": 2,
        "controlled_attribution_claims": 0,
        "later_phases": {
            "final_attribution_report": "NOT_RUN",
            "kb4_final_gate": "NOT_RUN",
            "kc": "NOT_RUN",
        },
        "external_execution": {"provider": 0, "harness": 0, "judge": 0, "matrix": 0, "ablation": 0},
    }


def verify_frozen_badcases(root: Path) -> BadCasePlan:
    expected = build_badcases(root)
    actual = BadCasePlan.model_validate_json((root / CANONICAL).read_text())
    require(actual == expected, "canonical BadCase drift")
    require(
        (root / CANONICAL).read_text() == encoded(expected.model_dump(mode="json")),
        "BadCase byte drift",
    )
    require(
        (root / RECEIPT).read_text() == encoded(freeze_receipt(expected)), "freeze receipt drift"
    )
    return actual
