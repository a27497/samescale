"""Diagnose persisted V6 discordances without executing subjects, verifiers, or an Analyst."""

# Reader-facing report sentences follow the existing V6 analysis convention.
# ruff: noqa: E501
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from pathlib import Path
from typing import Any, cast

from harnesslab.diagnosis.models import (
    DiagnosisInput,
    EvidenceOrigin,
    FailureClass,
    ToolCallEvidence,
    TraceEventEvidence,
    TraceEvidence,
)
from harnesslab.diagnosis.service import _failure_class, _trace_pattern, _verifier, _workspace_diff
from harnesslab.evidence.reader import trusted_artifact_path
from harnesslab.experiment.outcomes import normalize_manifest_evidence
from harnesslab.experiment.statistics import evidence_tier
from harnesslab.harness_lane.models import NormalizedTrace
from harnesslab.harness_lane.runner import changed_path_evidence, workspace_inventory
from harnesslab.tasks.models import VerifierReport
from harnesslab.tasks.package import TaskPackage, digest_tree
from scripts.analyze_formal_matrix_final import _load_jsonl, _sha256_file, _validate_dataset
from scripts.analyze_kb4_timeout_sensitivity import OUTPUT as TIMEOUT_OUTPUT
from scripts.analyze_kb4_timeout_sensitivity import PAIR_DEFINITIONS, counts, require
from scripts.analyze_kb4_timeout_sensitivity import validate as validate_timeout

OUTPUT = "release/kb4-discordant-pair-attribution"
BASE_COMMIT = "ed9ce4c51b1f78811bc840c87a2a82be8a745305"
PREFIX = "release/core-real-matrix-v6-"
CAPABILITY = {"capability_pass", "capability_fail"}
FROZEN_INPUTS = {
    TIMEOUT_OUTPUT
    + ".json": "sha256:f7f981dab4026941e08a51f1166250fa49edf88c608c9719b6db57fa29239962",
    TIMEOUT_OUTPUT
    + ".md": "sha256:4d2895b925f7af6fe0522f1923e6a1f9c302e7d7645483ee0f5c84cf8cf0d229",
    "release/badcases.json": "sha256:f6da6f36ca1ce2cce002765398000ab51d42eaa8da8a22ed45cf201e5dd4f817",
}
LEVELS = (
    "OBSERVED_FACT",
    "DIAGNOSTIC_ASSOCIATION",
    "ATTRIBUTION_HYPOTHESIS",
    "CONTROLLED_ATTRIBUTION",
)


def digest_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    require(isinstance(value, dict), "expected JSON object")
    return cast(dict[str, Any], value)


def discordance_kind(pair: dict[str, Any]) -> str:
    a, b = pair["effective"]["left_outcome"], pair["effective"]["right_outcome"]
    if a not in CAPABILITY or b not in CAPABILITY:
        return "MISSING_CAPABILITY"
    if a == b:
        return "CONCORDANT"
    return "LEFT_PASS_RIGHT_FAIL" if a == "capability_pass" else "LEFT_FAIL_RIGHT_PASS"


def trace_projection(raw: dict[str, Any]) -> dict[str, Any]:
    trace = NormalizedTrace.model_validate(raw)
    events = []
    for event in trace.events:
        # Never copy text or outputs, even for REASONING_PRESENT. Commands are public tool
        # actions but can contain large source dumps, so retain their hashes and bounded markers.
        command = event.command or ""
        markers = [
            name
            for name, needle in (
                ("python_byte_compile", "-m py_compile"),
                ("java_compile", "javac"),
                ("pytest_invocation", "pytest"),
                ("npm_test_invocation", "npm test"),
                ("assertion_syntax", "assert "),
                ("empty_key_call_syntax", "record_success(''"),
            )
            if needle in command
        ]
        events.append(
            {
                "ordinal": event.ordinal,
                "type": event.type.value,
                "item_id": event.item_id,
                "status": event.status,
                "exit_code": event.exit_code,
                "file_changes": [v.model_dump(mode="json") for v in event.file_changes],
                "command_sha256": digest_text(command) if command else None,
                "command_markers": markers,
                "empty_key_acceptance_assertion_lines": [
                    line.strip()
                    for line in command.splitlines()
                    if line.strip().startswith("assert ")
                    and "record_success(''," in line
                    and line.strip().endswith(" is True")
                ],
                "workspace_unavailable_self_report": event.type.value == "AGENT_MESSAGE"
                and "workspace is unavailable" in (event.text or ""),
                "public_output_sha256": digest_text(event.public_output)
                if event.public_output
                else None,
                "git_repository_error_reported": "fatal: not a git repository"
                in (event.public_output or ""),
            }
        )
    commands = [e for e in events if e["type"] == "COMMAND_EXECUTION"]
    return {
        "status": "REPORTED",
        "events": events,
        "event_type_counts": counts(e["type"] for e in events),
        "completed_command_events": sum(e["status"] in {"completed", "failed"} for e in commands),
        "successful_command_events": sum(
            e["status"] == "completed" and e["exit_code"] == 0 for e in commands
        ),
        "failed_command_events": [
            e["ordinal"] for e in commands if e["exit_code"] not in {None, 0}
        ],
        "check_or_build_command_events": [e["ordinal"] for e in commands if e["command_markers"]],
        "command_detail_policy": "Hashes/ordinals locate full public commands in the bound trace; no command is executed here. Markers describe issued syntax, not successful subcommands or test coverage. Shell exit zero cannot prove every command succeeded.",
        "private_reasoning_persisted": False,
    }


