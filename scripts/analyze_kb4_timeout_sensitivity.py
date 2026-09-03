# Reader-facing Markdown strings preserve complete sentences, as in the final V6 analysis.
# ruff: noqa: E501, RUF001

"""Read-only V6 timeout sensitivity; no database, planner, verifier, or provider execution."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any

import yaml

from harnesslab.comparability.engine import ComparabilityEngine, capability_pair_eligible
from harnesslab.comparability.manifest import facts_from_manifest
from harnesslab.comparability.models import (
    ComparabilityIntent,
    ComparisonFacts,
    canonical_digest,
)
from harnesslab.experiment.outcomes import normalize_manifest_evidence
from harnesslab.registry.seeds import build_registry_catalog
from harnesslab.release.v6 import v6_budget_contract
from scripts.analyze_formal_matrix_final import (
    _load_json_object,
    _load_jsonl,
    _sha256_file,
    _validate_dataset,
)
from scripts.audit_gpt_relay_attribution_sources import (
    GPT_CELLS,
    _validate_frozen_inputs,
)

PREFIX = "release/core-real-matrix-v6-"
OUTPUT = "release/kb4-gpt-codex-timeout-sensitivity"
CAPABILITY = {"capability_pass", "capability_fail"}
KINDS = ("primary", "recovery")
PAIR_DEFINITIONS = (
    ("gpt56-relay-direct-vs-codex", GPT_CELLS[0], GPT_CELLS[1], "HARNESS_UPLIFT"),
    ("codex-gpt56-reasoning-effort", GPT_CELLS[1], GPT_CELLS[2], "CONTROLLED_ABLATION"),
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def counts(values: Any) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def timeout_fact(manifest: dict[str, Any] | None, source: str) -> str:
    """Observe timeout independently of the immutable infrastructure/capability label."""
    if manifest is None:
        return "NOT_VERIFIED"
    if (
        manifest.get("timed_out") is True
        or manifest.get("provider_failure") == "timeout"
        or (manifest.get("provider_error") or {}).get("category") == "timeout"
        or source in {"harness_error:timeout", "harness_error:execution_budget_exhausted"}
    ):
        return "OBSERVED"
    return "NOT_OBSERVED"


def attempt_projection(
    row: dict[str, Any], kind: str, manifest: dict[str, Any] | None
) -> dict[str, Any]:
    source = row[f"{kind}_source_outcome"]
    outcome = row[f"{kind}_normalized_outcome"]
    error = (manifest or {}).get("provider_error") or {}
    profile = (manifest or {}).get("profile") or {}
    generation = (manifest or {}).get("generation_settings") or {}
    fact = timeout_fact(manifest, source)
    duration = (manifest or {}).get("duration_ms")
    basis = "harness_process_elapsed_ms"
    if row["cell_id"] == GPT_CELLS[0]:
        duration = error.get("latency_ms")
        if duration is None:
            duration = ((manifest or {}).get("provider_result") or {}).get("latency_ms")
        basis = "provider_invocation_latency_ms"
    limit = profile.get("execution_timeout_seconds", generation.get("request_timeout_seconds"))
    return {
        "attempt_kind": kind,
        "normalized_outcome": outcome,
        "source_outcome": source,
        "timeout_fact": fact,
        "timeout_infrastructure": fact == "OBSERVED" and outcome == "infra_failure",
        "execution_budget_capability_failure": (
            source == "harness_error:execution_budget_exhausted" and outcome == "capability_fail"
        ),
        "provider_failure": (manifest or {}).get("provider_failure"),
        "harness_failure": (manifest or {}).get("harness_failure"),
        "backend_failure": (manifest or {}).get("backend_failure"),
        "timed_out": (manifest or {}).get("timed_out"),
        "timeout_phase": error.get("timeout_phase"),
        "read_timeout_stage": error.get("read_timeout_stage"),
        "phase_interpretation": (
            "outer_harness_process; provider/tool phase not localized"
            if fact == "OBSERVED" and profile
            else error.get("timeout_phase")
        ),
        "execution_limit_seconds": limit,
        "duration_ms": duration,
        "duration_basis": basis,
        "dataset_duration_ms": row[f"{kind}_duration_ms"],
        "boundary_delta_ms": duration - limit * 1000 if duration is not None and limit else None,
        "manifest_available": manifest is not None,
        "run_id": (manifest or {}).get("run_id"),
        "requested_model": (manifest or {}).get("requested_model"),
        "observed_model": (manifest or {}).get("observed_model"),
        "observed_model_status": (manifest or {}).get("observed_model_status"),
        "resource_budget": (manifest or {}).get("resource_budget"),
        "comparison_facts": None,
    }


def comparison_controls(root: Path, control: dict[str, Any]) -> dict[str, Any]:
    """Recover only registry controls whose binding matches the persisted V6 digest."""
    catalog = build_registry_catalog(root, {})
    providers = {p.profile_id: p for p in catalog.provider_model_profiles}
    profiles = {p.profile_id: (h, p) for h in catalog.harnesses for p in h.profiles}
    result = {}
    for c in control["cells"]:
        if c["cell_id"] not in GPT_CELLS:
            continue
        provider = providers[c["provider_profile_id"]]
        harness, profile = profiles[c["harness_profile_id"]]
        require(provider.profile_identity == c["provider_profile_identity"], "provider drift")
        binding = {
            "cell_id": c["cell_id"],
            "requested_model": provider.requested_model,
            "provider_route": provider.provider_route_identity,
            "profile_identity": canonical_digest(
                {
                    "provider_profile_identity": provider.profile_identity,
                    "harness_id": harness.harness_id,
                    "harness_version": harness.version,
                    "profile_reference": profile.profile_reference,
                }
            ),
            "harness": harness.harness_id,
            "harness_version": harness.version,
            "harness_config_identity": profile.harness_config_identity,
            "reasoning_effort": profile.reasoning_effort or provider.reasoning_effort,
            "runner_contract": harness.runner_contract,
            "credential_reference": provider.credential_reference,
        }
        require(canonical_digest(binding) == c["execution_binding_identity"], "binding drift")
        result[c["cell_id"]] = {"frozen_cell": c, "digest_verified_binding": binding}
    return result


def assess_pair(left: dict[str, Any], right: dict[str, Any], intent: str) -> dict[str, Any]:
    if left["comparison_facts"] is None or right["comparison_facts"] is None:
        return {
            "status": "NOT_COMPARABLE",
            "eligible": False,
            "reasons": [{"code": "MANIFEST_UNAVAILABLE", "severity": "BLOCKING"}],
        }
    facts = [ComparisonFacts.model_validate(a["comparison_facts"]) for a in (left, right)]
    if intent == "CONTROLLED_ABLATION":
        facts = [
            f.model_copy(update=a["ablation_controls"])
            for f, a in zip(facts, (left, right), strict=True)
        ]
    report = ComparabilityEngine().assess(
        facts[0],
        facts[1],
        intent=ComparabilityIntent(intent),
    )
    return {
        "status": report.status.value,
        "eligible": capability_pair_eligible(report),
        "report_digest": canonical_digest(report.model_dump(mode="json")),
        "reasons": [r.model_dump(mode="json") for r in report.reasons],
    }


def pair_views(slots: list[dict[str, Any]]) -> dict[str, Any]:
    index = {(s["cell_id"], s["task_id"], s["repeat_index"]): s for s in slots}
    require(len(index) == len(slots), "duplicate cell/task/repeat")
    result = {}
    for name, left_cell, right_cell, intent in PAIR_DEFINITIONS:
        keys = sorted((task, repeat) for cell, task, repeat in index if cell == left_cell)
        require(set(keys) == {(t, r) for c, t, r in index if c == right_cell}, "unmatched keys")
        records = []
        for task, repeat in keys:
            left, right = index[left_cell, task, repeat], index[right_cell, task, repeat]
            require(left["paired_slot_identity"] == right["paired_slot_identity"], "pair drift")
            require(left["task_digest"] == right["task_digest"], "task identity drift")
            record: dict[str, Any] = {
                "task_id": task,
                "repeat_index": repeat,
                "paired_slot_identity": left["paired_slot_identity"],
                "left_slot_id": left["slot_id"],
                "right_slot_id": right["slot_id"],
                "unresolved_timeout_slots": [
                    s["slot_id"] for s in (left, right) if s["timeout_affected_unresolved"]
                ],
            }
            for view in ("primary", "effective"):
                a, b = (
                    s[s["effective_source"] if view == "effective" else "primary"]
                    for s in (left, right)
                )
                complete = all(x["normalized_outcome"] in CAPABILITY for x in (a, b))
                assessment = assess_pair(a, b, intent)
                record[view] = {
                    "left_attempt_kind": a["attempt_kind"],
                    "right_attempt_kind": b["attempt_kind"],
                    "left_outcome": a["normalized_outcome"],
                    "right_outcome": b["normalized_outcome"],
                    "capability_complete": complete,
                    "exploratory_eligible": complete and assessment["eligible"],
                    "formal_comparable": complete and assessment["status"] == "COMPARABLE",
                    "comparability": assessment,
                }
            records.append(record)
        summary: dict[str, Any] = {
            "planned": len(records),
            "intent": intent,
            "left_cell": left_cell,
            "right_cell": right_cell,
        }
        for view in ("primary", "effective"):
            per_task = []
            for task in sorted({r["task_id"] for r in records}):
                task_rows = [r[view] for r in records if r["task_id"] == task]
                per_task.append(
                    {
                        "task_id": task,
                        **{
                            k: sum(r[k] for r in task_rows)
                            for k in (
                                "capability_complete",
                                "exploratory_eligible",
                                "formal_comparable",
                            )
                        },
                    }
                )
            summary[view] = {
                **{
                    k: sum(r[view][k] for r in records)
                    for k in ("capability_complete", "exploratory_eligible", "formal_comparable")
                },
                "complete_pair_comparability": {
                    state: sum(
                        r[view]["capability_complete"]
                        and r[view]["comparability"]["status"] == state
                        for r in records
                    )
                    for state in ("COMPARABLE", "PARTIALLY_COMPARABLE", "NOT_COMPARABLE")
                },
                "tasks_with_five_complete_pairs": sum(
                    t["capability_complete"] == 5 for t in per_task
                ),
                "tasks_with_five_formal_pairs": sum(t["formal_comparable"] == 5 for t in per_task),
                "formal_eligible": all(t["formal_comparable"] >= 5 for t in per_task),
                "by_task": per_task,
            }
        summary["timeout_affected_unavailable_pairs"] = sum(
            bool(r["unresolved_timeout_slots"]) for r in records
        )
        summary["other_unavailable_pairs"] = sum(
            not r["effective"]["capability_complete"] and not r["unresolved_timeout_slots"]
            for r in records
        )
        summary["pairs_restored_by_all_authorized_recovery"] = sum(
            r["effective"]["capability_complete"] and not r["primary"]["capability_complete"]
            for r in records
        )
        summary["effective_complete_pairs_with_primary_infra_timeout_history"] = sum(
            r["effective"]["capability_complete"]
            and any(
                index[cell, r["task_id"], r["repeat_index"]]["primary"]["timeout_infrastructure"]
                for cell in (left_cell, right_cell)
            )
            for r in records
        )
        result[name] = {"summary": summary, "records": records}
    return result


def group_summary(slots: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "planned": len(slots),
        "recorded_physical_primary_attempts": sum(s["primary_attempt_count"] for s in slots),
        "extra_primary_attempts_without_selected_manifest": sum(
            s["unobserved_extra_primary_attempts"] for s in slots
        ),
        "selected_primary_manifest_unavailable": sum(
            not s["primary"]["manifest_available"] for s in slots
        ),
    }
    for kind in KINDS:
        attempts = [s[kind] for s in slots if s[kind] is not None]
        timeout = [a for a in attempts if a["timeout_fact"] == "OBSERVED"]
        summary[kind] = {
            "attempts": len(attempts),
            "outcomes": counts(a["normalized_outcome"] for a in attempts),
            "source_outcomes": counts(a["source_outcome"] for a in attempts),
            "timeout_infrastructure": sum(a["timeout_infrastructure"] for a in attempts),
            "execution_budget_capability_failures": sum(
                a["execution_budget_capability_failure"] for a in attempts
            ),
            "timeout_facts": counts(a["timeout_fact"] for a in attempts),
            "failure_categories": counts(
                a["harness_failure"] or a["provider_failure"] or a["source_outcome"]
                for a in attempts
                if a["normalized_outcome"] == "infra_failure"
            ),
            "timeout_duration_by_class": {},
        }
        for label, field in (
            ("infrastructure", "timeout_infrastructure"),
            ("capability", "execution_budget_capability_failure"),
        ):
            aa = [a for a in timeout if a[field]]
            dd = [a["duration_ms"] for a in aa if a["duration_ms"] is not None]
            summary[kind]["timeout_duration_by_class"][label] = {
                "observations": len(aa),
                "duration_available": len(dd),
                "min_ms": min(dd) if dd else None,
                "median_ms": median(dd) if dd else None,
                "max_ms": max(dd) if dd else None,
                "within_1000ms_of_configured_boundary": sum(
                    a["boundary_delta_ms"] is not None and abs(a["boundary_delta_ms"]) <= 1000
                    for a in aa
                ),
            }
    effective = counts(s["effective_outcome"] for s in slots)
    affected = [s for s in slots if s["primary"]["timeout_infrastructure"]]
    summary["effective"] = {
        "outcomes": effective,
        "capability_n": sum(effective.get(k, 0) for k in CAPABILITY),
        "infra_count": effective.get("infra_failure", 0),
        "missing_count": sum(s["effective_outcome"] not in CAPABILITY for s in slots),
        "cancelled": effective.get("cancelled", 0),
        "recovery_attempt_count": sum(s["recovery"] is not None for s in slots),
    }
    summary["timeout_affected_recovery"] = {
        "primary_infra_timeout_slots": len(affected),
        "entered_recovery": sum(s["recovery"] is not None for s in affected),
        "recovery_outcomes": counts(
            s["recovery"]["normalized_outcome"] for s in affected if s["recovery"] is not None
        ),
        "recovery_source_outcomes": counts(
            s["recovery"]["source_outcome"] for s in affected if s["recovery"] is not None
        ),
        "unresolved": sum(s["timeout_affected_unresolved"] for s in slots),
    }
    return summary


def build(root: Path, evidence_root: Path) -> dict[str, Any]:
    sources: dict[str, str] = {}

    def read(path: Path, expected: str | None = None) -> dict[str, Any]:
        digest = _sha256_file(path)
        require(expected is None or expected == digest, f"source digest mismatch: {path.name}")
        reference = (
            path.relative_to(root).as_posix()
            if path.is_relative_to(root)
            else "evidence:" + path.relative_to(evidence_root).as_posix()
        )
        sources[reference] = digest
        return _load_json_object(path)

    rows = _load_jsonl(root / (PREFIX + "analysis-dataset.jsonl"))
    manifest = read(root / (PREFIX + "analysis-dataset-manifest.json"))
    control = read(root / (PREFIX + "control.json"))
    checkpoint = read(root / (PREFIX + "checkpoint-630.json"))
    final = read(root / (PREFIX + "final-analysis.json"))
    audit = read(root / (PREFIX + "gpt-relay-attribution-source-audit.json"))
    validation = _validate_dataset(
        rows, manifest, _sha256_file(root / (PREFIX + "analysis-dataset.jsonl"))
    )
    _validate_frozen_inputs(root, rows, manifest, control)
    controls = comparison_controls(root, control)
    original_root = Path(checkpoint["artifact_roots"]["matrix"])
    slots = []
    for row in rows:
        if row["cell_id"] not in GPT_CELLS:
            continue
        task_path = root / row["task_package_path"] / "task.yaml"
        sources[task_path.relative_to(root).as_posix()] = _sha256_file(task_path)
        task = yaml.safe_load(task_path.read_text())
        require(
            task["id"] == row["task_id"] and task["version"] == row["task_version"], "task drift"
        )
        slot = {
            k: row[k]
            for k in (
                "slot_id",
                "slot_order",
                "cell_id",
                "task_id",
                "task_digest",
                "task_version",
                "repeat_index",
                "paired_slot_identity",
                "primary_attempt_count",
                "effective_source",
                "effective_outcome",
                "infra_recovery_exhausted",
                "primary_status",
            )
        }
        slot.update(
            language=task["metadata"].get("language"), category=task["metadata"].get("category")
        )
        slot["task_budget"] = task["budget"]
        slot["verifier_timeout_seconds"] = task["verifier"]["timeout_seconds"]
        slot["unobserved_extra_primary_attempts"] = max(0, row["primary_attempt_count"] - 1)
        for kind in KINDS:
            if kind == "recovery" and not row["recovery_attempted"]:
                slot[kind] = None
                continue
            path_value = row[
                "artifact_manifest_path" if kind == "primary" else "recovery_manifest_path"
            ]
            raw = None
            reference = None
            if path_value:
                relative = Path(path_value).relative_to(original_root)
                path = evidence_root / relative
                digest = row["evidence_digest" if kind == "primary" else "recovery_manifest_digest"]
                require(isinstance(digest, str), "manifest digest unavailable")
                raw = read(path, digest)
                reference = "evidence:" + relative.as_posix()
                normalized = normalize_manifest_evidence(raw)
                require(
                    normalized.outcome.value == row[f"{kind}_normalized_outcome"], "outcome drift"
                )
                require(
                    normalized.source_taxonomy == row[f"{kind}_source_outcome"], "taxonomy drift"
                )
            attempt = attempt_projection(row, kind, raw)
            attempt["manifest_reference"] = reference
            if raw is not None:
                facts = facts_from_manifest(raw, verifier_control_identity=row["verifier_identity"])
                binding = controls[row["cell_id"]]["digest_verified_binding"]
                require(facts.requested_model == binding["requested_model"], "model drift")
                require(facts.provider_route == binding["provider_route"], "route drift")
                require(
                    facts.harness_profile_identity == binding["profile_identity"], "profile drift"
                )
                require(
                    raw.get("plan_harness_config_identity") == binding["harness_config_identity"],
                    "config drift",
                )
                require(facts.task_digest == row["task_digest"], "manifest task drift")
                require(facts.reasoning_effort == binding["reasoning_effort"], "reasoning drift")
                require(attempt["execution_limit_seconds"] == 180, "timeout drift")
                # Same supplementation as experiment/report.py, using V6's persisted binding
                # and source-defined envelope; never fill observed model or executed verifier.
                facts = facts.model_copy(
                    update={
                        "resource_envelope_identity": canonical_digest(
                            {
                                "task_budget_identity": facts.budget_identity,
                                "request_timeout_seconds": controls[row["cell_id"]]["frozen_cell"][
                                    "request_timeout_seconds"
                                ],
                                "max_output_tokens": controls[row["cell_id"]]["frozen_cell"][
                                    "max_output_tokens"
                                ],
                            }
                        ),
                    }
                )
                attempt["comparison_facts"] = facts.model_dump(mode="json")
                attempt["ablation_controls"] = {
                    "runner_contract": binding["runner_contract"],
                    "credential_reference_identity": binding["credential_reference"],
                }
            slot[kind] = attempt
        if row["recovery_attempted"]:
            side = read(
                evidence_root / Path(row["recovery_sidecar_path"]).relative_to(original_root)
            )
            for key in ("slot_id", "cell_id", "recovery_attempt_identity", "recovery_run_id"):
                require(side[key] == row[key], "recovery linkage drift")
            require(
                side["manifest_digest"] == row["recovery_manifest_digest"], "recovery digest drift"
            )
            require(
                side["original_attempt_identity"]
                == f"{row['run_id']}-a{row['primary_attempt_count']}",
                "original attempt drift",
            )
            slot["recovery_link"] = {
                k: side[k]
                for k in (
                    "original_attempt_identity",
                    "recovery_attempt_identity",
                    "recovery_run_id",
                )
            }
        slot["timeout_affected_unresolved"] = row["effective_outcome"] not in CAPABILITY and any(
            slot[k] and slot[k]["timeout_infrastructure"] for k in KINDS
        )
        slots.append(slot)
    for source_relative in (
        PREFIX + "analysis-dataset.jsonl",
        PREFIX + "final-analysis.md",
        PREFIX + "gpt-relay-attribution-source-audit.md",
        PREFIX + "gpt-relay-match-map.jsonl",
        "docs/EVAL_METHODOLOGY_V2.md",
        "docs/EXPERIMENT_STATISTICS.md",
        "docs/HARNESS_COMPARABILITY.md",
        "src/harnesslab/release/v6.py",
        "src/harnesslab/registry/seeds.py",
        "src/harnesslab/comparability/engine.py",
        "src/harnesslab/comparability/manifest.py",
        "src/harnesslab/experiment/report.py",
        "src/harnesslab/comparability/models.py",
        "src/harnesslab/harness_lane/models.py",
        "scripts/analyze_formal_matrix_final.py",
        "scripts/audit_gpt_relay_attribution_sources.py",
        "src/harnesslab/experiment/outcomes.py",
        "src/harnesslab/harness_lane/trace.py",
        "src/harnesslab/harness_lane/docker_backend.py",
        "src/harnesslab/harness_lane/adapter.py",
        "src/harnesslab/model_lane/providers.py",
        "scripts/analyze_kb4_timeout_sensitivity.py",
    ):
        sources[source_relative] = _sha256_file(root / source_relative)
    result = {
        "schema_version": 1,
        "comparison_contract": "HARNESS_UPLIFT and CONTROLLED_ABLATION via unmodified ComparabilityEngine and experiment/report.py supplementation; complete pairs are not automatically eligible",
        "status": "READY_FOR_DISCORDANT_PAIR_ATTRIBUTION",
        "counterfactual_status": "INSUFFICIENT_EVIDENCE_FOR_COUNTERFACTUAL",
        "new_controlled_execution_required_before_bounded_attribution": False,
        "provenance": {
            "experiment_id": control["experiment_id"],
            "plan_digest": control["plan_digest"],
            "as_of": checkpoint["recorded_at"],
            "sources_sha256": dict(sorted(sources.items())),
            "reproduce": "uv run --locked python -m scripts.analyze_kb4_timeout_sensitivity --check",
            "evidence_root_default": str(original_root),
        },
        "dataset_validation": validation,
        "scientific_controls": checkpoint["scientific_controls"],
        "campaign_reconciliation": {
            "primary": checkpoint["primary"],
            "recovery": checkpoint["recovery"],
            "effective": checkpoint["effective"],
        },
        "controls": controls,
        "plan_budget_contract_source_defined": v6_budget_contract().model_dump(mode="json"),
        "by_cell": {c: group_summary([s for s in slots if s["cell_id"] == c]) for c in GPT_CELLS},
        "by_task": {
            t: {
                c: group_summary([s for s in slots if s["cell_id"] == c and s["task_id"] == t])
                for c in GPT_CELLS
            }
            for t in sorted({s["task_id"] for s in slots})
        },
        "by_language": {
            t: {
                c: group_summary([s for s in slots if s["cell_id"] == c and s["language"] == t])
                for c in GPT_CELLS
            }
            for t in sorted({s["language"] for s in slots})
        },
        "by_category": {
            t: {
                c: group_summary([s for s in slots if s["cell_id"] == c and s["category"] == t])
                for c in GPT_CELLS
            }
            for t in sorted({s["category"] for s in slots})
        },
        "pairs": pair_views(slots),
        "slots": slots,
        "prior_comparison_conclusions": final["paired_comparisons"],
        "relay_source_audit_decision": audit["attribution_decision"],
        "external_execution": {"provider": 0, "harness": 0, "judge": 0, "matrix": 0},
        "limitations": [
            "Only digest-bound selected authoritative attempts are counted. Four extra physical primary attempts (Direct 1, medium 2, high 1) have no selected manifest, and one high selected primary manifest was rejected for control mismatch. Thus 269 of 274 recorded physical primaries have authoritative manifests; timeout facts for the other five are NOT_VERIFIED. Counts are observed minima, not a complete physical-attempt census.",
            "Known timeout-related censoring is historical association: two unresolved slots now end in protocol_error, not a timeout category. It is not proof that timeout caused missingness or capability differences.",
            "Trace-proven execution_budget_exhausted remains capability failure under the frozen budget; it is not missingness and is never removed or recovered for sensitivity.",
            "The 300-second plan wall-time contract, 90-second task budget, 180-second provider request timeout, 180-second Codex outer process deadline, and 15-second verifier timeout have distinct scopes. Recorded provider metadata does not prove an enforced Codex-wide output-token cap.",
            "Direct HTTP timeout is a transport phase timeout, not the Codex outer process deadline. Near-boundary duration (absolute difference <=1000ms) is a descriptive diagnostic, not a significance test or a timeout detector.",
            "Formal eligibility uses five COMPARABLE capability pairs per task. Complete pairs alone do not establish comparability; prior effect labels are descriptive frozen system/configuration observations.",
            "No longer-timeout treatment, complete Codex provider-call timing, or random missingness evidence exists. Longer-budget pass outcomes, relay causation, and reasoning-caused timeouts cannot be concluded.",
            "Bounded later review can proceed with these limitations; this status does not authorize that next phase or any real execution.",
        ],
    }
    validate(result)
    return result


def validate(result: dict[str, Any]) -> None:
    require(result["schema_version"] == 1, "unsupported sensitivity schema")
    require(set(result["by_cell"]) == set(GPT_CELLS), "missing cell")
    require(len(result["slots"]) == 270, "slot coverage")
    require(len({s["slot_id"] for s in result["slots"]}) == 270, "duplicate slot")
    require(result["pairs"] == pair_views(result["slots"]), "pair calculation drift")
    for c in GPT_CELLS:
        ss = [s for s in result["slots"] if s["cell_id"] == c]
        require(result["by_cell"][c] == group_summary(ss), "cell calculation drift")
        for s in ss:
            require(
                s["effective_outcome"] == s[s["effective_source"]]["normalized_outcome"],
                "effective drift",
            )
            require(
                s["recovery"] is None or s["primary"]["normalized_outcome"] == "infra_failure",
                "unauthorized recovery",
            )
            for kind in KINDS:
                a = s[kind]
                if a and a["execution_budget_capability_failure"]:
                    require(a["normalized_outcome"] == "capability_fail", "budget reclassification")
    for dimension in ("task", "language", "category"):
        field = "task_id" if dimension == "task" else dimension
        expected = {
            key: {
                cell: group_summary(
                    [s for s in result["slots"] if s[field] == key and s["cell_id"] == cell]
                )
                for cell in GPT_CELLS
            }
            for key in sorted({s[field] for s in result["slots"]})
        }
        require(result[f"by_{dimension}"] == expected, "distribution drift")
    json.dumps(result, allow_nan=False)


def markdown(result: dict[str, Any]) -> str:
    lines = [
        "# K-B4.1 GPT/Codex timeout sensitivity",
        "",
        f"**{result['status']}**",
        "",
        "Persisted V6 evidence supports bounded later attribution; no new controlled execution is required before that review. The next phase is not started or authorized here.",
        "",
        "## Frozen controls",
        "",
        "All three cells freeze `gpt-5.6-sol` on the GPT relay Responses route. Direct/medium use medium effort; high uses high effort. The provider request timeout is 180 seconds; all 104 available Direct manifests confirm it. All 217 Codex manifests record a 180-second outer process execution limit. These are different timeout scopes. Task budget: 90 seconds; verifier: 15 seconds. The source-defined V6 plan contract declares 300 seconds per logical run and 2,000 output tokens per provider request, with turns/tools/requests/cost unavailable. These numbers are not evidence of one interchangeable execution deadline or of a Codex-wide token ceiling.",
        "",
        "Manifest facts preserve requested/observed model, route, profile, controls, and primary/recovery identity. Comparison supplementation follows `experiment/report.py`; registry bindings must match the persisted V6 execution-binding digest. No plan or task-health execution is performed.",
        "",
        "## Primary, recovery, and effective evidence",
        "",
        "| Cell | Primary infra timeouts | Primary budget capability failures | Recovery infra timeouts | Recovery budget capability failures | All recoveries | Effective pass/fail | Infra/cancelled |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for c in GPT_CELLS:
        g = result["by_cell"][c]
        e = g["effective"]["outcomes"]
        lines.append(
            f"| `{c}` | {g['primary']['timeout_infrastructure']} | {g['primary']['execution_budget_capability_failures']} | {g['recovery']['timeout_infrastructure']} | {g['recovery']['execution_budget_capability_failures']} | {g['recovery']['attempts']} | {e.get('capability_pass', 0)}/{e.get('capability_fail', 0)} | {e.get('infra_failure', 0)}/{e.get('cancelled', 0)} |"
        )
    lines += [
        "",
        "Capability denominators stay 86 / 86 / 85; campaign-wide 599. Each cell has 90 planned slots. Infrastructure is excluded from capability; cancellations stay separate. Primary evidence is immutable. Zero Direct timeouts means zero observed in selected manifests, not a proven zero across the unobserved extra physical attempt. Across GPT/Codex, four extra physical primaries (1/2/1 by cell) plus one rejected high primary lack authoritative manifests: 269 of 274 recorded physical primaries are observable. Their unknown timeout facts are preserved, not imputed.",
        "",
        "## Timeout-affected slots",
        "",
        "| Cell | Task | Repeat (zero based) | Language/category | Recovery | Still missing capability |",
        "|---|---|---:|---|---|---|",
    ]
    for s in result["slots"]:
        if s["primary"]["timeout_infrastructure"]:
            lines.append(
                f"| `{s['cell_id']}` | `{s['task_id']}` | {s['repeat_index']} | {s['language']} / {s['category']} | `{s['recovery']['source_outcome']}` | {s['timeout_affected_unresolved']} |"
            )
    lines += [
        "",
        "All five entered the authorized single recovery path. Three medium slots passed; one medium and one high slot exhausted recovery with protocol errors. There are zero recovery infrastructure timeouts. Two slots are historically timeout-affected and unresolved; their final category is protocol error. This is association, not causal attribution. Other final infrastructure gaps are Direct malformed responses (4), medium protocol errors (2), and high protocol errors (3).",
        "",
        "## Matched evidence and formal eligibility",
        "",
        "| Comparison | Primary complete | Effective complete | Timeout-affected unavailable | Other unavailable | Tasks with 5 effective complete pairs | Effective comparable/partial/not comparable | Formal eligible |",
        "|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for name, _, _, _ in PAIR_DEFINITIONS:
        g = result["pairs"][name]["summary"]
        e = g["effective"]
        cc = e["complete_pair_comparability"]
        lines.append(
            f"| `{g['left_cell']}` → `{g['right_cell']}` | {g['primary']['capability_complete']}/90 | {e['capability_complete']}/90 | {g['timeout_affected_unavailable_pairs']} | {g['other_unavailable_pairs']} | {e['tasks_with_five_complete_pairs']}/18 | {cc['COMPARABLE']}/{cc['PARTIALLY_COMPARABLE']}/{cc['NOT_COMPARABLE']} | {e['formal_eligible']} |"
        )
    lines += [
        "",
        "GPT direct/medium is PARTIALLY_COMPARABLE because Codex does not expose observed model, Direct trace coverage is limited, and provider configuration evidence differs. Medium/high has 42 COMPARABLE complete pairs and 41 NOT_COMPARABLE complete pairs: the unchanged ablation engine blocks missing verifier execution identity (41), with asymmetric verifier execution/control status in 32. Both unexposed observed models remain informational under the operator-trusted ablation contract. No task has five formal eligible pairs. These existing control restrictions are separate from the two timeout-affected missing slots.",
        "",
        "Exact task/repeat and paired-slot identities drive all joins. Missing pairs remain visible; per-task coverage and every ComparabilityEngine reason are in JSON. Coverage and eligibility are distinct: recovery never upgrades controls. The prior 82/90 and 83/90 complete-pair readouts remain reproducible as observed end-to-end configuration performance. Their effect labels and existing intervals do not prove controlled Harness uplift or reasoning causation. No new significance tests or counterfactual scores are computed.",
        "",
        "Timeout censoring removes a small, explicit subset of usable matches. It limits exhaustive five-repeat coverage and requires excluding those identities from later capability-pair review, but does not block bounded descriptive review of the remaining observations. Other missingness and comparability limits also remain; random missingness and population-wide representativeness are not established.",
        "",
        "## Duration at the actual boundary",
        "",
    ]
    for c in GPT_CELLS[1:]:
        for kind in KINDS:
            for label in ("infrastructure", "capability"):
                d = result["by_cell"][c][kind]["timeout_duration_by_class"][label]
                if d["observations"]:
                    lines.append(
                        f"- `{c}` {kind} {label}: n={d['observations']}; duration min/median/max = {d['min_ms']}/{d['median_ms']}/{d['max_ms']} ms; {d['within_1000ms_of_configured_boundary']} within ±1,000 ms of 180,000 ms."
                    )
    lines += [
        "",
        "These persisted process durations establish boundary clustering only. Queue/logical-run start–finish windows are not substituted for attempt duration. Provider/tool phase allocation and relay waiting inside Codex are unavailable; the relay audit has 73 selected Direct matches and zero Codex matches, so relay residuals cannot be computed.",
        "",
        "## Limits and reproducibility",
        "",
        "**INSUFFICIENT_EVIDENCE_FOR_COUNTERFACTUAL**: existing evidence cannot establish that a model would pass with longer time, that high reasoning caused expiry, that timeout caused the capability difference, or that increasing time would improve score. No new execution is necessary for the next bounded evidence review; a future causal timeout question would require a separately authorized controlled treatment.",
        "",
    ]
    lines.extend(f"- {x}" for x in result["limitations"])
    lines += [
        "",
        "Reproduce (requires the persisted evidence tree; `--evidence-root` can relocate it):",
        "",
        "```sh",
        result["provenance"]["reproduce"],
        "```",
        "",
        "The JSON includes source byte digests, safe attempt facts, all 270 slot identities, exact pair ledgers, task/language/category distributions, prior comparison readouts, and campaign reconciliation. `--check` validates structure/reconciliation and compares both generated files byte for byte. No source artifact is rewritten. Provider/Harness/Judge/Matrix calls: **0**. Discordant attribution, real ablation, K-C, Full Release CI, and expensive qualification regeneration: **NOT RUN**.",
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
    outputs = {
        ".json": json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        ".md": markdown(result),
    }
    for suffix, value in outputs.items():
        path = args.repo_root / (OUTPUT + suffix)
        if args.check:
            require(path.read_text() == value, f"generated artifact drift: {path.name}")
        else:
            path.write_text(value)
    print(result["status"])


if __name__ == "__main__":
    main()