def classify_failure(member: dict[str, Any]) -> str | None:
    if member["effective_outcome"] != "capability_fail":
        return None
    raw = member["manifest_facts"]
    verifier = _verifier(raw)
    workspace = _workspace_diff(raw, frozenset(member["protected_paths"]))
    # Specific verifier-backed findings take precedence over ancillary failed tool calls.
    # This is the existing declared_failure_class input, not a competing taxonomy.
    declared = None
    if member["verifier"]["status"] == "FAILED":
        declared = (
            FailureClass.NO_MODIFICATION
            if workspace.pattern == "no-modification"
            else FailureClass.TEST_FAILURE
        )
    events = tuple(
        TraceEventEvidence(
            ordinal=e["ordinal"], type=e["type"], status=e["status"], exit_code=e["exit_code"]
        )
        for e in member["trace"].get("events", [])
    )
    failed = tuple(e.exit_code for e in events if e.exit_code not in {None, 0})
    item = DiagnosisInput(
        run_id=member["effective_run_id"],
        origin=EvidenceOrigin.IMMUTABLE_EXPERIMENT,
        cell_id=member["cell_id"],
        task_id=member["task_id"],
        task_version=member["task_version"],
        model=raw["requested_model"],
        harness=raw.get("harness") or "direct-model",
        language=member["language"],
        task_family=member["category"],
        normalized_outcome=member["effective_outcome"],
        source_outcome=member["source_outcome"],
        declared_failure_class=declared,
        provider_failure=raw.get("provider_failure"),
        harness_failure=raw.get("harness_failure"),
        artifact_available=True,
        evidence_identity=member["manifest_digest"],
        trace=TraceEvidence(
            status="REPORTED" if events else "NOT_REPORTED",
            coverage=raw.get("trace_coverage"),
            digest=raw.get("normalized_trace_digest"),
            pattern=_trace_pattern(events, raw.get("trace_coverage")),
            events=events,
        ),
        workspace_diff=workspace,
        tool_calls=ToolCallEvidence(
            status="REPORTED" if events else "NOT_REPORTED",
            pattern=f"failed-command-events={len(failed)}",
            failed_exit_codes=failed,
        ),
        verifier=verifier,
    )
    return _failure_class(item).value


def inspect_member(
    slot: dict[str, Any],
    row: dict[str, Any],
    root: Path,
    evidence_root: Path,
    expected_sources: dict[str, str],
    sources: dict[str, Any],
) -> dict[str, Any]:
    selected = slot[slot["effective_source"]]
    reference = selected["manifest_reference"]
    manifest_path = trusted_artifact_path(
        evidence_root / reference.removeprefix("evidence:"), (evidence_root,)
    )

    def bound_file(path: Path, expected: str | None = None) -> str:
        path = trusted_artifact_path(path, (root, evidence_root))
        ref = (
            path.relative_to(root).as_posix()
            if path.is_relative_to(root)
            else "evidence:" + path.relative_to(evidence_root).as_posix()
        )
        actual = _sha256_file(path)
        require(expected is None or actual == expected, f"file digest mismatch: {ref}")
        sources[ref] = {"sha256": actual, "binding": "MATCH" if expected else "CONTENT_ADDRESSED"}
        return ref

    bound_file(manifest_path, expected_sources[reference])
    raw = read_json(manifest_path)
    require(raw["run_id"] == selected["run_id"], "attempt identity drift")
    require(raw["task_digest"] == slot["task_digest"], "manifest task drift")
    normalized = normalize_manifest_evidence(raw)
    require(normalized.outcome.value == slot["effective_outcome"], "effective outcome drift")
    require(normalized.source_taxonomy == selected["source_outcome"], "source taxonomy drift")
    package_root = root / row["task_package_path"]
    package = TaskPackage.load(package_root)
    require(package.definition.content_digest == slot["task_digest"], "task package drift")
    require(package.verifier_digest == row["verifier_identity"], "verifier definition drift")
    for path in package_root.rglob("*"):
        if path.is_file():
            bound_file(path)
    raw_facts = {
        k: raw.get(k)
        for k in (
            "requested_model",
            "observed_model",
            "harness",
            "provider_failure",
            "harness_failure",
            "outcome",
            "verifier_passed",
            "verifier_score",
            "trace_coverage",
            "normalized_trace_digest",
            "native_transcript_digest",
            "workspace_input_digest",
            "workspace_output_digest",
            "changed_paths",
            "verifier_artifact_digest",
            "verifier_sandbox_manifest",
            "timed_out",
            "duration_ms",
            "process_exit_code",
            "terminal_native_event",
            "plan_profile_identity",
            "plan_harness_config_identity",
        )
    }
    member: dict[str, Any] = {
        k: slot[k]
        for k in (
            "slot_id",
            "cell_id",
            "task_id",
            "task_version",
            "task_digest",
            "repeat_index",
            "language",
            "category",
            "paired_slot_identity",
            "effective_outcome",
            "effective_source",
            "primary_attempt_count",
            "unobserved_extra_primary_attempts",
        )
    }
    member.update(
        effective_run_id=raw["run_id"],
        source_outcome=selected["source_outcome"],
        manifest_reference=reference,
        manifest_digest=expected_sources[reference],
        manifest_facts=raw_facts,
        primary=slot["primary"],
        recovery=slot["recovery"],
        recovery_link=slot.get("recovery_link"),
        protected_paths=list(package.manifest.protected_paths),
        task_contract={
            "instruction": (package_root / package.manifest.instruction_path).read_text(),
            "source": row["task_package_path"] + "/instruction.md",
        },
        execution_budget={
            k: selected[k]
            for k in (
                "duration_ms",
                "duration_basis",
                "execution_limit_seconds",
                "timeout_fact",
                "execution_budget_capability_failure",
            )
        },
    )
    run_root = manifest_path.parent
    trace_path = run_root / "trace/normalized.json"
    if raw.get("normalized_trace_digest"):
        bound_file(trace_path, raw["normalized_trace_digest"])
        member["trace"] = trace_projection(read_json(trace_path))
        member["trace"]["reference"] = (
            "evidence:" + trace_path.relative_to(evidence_root).as_posix()
        )
        if raw.get("native_transcript_digest"):
            bound_file(run_root / "native/codex.sanitized.jsonl", raw["native_transcript_digest"])
    else:
        member["trace"] = {
            "status": "NOT_REPORTED",
            "events": [],
            "private_reasoning_persisted": False,
        }

    def tree_binding(directory: Path, expected: str) -> dict[str, Any]:
        actual = digest_tree(directory) if directory.is_dir() else None
        return {
            "expected_digest": expected,
            "actual_digest": actual,
            "status": "MATCH" if actual == expected else "INTEGRITY_MISMATCH",
            "reference": "evidence:" + directory.relative_to(evidence_root).as_posix(),
        }

    workspace_path = run_root / "workspace"
    workspace_binding = tree_binding(workspace_path, raw["workspace_output_digest"])
    require(
        digest_tree(package_root / "workspace") == raw["workspace_input_digest"],
        "baseline workspace drift",
    )
    before = workspace_inventory(package_root / "workspace")
    after = workspace_inventory(workspace_path)
    actual_changes = changed_path_evidence(before, after)
    expected_paths = {x.path: x.digest for x in before}
    for change in raw.get("changed_paths") or []:
        if change["after_digest"] is None:
            expected_paths.pop(change["path"], None)
        else:
            expected_paths[change["path"]] = change["after_digest"]
    actual_paths = {x.path: x.digest for x in after}
    missing = (
        sorted(set(expected_paths) - set(actual_paths))
        if raw.get("changed_paths") is not None
        else []
    )
    diffs = []
    for change in actual_changes:
        path = change.path
        if Path(path).suffix not in {".py", ".java", ".ts", ".txt"}:
            continue
        old = package_root / "workspace" / path
        new = workspace_path / path
        file_verified = workspace_binding["status"] == "MATCH" or (
            raw.get("changed_paths") is not None
            and actual_paths.get(path) == expected_paths.get(path)
        )
        require(file_verified, "source file differs from bound workspace inventory")
        for source in (old, new):
            if source.is_file():
                bound_file(source)
        diff = "".join(
            difflib.unified_diff(
                old.read_text().splitlines(True) if old.is_file() else [],
                new.read_text().splitlines(True) if new.is_file() else [],
                fromfile="baseline/" + path,
                tofile="observed/" + path,
            )
        )
        diffs.append(
            {
                "path": path,
                "before_digest": change.before_digest,
                "after_digest": change.after_digest,
                "file_binding_verified": True,
                "unified_diff": diff if len(diff) <= 16000 else None,
                "diff_sha256": digest_text(diff),
            }
        )
    member["workspace"] = {
        "binding": workspace_binding,
        "missing_manifest_inventory_paths": missing,
        "recorded_changed_paths": raw.get("changed_paths"),
        "available_snapshot_changes": [v.model_dump(mode="json") for v in actual_changes],
        "source_diffs": diffs,
        "unchanged_verified": workspace_binding["status"] == "MATCH"
        and raw["workspace_input_digest"] == raw["workspace_output_digest"],
        "limitation": "Individual source-file matches do not repair missing bytecode/class files or prove the full snapshot digest.",
    }
    if raw.get("verifier_artifact_digest"):
        verifier_root = run_root / "verifier"
        vb = tree_binding(verifier_root, raw["verifier_artifact_digest"])
        verifier_manifest = read_json(verifier_root / "manifest.json")
        require(verifier_manifest == raw["verifier_sandbox_manifest"], "verifier manifest drift")
        bound_file(verifier_root / "manifest.json")
        for stream in ("stdout", "stderr"):
            bound_file(verifier_root / f"{stream}.txt", verifier_manifest[stream]["digest"])
        report = VerifierReport.model_validate_json((verifier_root / "stdout.txt").read_text())
        require(
            report.passed == raw["verifier_passed"] and report.score == raw["verifier_score"],
            "verifier result drift",
        )
        require(report.passed == all(c.passed for c in report.checks), "verifier checks disagree")
        require(
            verifier_manifest["workspace_input_digest"] == raw["workspace_output_digest"],
            "verifier input drift",
        )
        member["verifier"] = {
            "status": "PASSED" if report.passed else "FAILED",
            "binding": vb,
            "report": report.model_dump(mode="json"),
            "stdout_independently_digest_verified": True,
            "failed_checks": [c.name for c in report.checks if not c.passed],
            "report_reference": "evidence:"
            + (verifier_root / "stdout.txt").relative_to(evidence_root).as_posix(),
        }
    else:
        member["verifier"] = {
            "status": "NOT_RUN",
            "failed_checks": [],
            "report": None,
            "binding": {"status": "NOT_APPLICABLE"},
        }
    member["complete_bundle_verified"] = workspace_binding["status"] == "MATCH" and member[
        "verifier"
    ]["binding"]["status"] in {"MATCH", "NOT_APPLICABLE"}
    member["failure_class"] = classify_failure(member)
    member["failure_scope"] = (
        "CAPABILITY" if member["effective_outcome"] == "capability_fail" else None
    )
    member["diagnosis_level"] = "OBSERVED_FACT"
    return member


def summarize(ledgers: dict[str, Any], members: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for name, ledger in ledgers.items():
        dd = ledger["discordant_pairs"]
        groups = {}
        for status in ("COMPARABLE", "PARTIALLY_COMPARABLE", "NOT_COMPARABLE"):
            pairs = [p for p in dd if p["comparability"]["status"] == status]
            groups[status] = {
                "discordant_pairs": len(pairs),
                "direction": counts(p["direction"] for p in pairs),
                "failure_taxonomy": counts(
                    members[p["failed_slot_id"]]["failure_class"] for p in pairs
                ),
            }
        result[name] = {
            "planned_pairs": 90,
            "effective_complete_pairs": ledger["frozen_summary"]["effective"][
                "capability_complete"
            ],
            "complete_pair_comparability": ledger["frozen_summary"]["effective"][
                "complete_pair_comparability"
            ],
            "formal_eligible": ledger["frozen_summary"]["effective"]["formal_eligible"],
            "discordant_pairs": len(dd),
            "direction": counts(p["direction"] for p in dd),
            "concordant_pairs": len(ledger["concordant_pairs"]),
            "excluded_missing_pairs": len(ledger["excluded_pairs"]),
            "timeout_affected_missing_pairs": sum(
                bool(p["unresolved_timeout_slots"]) for p in ledger["excluded_pairs"]
            ),
            "by_comparability": groups,
            "failure_taxonomy": counts(members[p["failed_slot_id"]]["failure_class"] for p in dd),
            "by_task": counts(p["task_id"] for p in dd),
            "failure_attempt_source": counts(
                members[p["failed_slot_id"]]["effective_source"] for p in dd
            ),
            "current_complete_bundles_for_both_members": sum(
                p["both_member_bundles_verified"] for p in dd
            ),
            "controlled_attribution_claims": 0,
        }
    return result


def candidates_for(ledgers: dict[str, Any], members: dict[str, Any]) -> list[dict[str, Any]]:
    associations: dict[str, list[dict[str, Any]]] = {}
    for name, ledger in ledgers.items():
        for pair in ledger["discordant_pairs"]:
            associations.setdefault(pair["failed_slot_id"], []).append(
                {
                    "comparison_id": name,
                    "pair_id": pair["pair_id"],
                    "comparability": pair["comparability"],
                    "both_member_bundles_verified": pair["both_member_bundles_verified"],
                }
            )
    candidates = []
    for slot_id, pairs in sorted(associations.items()):
        m = members[slot_id]
        if m["verifier"]["status"] != "FAILED":
            continue
        eligible = (
            m["complete_bundle_verified"] and m["verifier"]["stdout_independently_digest_verified"]
        )
        c = {
            "candidate_id": "kb4-candidate-" + digest_text(slot_id + m["manifest_digest"])[7:23],
            "slot_id": slot_id,
            "run_id": m["effective_run_id"],
            "cell_id": m["cell_id"],
            "task_id": m["task_id"],
            "task_version": m["task_version"],
            "repeat_index": m["repeat_index"],
            "evidence_identity": m["manifest_digest"],
            "failure_class": m["failure_class"],
            "verifier_failure_checks": m["verifier"]["failed_checks"],
            "verifier_score": m["verifier"]["report"]["score"],
            "diagnosis_level": "OBSERVED_FACT",
            "comparisons": pairs,
            "eligible_for_final_freeze_review": eligible,
            "suitability": "READY_FOR_REVIEW" if eligible else "HOLD_INTEGRITY_MISMATCH",
            "selected_as_final_badcase": False,
            "evidence_refs": [
                m["manifest_reference"],
                m["verifier"]["report_reference"],
                m["workspace"]["binding"]["reference"],
            ],
            "trace_event_ordinals": [
                e["ordinal"]
                for e in m["trace"]["events"]
                if e["type"] in {"FILE_CHANGE", "COMMAND_EXECUTION"}
            ],
            "value": (
                "Intact unchanged workspace and four failing header-normalization checks; no tool events support the public workspace-unavailable claim."
                if m["failure_class"] == FailureClass.NO_MODIFICATION.value
                else "Frozen empty-key rejection check fails while four retry-ledger checks pass; the bound source diff exposes accepted empty-key behavior."
            ),
            "limitations": [
                "Candidate only; no canonical BadCase or final-three selection is written.",
                "The failure's own bundle must be intact; comparison membership alone does not establish causal mechanism.",
            ],
        }
        if m["task_id"] == "core-python-deduplicate":
            c["limitations"].append(
                "The public instruction describes non-empty keys but does not explicitly prescribe empty-key rejection; the frozen verifier does. Preserve this specification limitation without changing the outcome."
            )
        if m["trace"]["status"] == "NOT_REPORTED":
            c["limitations"].append(
                "Direct execution has no agent trajectory; the explanation rests on the verifier and final source diff."
            )
        if not eligible:
            c["limitations"].append(
                "Missing compiled artifact(s) invalidate full workspace/verifier tree hashes. Independently matching stdout/source files do not make this candidate freeze-ready."
            )
        candidates.append(c)
    # More failing checks first (distinct unchanged-workspace failure), then available trace,
    # then stable task/cell/repeat identity. No score-selected retries or final selection.
    candidates.sort(
        key=lambda c: (
            not c["eligible_for_final_freeze_review"],
            -len(c["verifier_failure_checks"]),
            not bool(c["trace_event_ordinals"]),
            c["task_id"],
            c["cell_id"],
            c["repeat_index"],
        )
    )
    rank = 0
    for c in candidates:
        if c["eligible_for_final_freeze_review"]:
            rank += 1
            c["rank"] = rank
        else:
            c["rank"] = None
    return candidates


def build(root: Path, evidence_root: Path) -> dict[str, Any]:
    for reference, digest in FROZEN_INPUTS.items():
        require(_sha256_file(root / reference) == digest, "accepted frozen input changed")
    timeout = read_json(root / (TIMEOUT_OUTPUT + ".json"))
    validate_timeout(timeout)
    source_hashes = timeout["provenance"]["sources_sha256"]
    for reference, digest in source_hashes.items():
        if not reference.startswith("evidence:"):
            require(_sha256_file(root / reference) == digest, "K-B4.1 source changed")
    rows = _load_jsonl(root / (PREFIX + "analysis-dataset.jsonl"))
    manifest = read_json(root / (PREFIX + "analysis-dataset-manifest.json"))
    _validate_dataset(rows, manifest, _sha256_file(root / (PREFIX + "analysis-dataset.jsonl")))
    sources: dict[str, Any] = {}
    by_slot = {s["slot_id"]: s for s in timeout["slots"]}
    rows_by_slot = {s["slot_id"]: s for s in rows}
    required: set[str] = set()
    for p in timeout["pairs"].values():
        for pair in p["records"]:
            if discordance_kind(pair) in {"LEFT_PASS_RIGHT_FAIL", "LEFT_FAIL_RIGHT_PASS"}:
                required.update((pair["left_slot_id"], pair["right_slot_id"]))
    members = {
        slot_id: inspect_member(
            by_slot[slot_id], rows_by_slot[slot_id], root, evidence_root, source_hashes, sources
        )
        for slot_id in sorted(required)
    }
    ledgers = {}
    for name, left_cell, right_cell, intent in PAIR_DEFINITIONS:
        source = timeout["pairs"][name]
        ledger: dict[str, Any] = {
            "left_cell_id": left_cell,
            "right_cell_id": right_cell,
            "intent": intent,
            "frozen_summary": source["summary"],
            "discordant_pairs": [],
            "concordant_pairs": [],
            "excluded_pairs": [],
        }
        for pair in source["records"]:
            kind = discordance_kind(pair)
            record = dict(pair)
            if kind == "MISSING_CAPABILITY":
                ledger["excluded_pairs"].append(record)
                continue
            if kind == "CONCORDANT":
                ledger["concordant_pairs"].append(record)
                continue
            left, right = members[pair["left_slot_id"]], members[pair["right_slot_id"]]
            require(
                (
                    left["task_id"],
                    left["task_version"],
                    left["task_digest"],
                    left["repeat_index"],
                    left["paired_slot_identity"],
                )
                == (
                    right["task_id"],
                    right["task_version"],
                    right["task_digest"],
                    right["repeat_index"],
                    right["paired_slot_identity"],
                ),
                "exact pair identity drift",
            )
            failed = right if kind == "LEFT_PASS_RIGHT_FAIL" else left
            task_coverage = next(
                t
                for t in source["summary"]["effective"]["by_task"]
                if t["task_id"] == pair["task_id"]
            )
            record.update(
                pair_id=name + ":" + pair["paired_slot_identity"],
                direction=kind,
                task_version=left["task_version"],
                task_digest=left["task_digest"],
                language=left["language"],
                category=left["category"],
                failed_slot_id=failed["slot_id"],
                comparability=pair["effective"]["comparability"],
                strongest_supported_diagnosis_level="OBSERVED_FACT",
                both_member_bundles_verified=left["complete_bundle_verified"]
                and right["complete_bundle_verified"],
                frozen_comparable_pair_level_evidence=pair["effective"]["formal_comparable"],
                current_task_comparable_n=task_coverage["formal_comparable"],
                current_task_evidence_tier=evidence_tier(task_coverage["formal_comparable"]).value,
                formal_eligible=source["summary"]["effective"]["formal_eligible"],
                controlled_attribution_claimed=False,
                findings=[
                    {
                        "level": "OBSERVED_FACT",
                        "field": "effective_outcomes",
                        "value": {
                            "left": left["effective_outcome"],
                            "right": right["effective_outcome"],
                        },
                        "evidence_refs": [left["manifest_reference"], right["manifest_reference"]],
                    },
                    {
                        "level": "OBSERVED_FACT",
                        "field": "failed_member_taxonomy",
                        "value": {
                            "failure_class": failed["failure_class"],
                            "source_outcome": failed["source_outcome"],
                            "verifier_failed_checks": failed["verifier"]["failed_checks"],
                        },
                        "evidence_refs": [
                            failed["manifest_reference"],
                            failed["verifier"].get(
                                "report_reference", failed["trace"].get("reference")
                            ),
                        ],
                    },
                ],
                limitations=[
                    "Frozen comparability is retained exactly; current bundle audit is an additional evidence limitation, not a reclassification of capability.",
                    "Agent messages and shell exit status do not override verifier output; unobserved reasoning and longer-timeout outcomes remain unknown.",
                ],
            )
            ledger["discordant_pairs"].append(record)
        ledgers[name] = ledger
    summaries = summarize(ledgers, members)
    candidates = candidates_for(ledgers, members)
    for relative in (
        TIMEOUT_OUTPUT + ".json",
        TIMEOUT_OUTPUT + ".md",
        PREFIX + "analysis-dataset-manifest.json",
        PREFIX + "analysis-dataset.jsonl",
        PREFIX + "final-analysis.json",
        PREFIX + "final-analysis.md",
        PREFIX + "gpt-relay-attribution-source-audit.json",
        PREFIX + "gpt-relay-match-map.jsonl",
        "release/badcases.json",
        "docs/ANALYST.md",
        "docs/BADCASES.md",
        "docs/EXPERIMENT_STATISTICS.md",
        "docs/EVAL_METHODOLOGY_V2.md",
        "docs/EVAL_METHODOLOGY.md",
        "docs/FAIRNESS_CONTRACT.md",
        "src/harnesslab/diagnosis/models.py",
        "src/harnesslab/diagnosis/service.py",
        "src/harnesslab/harness_lane/models.py",
        "src/harnesslab/tasks/package.py",
        "src/harnesslab/tasks/models.py",
        "src/harnesslab/experiment/statistics.py",
        "scripts/analyze_kb4_discordant_pairs.py",
    ):
        sources[relative] = {
            "sha256": _sha256_file(root / relative),
            "binding": "CONTENT_ADDRESSED",
        }
    result = {
        "schema_version": 1,
        "phase": "K-B4.2",
        "base_commit": BASE_COMMIT,
        "status": "READY_FOR_BADCASE_FREEZE"
        if sum(c["eligible_for_final_freeze_review"] for c in candidates) >= 3
        else "BLOCKED_BY_INSUFFICIENT_DISCORDANT_EVIDENCE",
        "new_external_execution_required": False,
        "canonical_badcases_modified": False,
        "provenance": {
            "experiment_id": manifest["experiment_id"],
            "plan_digest": manifest["plan_digest"],
            "as_of": timeout["provenance"]["as_of"],
            "sources": dict(sorted(sources.items())),
            "reproduce": "uv run --locked python -m scripts.analyze_kb4_discordant_pairs --check",
        },
        "diagnosis_levels": {
            "OBSERVED_FACT": "Repository VERIFIED_FACT semantics: manifest, trace, verifier, or digest-bound diff observation.",
            "DIAGNOSTIC_ASSOCIATION": "Repository CORRELATION_ONLY / CONTROLLED_ABLATION_ASSOCIATION; no cause inferred.",
            "ATTRIBUTION_HYPOTHESIS": "Repository HYPOTHESIS; requires specified verifying/falsifying evidence.",
            "CONTROLLED_ATTRIBUTION": "No claim here. COMPARABLE is necessary, not sufficient for causal mechanism or a formal effect.",
        },
        "comparisons": ledgers,
        "summaries": summaries,
        "members": members,
        "badcase_candidates": candidates,
        "candidate_ranking_policy": "Eligible intact bundles first; more failing verifier checks, then structured tool/edit trace availability, then stable task/cell/repeat. All eligible cases remain candidates; none are final selections.",
        "reconciliation": {
            "comparison_memberships_not_pooled_as_a_treatment": True,
            "unique_inspected_slots": len(members),
            "unique_failed_slots": sum(
                m["effective_outcome"] == "capability_fail" for m in members.values()
            ),
            "workspace_digest_mismatches": sum(
                m["workspace"]["binding"]["status"] != "MATCH" for m in members.values()
            ),
            "verifier_tree_digest_mismatches": sum(
                m["verifier"]["binding"]["status"] == "INTEGRITY_MISMATCH" for m in members.values()
            ),
            "verifier_failure_candidates": len(candidates),
            "eligible_candidates": sum(c["eligible_for_final_freeze_review"] for c in candidates),
            "candidate_distinct_failure_signatures": len(
                {
                    (c["failure_class"], tuple(c["verifier_failure_checks"]))
                    for c in candidates
                    if c["eligible_for_final_freeze_review"]
                }
            ),
            "capability_denominators_unchanged": timeout["by_cell"],
        },
        "findings": [
            {
                "level": "DIAGNOSTIC_ASSOCIATION",
                "statement": "Execution-budget failures dominate discordances (16/18 Direct/medium; 32/34 medium/high). This describes selected discordant evidence, not the cause of the difference or a population failure rate.",
                "evidence_refs": ["summaries", TIMEOUT_OUTPUT + ".json"],
            },
            {
                "level": "DIAGNOSTIC_ASSOCIATION",
                "statement": "Two medium/high discordances are frozen COMPARABLE pair-level contrasts, both medium PASS/high FAIL. Repository semantics permit only controlled-ablation association. Passing medium bundles now have digest mismatches, further restricting full trajectory audit; no controlled causal claim is made.",
                "evidence_refs": ["comparisons/codex-gpt56-reasoning-effort"],
            },
            {
                "level": "ATTRIBUTION_HYPOTHESIS",
                "statement": "A public-contract interpretation gap may explain repeated empty-key acceptance. The instruction specifies behavior for non-empty keys without expressly requiring rejection of empty keys, while the frozen verifier requires ValueError. This does not establish the model's private reasoning or invalidate frozen scores.",
                "verify_or_falsify": "Review the frozen subject instruction, contract, bound source edits and public local-check commands. A causal test would require separately authorized explicit-contract control versus original-contract treatment; none is needed to freeze a factual verifier-failure case with this limitation.",
                "evidence_refs": [
                    "tasks/core-python-deduplicate/1.0.2/instruction.md",
                    "tasks/core-python-deduplicate/1.0.2/verifier/subject_probe.py",
                ],
            },
        ],
        "limitations": [
            "Every GPT direct/medium complete pair remains PARTIALLY_COMPARABLE; no Harness-uplift causal attribution is permitted.",
            "Only two of the 34 medium/high discordances are COMPARABLE; the other 32 must never contribute controlled claims. Formal eligibility remains false for both comparisons.",
            "Known current tree mismatches are retained without repair. Missing .pyc/.class paths match recorded inventories, but their absence is not proof of when or why loss occurred; no binary reconstruction is attempted.",
            "Verifier stdout has its own immutable digest binding even when a containing verifier tree is incomplete; report-level facts remain distinguishable from complete-bundle eligibility.",
            "The four candidate records provide only two distinct verifier failure signatures. One candidate is held for integrity; do not pretend three distinct engineering mechanisms have been found.",
            "Direct lacks agent traces; Codex streams lack complete provider timing and private reasoning. Five physical primary timeout facts remain unknown under K-B4.1.",
            "No compile/build failure is established among these verifier-backed failures. Nonzero git commands are ancillary tool facts, not causes of the behavioral failure. Issued self-check syntax does not prove checks actually passed.",
            "New external execution is not required for the three intact candidates. The integrity-held candidate needs exact original artifact recovery, not a replacement experiment. Canonical final BadCases remain unchanged.",
        ],
        "external_execution": {"provider": 0, "harness": 0, "judge": 0, "matrix": 0},
    }
    validate(result)
    return result


def validate(result: dict[str, Any]) -> None:
    require(result["schema_version"] == 1 and result["phase"] == "K-B4.2", "schema mismatch")
    require(
        result["summaries"] == summarize(result["comparisons"], result["members"]), "summary drift"
    )
    require(
        result["badcase_candidates"] == candidates_for(result["comparisons"], result["members"]),
        "candidate drift",
    )
    for ledger in result["comparisons"].values():
        all_pairs = (
            ledger["discordant_pairs"] + ledger["concordant_pairs"] + ledger["excluded_pairs"]
        )
        require(len(all_pairs) == 90, "pair coverage drift")
        require(
            len({(p["task_id"], p["repeat_index"]) for p in all_pairs}) == 90,
            "duplicate task/repeat",
        )
        for p in ledger["discordant_pairs"]:
            require(discordance_kind(p) == p["direction"], "false discordance")
            require(p["comparability"] == p["effective"]["comparability"], "comparability upgraded")
            require(not p["controlled_attribution_claimed"], "unsupported controlled attribution")
            for side in ("left", "right"):
                m = result["members"][p[f"{side}_slot_id"]]
                require(
                    (
                        m["task_id"],
                        m["task_version"],
                        m["task_digest"],
                        m["repeat_index"],
                        m["paired_slot_identity"],
                        m["cell_id"],
                    )
                    == (
                        p["task_id"],
                        p["task_version"],
                        p["task_digest"],
                        p["repeat_index"],
                        p["paired_slot_identity"],
                        ledger[f"{side}_cell_id"],
                    ),
                    "pair member identity drift",
                )
                require(
                    m["effective_outcome"] == p["effective"][f"{side}_outcome"],
                    "pair outcome drift",
                )
            require(all(f["level"] in LEVELS for f in p["findings"]), "unknown diagnosis level")
        require(
            all(discordance_kind(p) == "MISSING_CAPABILITY" for p in ledger["excluded_pairs"]),
            "exclusion drift",
        )
        require(
            all(discordance_kind(p) == "CONCORDANT" for p in ledger["concordant_pairs"]),
            "concordance drift",
        )
    for m in result["members"].values():
        require(m["failure_class"] == classify_failure(m), "failure taxonomy drift")
        require(
            m["complete_bundle_verified"]
            == (
                m["workspace"]["binding"]["status"] == "MATCH"
                and m["verifier"]["binding"]["status"] in {"MATCH", "NOT_APPLICABLE"}
            ),
            "bundle eligibility drift",
        )
        if m["verifier"]["report"]:
            VerifierReport.model_validate(m["verifier"]["report"])
    require(
        all(
            f["level"] in LEVELS and f["level"] != "CONTROLLED_ATTRIBUTION"
            for f in result["findings"]
        ),
        "unsupported finding level",
    )
    require(not result["canonical_badcases_modified"], "final BadCases are out of scope")
    require(all(v == 0 for v in result["external_execution"].values()), "real execution forbidden")
    json.dumps(result, allow_nan=False)


def markdown(result: dict[str, Any]) -> str:
    lines = [
        "# K-B4.2 Discordant pair failure attribution",
        "",
        f"**{result['status']}**",
        "",
        "Analysis only. Exact task/version/repeat and paired-slot identity determine discordance. Frozen outcomes, primary/recovery evidence, and comparability are retained. No final BadCases are selected or frozen.",
        "",
        "## Counts and eligibility",
        "",
        "| Comparison | Complete | Left PASS/right FAIL | Left FAIL/right PASS | Discordances by comparable/partial/not comparable | Missing (timeout-affected) |",
        "|---|---:|---:|---:|---|---:|",
    ]
    for name, _, _, _ in PAIR_DEFINITIONS:
        s = result["summaries"][name]
        g = s["by_comparability"]
        lines.append(
            f"| `{name}` | {s['effective_complete_pairs']}/90 | {s['direction'].get('LEFT_PASS_RIGHT_FAIL', 0)} | {s['direction'].get('LEFT_FAIL_RIGHT_PASS', 0)} | {g['COMPARABLE']['discordant_pairs']}/{g['PARTIALLY_COMPARABLE']['discordant_pairs']}/{g['NOT_COMPARABLE']['discordant_pairs']} | {s['excluded_missing_pairs']} ({s['timeout_affected_missing_pairs']}) |"
        )
    lines += [
        "",
        "Direct/medium: all 82 complete pairs are PARTIALLY_COMPARABLE. Medium/high: 42 complete pairs are COMPARABLE and 41 NOT_COMPARABLE. Among discordances, the two comparable cases both favor medium; the 32 not-comparable cases split 23 medium-pass/high-fail and 9 medium-fail/high-pass. Both comparisons retain formal eligibility=false. Missing pairs are exclusions, never capability failures.",
        "",
        "## Evidence-supported diagnosis",
        "",
        "- **OBSERVED_FACT:** Direct/medium has 16 execution-budget failures and 2 verifier-backed failures. Medium/high has 32 execution-budget failures and 2 verifier-backed failures. All budget failures retain the native `Timeout` class with CAPABILITY scope and `execution_budget_exhausted` subtype; they are not infrastructure outcomes or eligible verifier-backed BadCases.",
        "- **OBSERVED_FACT:** High `core-java-settings-merge`, repeat 0, left its workspace unchanged. Its verifier failed `normalizes`, `preserves-order`, `duplicate-rejected`, and `invalid-rejected` (score 0.2). The trace has thread/turn start, one public agent message, and turn completion; no commands or edits. The agent's workspace-unavailable statement is an unverified self-report, not an established runtime cause. Native taxonomy: `No Modification`.",
        "- **OBSERVED_FACT:** Direct `core-python-deduplicate` repeat 0, medium repeat 4, and high repeat 2 each fail only `empty-key-rejected` (score 0.8). Their bound source edits accept empty keys; four other ledger checks pass. Native taxonomy: `Test Failure`. Two Codex traces issue local assertions accepting empty keys, but shell exit zero and public self-report cannot prove every local assertion ran or passed.",
        "- **DIAGNOSTIC_ASSOCIATION:** Budget exhaustion dominates selected discordances. This is not proof that timeout, relay waiting, or reasoning effort caused the observed capability difference.",
        "- **ATTRIBUTION_HYPOTHESIS:** Empty-key acceptance may reflect a specification interpretation gap: the public instruction defines non-empty-key behavior but does not expressly require empty-key rejection, while the frozen verifier does. Frozen instruction, code edits, and public check commands can corroborate the observation; causal verification would need a separately authorized explicit-contract control. No private reasoning is inferred and no score is changed.",
        "",
        "## Controlled pair-level evidence and integrity limits",
        "",
        "The two frozen COMPARABLE discordances are medium/high `core-java-settings-merge` repeat 0 and `core-python-deduplicate` repeat 2. They support recorded pair-level contrasts under the same operator-trusted route, with reasoning effort as the declared treatment. Repository semantics limit this to controlled-ablation association, not proof of a mechanism or a formal reasoning-effort effect. Their passing medium workspace/verifier bundles are currently incomplete, further limiting trajectory audit. **CONTROLLED_ATTRIBUTION claims: 0.** Partial and not-comparable pairs contribute none.",
        "",
        f"All {result['reconciliation']['unique_inspected_slots']} unique discordant member manifests and available trace files were digest-checked. Of these, {result['reconciliation']['workspace_digest_mismatches']} workspace trees and {result['reconciliation']['verifier_tree_digest_mismatches']} verifier trees fail their recorded directory digests. Recorded missing files are compiled `.pyc`/`.class` artifacts; available source-file bindings and verifier stdout digests still match. This does not establish when or why the files disappeared. Missing files are neither recreated nor ignored in complete-bundle eligibility. The machine-readable ledger preserves every mismatch separately from immutable capability/comparability results.",
        "",
        "## Ranked BadCase candidates (not final selections)",
        "",
        "| Review rank | Candidate | Cell/task/repeat | Verifier finding | Suitability |",
        "|---|---|---|---|---|",
    ]
    for c in result["badcase_candidates"]:
        lines.append(
            f"| {c['rank'] or 'Held'} | `{c['candidate_id']}` | `{c['cell_id']}` / `{c['task_id']}` / {c['repeat_index']} | {', '.join(c['verifier_failure_checks'])} | `{c['suitability']}` |"
        )
    lines += [
        "",
        "Three candidates have intact failure bundles; the medium Python candidate is held because compiled bytecode is absent from its workspace/verifier trees. Ranking favors the distinct unchanged-workspace case, then structured edit/tool evidence. The eligible candidates span only two failure signatures; the two Python cases are related, not three distinct mechanisms. Direct's explanation uses verifier and source diff because it has no agent trace. All Python cases retain the public-contract limitation above.",
        "",
        "**No new external execution is required before factual BadCase review/freezing of eligible evidence.** The held case would need exact original artifact recovery, not a replacement run. This candidate set does not select the final three or modify `release/badcases.json`.",
        "",
        "## Reproduction and boundaries",
        "",
        "```sh",
        result["provenance"]["reproduce"],
        "```",
        "",
        "The JSON records source hashes, all discordances/concordances/exclusions, per-member verifier checks, trace ordinals/command hashes, source diffs, immutable primary/recovery identities, comparability reasons, task evidence tiers, hypotheses, candidate eligibility, and reconciliation. `--check` rebuilds from persisted artifacts and compares JSON/Markdown byte for byte. Individual files can be audited even where directory completeness is limited.",
        "",
    ]
    lines.extend(f"- {x}" for x in result["limitations"])
    lines += [
        "",
        "**NOT RUN:** provider/Harness/Judge/Matrix calls (all 0), real ablation, final BadCase freeze, final K-B4 Attribution Report, K-C, Full Release CI, and qualification regeneration.",
        "",
    ]
    return "\n".join(lines)


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
    result = build(args.repo_root.resolve(), args.evidence_root.resolve())
    for suffix, content in (
        (".json", json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"),
        (".md", markdown(result)),
    ):
        path = args.repo_root / (OUTPUT + suffix)
        if args.check:
            require(path.read_text() == content, f"artifact drift: {path.name}")
        else:
            path.write_text(content)
    print(result["status"])


if __name__ == "__main__":
    main()
