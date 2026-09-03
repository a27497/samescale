"""Deterministic K-B4 synthesis; reads frozen evidence, never executes an Analyst backend."""

# Reader-facing report sentences follow the existing V6 analysis convention.
# ruff: noqa: E501, RUF001
from __future__ import annotations

import argparse
import ast
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from harnesslab.analyst.models import (
    EvidenceEntry,
    EvidenceRef,
    FactAssertion,
    HypothesisClaim,
    StrictModel,
    ToolName,
    VerifiedFact,
    canonical_fact_statement,
    fact_evidence_refs,
)
from harnesslab.analyst.report import _validate_assertion
from harnesslab.release.badcases import (
    CANONICAL,
    RECEIPT,
    SOURCE_DIGESTS,
    encoded,
    read_object,
    require,
    verify_frozen_badcases,
)
from harnesslab.sandbox.artifacts import sha256_file
from scripts.analyze_kb4_discordant_pairs import validate as validate_discordances
from scripts.analyze_kb4_timeout_sensitivity import PAIR_DEFINITIONS
from scripts.analyze_kb4_timeout_sensitivity import validate as validate_timeouts

OUTPUT = "release/kb4-final-attribution-report"
BASE_COMMIT = "ac869396b9bcd9d7ed129fd9c8e7bc70d0e53eb9"
MATRIX = "release/core-real-matrix-v6-final-analysis.json"
DATA = "release/core-real-matrix-v6-analysis-dataset-manifest.json"
CHECKPOINT = "release/core-real-matrix-v6-checkpoint-630.json"
TIMEOUT = "release/kb4-gpt-codex-timeout-sensitivity.json"
DISCORDANT = "release/kb4-discordant-pair-attribution.json"
V6_SOURCE = "src/harnesslab/release/v6.py"
CELLS = ("model-gpt56-relay-responses", "harness-codex-gpt56-medium", "harness-codex-gpt56-high")
LABELS = dict(zip(CELLS, ("Direct GPT", "Codex medium", "Codex high"), strict=True))
MATRIX_PAIRS = ("gpt_harness_effect", "reasoning_effort_effect")
PINS = {
    **SOURCE_DIGESTS,
    CANONICAL: "sha256:8f2ac7d3ecc745ef0f9ba19204e9ec0ea0947b0c7388c4eee260205b34996082",
    RECEIPT: "sha256:0cf5b63aa5c5a40a1853e7c10dacf7e7452b8cf09548e4a130030de22325123b",
}
LIMITATIONS = (
    "All 82 Direct/medium complete pairs are PARTIALLY_COMPARABLE: observed model, provider configuration, and trace coverage limit interpretation. No causal Harness uplift is established.",
    "Medium/high has 42 COMPARABLE and 41 NOT_COMPARABLE complete pairs; no task has five comparable repeats and formal eligibility is false. The 41 excluded controls cannot contribute controlled claims.",
    "The two COMPARABLE discordances support recorded pair-level contrasts under the operator-trusted route, not a causal mechanism or population-wide reasoning-effort effect. Their passing comparator trees are integrity-limited.",
    "Direct lacks an equivalent agent trace. Private reasoning and complete Codex provider-call timing are unavailable; no reasoning reconstruction or relay-phase causal claim is possible.",
    "Five physical-primary timeout facts are unknown (four extra attempts plus one rejected primary); timeout counts are observed minima. Missingness is not established as random.",
    "The three BadCases span two failure signatures. Python specification interpretation remains a hypothesis, and every canonical root_cause remains null.",
    "No longer-timeout treatment exists. Longer budgets improving results, reasoning causing expiry, or timeout causing the capability delta are unsupported counterfactual claims.",
    "The corpus is 18 Tier-A micro-contract tasks with at most five repeats per task. Descriptive configuration results do not establish universal coding capability or population-wide causal rankings.",
    "Capability uses pass+fail; operational pass rates retain planned slots. Infra/cancelled and missing usage remain explicit, never zero-filled into capability or usage. Existing cost estimates are accounting, not billing truth.",
    "K-B4.2's 17 workspace and 9 verifier-tree mismatches remain historical audit limitations; this report does not repair or reclassify them. K-B4.3 independently verified the selected failures' required bundles.",
)


class ReportClaim(StrictModel):
    claim_id: str
    level: Literal["VERIFIED_FACT", "DIAGNOSTIC_ASSOCIATION", "ATTRIBUTION_HYPOTHESIS"]
    statement: str
    proof: VerifiedFact
    limitations: tuple[str, ...] = Field(min_length=1)
    causal_language_permitted: Literal[False] = False
    hypothesis: HypothesisClaim | None = None


def select(value: Any, path: Sequence[str | int]) -> Any:
    for segment in path:
        value = value[segment]
    return value


def declaration(root: Path) -> dict[str, Any]:
    """Read literal frozen declaration without constructing a plan or running task health."""
    calls = [
        n
        for n in ast.walk(ast.parse((root / V6_SOURCE).read_text()))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "AblationSpec"
    ]
    require(len(calls) == 1, "ambiguous V6 ablation declaration")
    return {
        k.arg: ast.literal_eval(k.value)
        for k in calls[0].keywords
        if k.arg is not None and k.arg != "intent"
    }


def load_sources(root: Path) -> dict[str, Any]:
    for reference, digest in PINS.items():
        require(sha256_file(root / reference) == digest, f"frozen input drift: {reference}")
    verify_frozen_badcases(root)
    timeout = read_object(root / TIMEOUT)
    for reference, digest in timeout["provenance"]["sources_sha256"].items():
        if not reference.startswith("evidence:"):
            require(sha256_file(root / reference) == digest, f"frozen V6 source drift: {reference}")
    sources = {
        p: read_object(root / p)
        for p in (MATRIX, DATA, CHECKPOINT, TIMEOUT, DISCORDANT, CANONICAL, RECEIPT)
    }
    validate_timeouts(timeout)
    validate_discordances(sources[DISCORDANT])
    sources[V6_SOURCE] = declaration(root)
    require(
        sources[V6_SOURCE]["changed_dimension"] == "reasoning_effort", "ablation treatment drift"
    )
    require(
        sources[DATA]["plan_digest"] == sources[CHECKPOINT]["scientific_controls"]["plan_digest"],
        "plan identity drift",
    )
    require(
        sources[MATRIX]["dataset_validation"]["dataset_sha256"] == sources[DATA]["dataset_sha256"],
        "dataset binding drift",
    )
    return sources


def build(root: Path) -> dict[str, Any]:
    sources = load_sources(root)
    matrix, timeout, dd, badcases = (sources[p] for p in (MATRIX, TIMEOUT, DISCORDANT, CANONICAL))
    catalog: dict[str, EvidenceEntry] = {}
    bindings: dict[str, Any] = {}
    claims: list[dict[str, Any]] = []

    def entry(ref: str, tool: ToolName, fields: dict[str, tuple[str, list[str | int]]]) -> None:
        digest_bindings = tuple(
            sorted({sha256_file(root / source) for source, _ in fields.values()})
        )
        catalog[ref] = EvidenceEntry(
            ref=EvidenceRef(id=ref),
            tools=(tool,),
            digest_bindings=digest_bindings,
            data_by_tool={
                tool.value: {
                    key: select(sources[source], path) for key, (source, path) in fields.items()
                }
            },
        )
        bindings[ref] = {
            "tool": tool.value,
            "digest_bindings": digest_bindings,
            "fields": {
                key: {"source": source, "path": path} for key, (source, path) in fields.items()
            },
        }

    def claim(
        claim_id: str,
        ref: str,
        paths: Sequence[Sequence[str | int]],
        statement: str,
        limits: tuple[str, ...],
        level: str = "VERIFIED_FACT",
        hypothesis: HypothesisClaim | None = None,
    ) -> None:
        item = catalog[ref]
        assertions = tuple(
            FactAssertion(
                evidence_ref=ref,
                tool=item.tools[0],
                field_path=tuple(path),
                expected_value=select(item.data_by_tool[item.tools[0].value], path),
            )
            for path in paths
        )
        for assertion in assertions:
            _validate_assertion(assertion, item)
        proof = VerifiedFact(
            statement=canonical_fact_statement(assertions),
            evidence_refs=fact_evidence_refs(assertions),
            assertions=assertions,
        )
        claims.append(
            ReportClaim.model_validate(
                {
                    "claim_id": claim_id,
                    "level": level,
                    "statement": statement,
                    "proof": proof,
                    "limitations": limits,
                    "hypothesis": hypothesis,
                }
            ).model_dump(mode="json")
        )

    cell_views = {}
    for i, cell in enumerate(CELLS, 1):
        ref = f"cell:core-real-matrix-v6:{cell}"
        entry(
            ref,
            ToolName.QUERY_RUNS,
            {
                "outcomes": (MATRIX, ["cell_summaries", cell]),
                "attempts": (TIMEOUT, ["by_cell", cell]),
                "usage": (MATRIX, ["usage", cell]),
                "control": (TIMEOUT, ["controls", cell, "digest_verified_binding"]),
            },
        )
        c, a = matrix["cell_summaries"][cell], timeout["by_cell"][cell]
        cell_views[cell] = {"outcomes": c, "attempts": a, "usage": matrix["usage"][cell]}
        require(
            c["capability_evaluable"] == a["effective"]["capability_n"],
            "capability denominator drift",
        )
        claim(
            f"F0{i}",
            ref,
            [["outcomes"], ["attempts", "effective"], ["control", "reasoning_effort"]],
            f"{LABELS[cell]} records {c['capability_pass']} passes and {c['capability_fail']} failures among {c['capability_evaluable']} capability results; {c['infra_missing']} infrastructure and {c['cancelled']} cancellations remain separate from its 90 planned slots.",
            (LIMITATIONS[8], LIMITATIONS[7]),
        )

    comparisons = {}
    for i, ((name, left, right, intent), matrix_name) in enumerate(
        zip(PAIR_DEFINITIONS, MATRIX_PAIRS, strict=True), 4
    ):
        ref = f"{'ablation' if intent == 'CONTROLLED_ABLATION' else 'pair'}:core-real-matrix-v6:{name}"
        entry(
            ref,
            ToolName.GET_ABLATION if intent == "CONTROLLED_ABLATION" else ToolName.COMPARE_CELLS,
            {
                "statistics": (MATRIX, ["paired_comparisons", matrix_name]),
                "comparability": (TIMEOUT, ["pairs", name, "summary", "effective"]),
                "discordances": (DISCORDANT, ["summaries", name]),
                **(
                    {
                        "declaration": (V6_SOURCE, []),
                        "accepted_association": (DISCORDANT, ["findings", 1]),
                    }
                    if intent == "CONTROLLED_ABLATION"
                    else {}
                ),
            },
        )
        stats, s = matrix["paired_comparisons"][matrix_name], dd["summaries"][name]
        cap = stats["capability"]
        require(cap["complete_pairs"] == s["effective_complete_pairs"], "complete-pair drift")
        require(
            cap["discordant_baseline_pass_variant_fail"] == s["direction"]["LEFT_PASS_RIGHT_FAIL"],
            "discordance drift",
        )
        require(
            cap["discordant_baseline_fail_variant_pass"] == s["direction"]["LEFT_FAIL_RIGHT_PASS"],
            "reverse discordance drift",
        )
        comparisons[name] = {
            "left_cell": left,
            "right_cell": right,
            "intent": intent,
            "descriptive_statistics": {
                k: stats[k] for k in ("capability", "operational", "missingness", "latency")
            },
            "comparability": timeout["pairs"][name]["summary"]["effective"],
            "discordance_summary": s,
            "causal_interpretation_permitted": False,
        }
        claim(
            f"F0{i}",
            ref,
            [
                ["statistics", "capability"],
                ["statistics", "operational"],
                ["comparability", "complete_pair_comparability"],
                ["comparability", "formal_eligible"],
                ["discordances", "by_comparability"],
            ],
            f"{LABELS[left]}→{LABELS[right]} has {cap['complete_pairs']}/90 complete pairs, discordances {cap['discordant_baseline_pass_variant_fail']}/{cap['discordant_baseline_fail_variant_pass']} (left-pass/right-fail versus reverse), and a descriptive equal-task capability delta of {100 * cap['delta']:.2f} percentage points; formal eligibility is false.",
            (
                LIMITATIONS[0] if i == 4 else LIMITATIONS[1],
                "Frozen confidence intervals and McNemar p-values remain descriptive; numerical significance cannot override Comparability.",
            ),
        )

    ablation_ref = f"ablation:core-real-matrix-v6:{PAIR_DEFINITIONS[1][0]}"
    comparable = [
        p
        for p in dd["comparisons"][PAIR_DEFINITIONS[1][0]]["discordant_pairs"]
        if p["comparability"]["status"] == "COMPARABLE"
    ]
    claim(
        "F06",
        ablation_ref,
        [
            ["declaration"],
            ["comparability", "formal_comparable"],
            ["comparability", "tasks_with_five_formal_pairs"],
            ["discordances", "by_comparability", "COMPARABLE"],
            ["accepted_association"],
        ],
        "The declared reasoning_effort treatment has real medium/high V6 observations and 42 comparable pairs, but no task has five comparable repeats. Its two comparable discordances favor medium; this supports bounded pair-level association, not a formal effect or verified mechanism.",
        (LIMITATIONS[1], LIMITATIONS[2]),
        "DIAGNOSTIC_ASSOCIATION",
    )

    # Use the existing pair identity for campaign/timeout context, not a fictitious run identity.
    context_ref = f"pair:core-real-matrix-v6:{PAIR_DEFINITIONS[0][0]}"
    context_fields: dict[str, tuple[str, list[str | int]]] = {
        "campaign": (DATA, []),
        "checkpoint": (CHECKPOINT, ["effective"]),
        "timeouts": (TIMEOUT, ["by_cell"]),
        "audit": (DISCORDANT, ["reconciliation"]),
        "taxonomy": (DISCORDANT, ["summaries"]),
        "counterfactual": (TIMEOUT, ["counterfactual_status"]),
        "execution_scopes": (TIMEOUT, ["plan_budget_contract_source_defined"]),
        "accepted_findings": (DISCORDANT, ["findings"]),
    }
    # A second tool namespace on the same real pair keeps its aggregate context explicit.
    previous = catalog[context_ref]
    previous_binding = bindings[context_ref]
    entry(context_ref, ToolName.INSPECT_FAILURE, context_fields)
    context = catalog[context_ref]
    catalog[context_ref] = context.model_copy(
        update={
            "tools": (*previous.tools, *context.tools),
            "digest_bindings": tuple(
                sorted(set(previous.digest_bindings + context.digest_bindings))
            ),
            "data_by_tool": {**previous.data_by_tool, **context.data_by_tool},
        }
    )
    bindings[context_ref] = {"namespaces": [previous_binding, bindings[context_ref]]}

    def context_claim(
        claim_id: str,
        paths: Sequence[Sequence[str | int]],
        statement: str,
        limits: tuple[str, ...],
        level: str = "VERIFIED_FACT",
    ) -> None:
        original = catalog[context_ref]
        catalog[context_ref] = original.model_copy(update={"tools": (ToolName.INSPECT_FAILURE,)})
        claim(claim_id, context_ref, paths, statement, limits, level)
        catalog[context_ref] = original

    observed_timeouts = sum(
        a["primary"]["timeout_infrastructure"] for a in timeout["by_cell"].values()
    )
    unresolved = sum(
        a["timeout_affected_recovery"]["unresolved"] for a in timeout["by_cell"].values()
    )
    unknown = sum(
        a["extra_primary_attempts_without_selected_manifest"]
        + a["selected_primary_manifest_unavailable"]
        for a in timeout["by_cell"].values()
    )
    context_claim(
        "F07",
        [
            ["campaign", "row_count"],
            ["campaign", "plan_digest"],
            ["campaign", "dataset_sha256"],
            ["checkpoint"],
        ],
        "The frozen V6 campaign contains 630 logical slots (18 tasks × 5 repeats × 7 cells), with 599 capability results, 29 infrastructure outcomes and two cancellations after bounded recovery.",
        (LIMITATIONS[7], LIMITATIONS[8]),
    )
    context_claim(
        "F08",
        [
            ["timeouts", cell, field]
            for cell in CELLS
            for field in (
                "timeout_affected_recovery",
                "extra_primary_attempts_without_selected_manifest",
                "selected_primary_manifest_unavailable",
            )
        ],
        f"{observed_timeouts} primary infrastructure timeouts were observed; {observed_timeouts - unresolved} recovered to capability evidence and {unresolved} remain unresolved with final protocol errors. {unknown} physical-primary timeout facts remain unknown.",
        (LIMITATIONS[4], LIMITATIONS[6]),
    )
    context_claim(
        "F09",
        [
            ["timeouts", cell, attempt, "timeout_duration_by_class"]
            for cell in CELLS[1:]
            for attempt in ("primary", "recovery")
        ]
        + [["execution_scopes"]],
        "All five observed primary infrastructure timeouts and most trace-proven capability budget exhaustions cluster within one second of the recorded 180-second Codex process boundary. This is a duration observation, not evidence that more time would change results.",
        (
            LIMITATIONS[6],
            "The 180-second provider request, 180-second Codex process, 90-second task, 15-second verifier and 300-second plan scopes are distinct.",
        ),
    )
    context_claim(
        "F10",
        [["taxonomy", name, "failure_taxonomy"] for name, *_ in PAIR_DEFINITIONS],
        "Direct/medium discordances contain 16 native Timeout and two Test Failure observations; medium/high contain 32 Timeout, one No Modification and one Test Failure. Trace-proven execution_budget_exhausted stays capability failure; infrastructure/protocol gaps remain excluded.",
        (
            "The two comparison intents are not pooled as one treatment; repeated medium membership is not a new run.",
        ),
    )
    context_claim(
        "F11",
        [
            ["audit", k]
            for k in (
                "unique_inspected_slots",
                "workspace_digest_mismatches",
                "verifier_tree_digest_mismatches",
            )
        ],
        "K-B4.2 inspected 95 unique discordant members and retained 17 workspace-tree and nine verifier-tree mismatches, with independently matching available source/trace/verifier-output bindings.",
        (LIMITATIONS[9], LIMITATIONS[2]),
    )
    context_claim(
        "A01",
        [
            ["taxonomy", name, field]
            for name, *_ in PAIR_DEFINITIONS
            for field in ("failure_taxonomy", "discordant_pairs")
        ]
        + [["accepted_findings", 0]],
        "Execution-budget exhaustion dominates the selected discordances (16/18 Direct/medium; 32/34 medium/high). This is a diagnostic association, not proof that timeout or reasoning effort caused the capability difference.",
        (LIMITATIONS[6], "Selected discordant failures are not a population failure-rate sample."),
        "DIAGNOSTIC_ASSOCIATION",
    )

    badcase_refs = []
    for i, case in enumerate(badcases["slots"]):
        ref = case["run_identity"]
        detail = case["frozen_evidence"]
        entry(ref, ToolName.INSPECT_FAILURE, {"badcase": (CANONICAL, ["slots", i])})
        claim(
            f"B0{i + 1}",
            ref,
            [
                ["badcase", key]
                for key in (
                    "slot_id",
                    "task_identity",
                    "cell_identity",
                    "observed_failure",
                    "attribution_classification",
                    "root_cause",
                    "mitigation_lesson",
                    "safe_trace_facts",
                )
            ]
            + [
                ["badcase", "frozen_evidence", key]
                for key in (
                    "manifest_digest",
                    "repeat_index",
                    "verifier_report",
                    "trace_status",
                    "failure_class",
                    "safe_tool_facts",
                )
            ],
            f"{case['cell_identity'].removeprefix('cell:')} / {case['task_identity'].split('#')[0].removeprefix('task:')} / repeat {detail['repeat_index']}: {detail['failure_class']}, deterministic verifier score {detail['verifier_report']['score']}. {case['observed_failure']} Classification remains OBSERVED_FACT and root_cause is null.",
            tuple(case["limitations"]),
        )
        badcase_refs.append(
            {
                "slot_id": case["slot_id"],
                "canonical_reference": CANONICAL,
                "json_pointer": f"/slots/{i}",
                "run_identity": ref,
                "manifest_digest": detail["manifest_digest"],
                "claim_id": f"B0{i + 1}",
                "trace_status": detail["trace_status"],
                "engineering_lesson": case["mitigation_lesson"],
            }
        )
    python_case = badcases["slots"][1]
    h = python_case["hypotheses"][0]
    hypothesis = HypothesisClaim(
        statement=h["statement"],
        evidence_refs=(python_case["run_identity"], badcases["slots"][2]["run_identity"]),
        additional_evidence_needed=h["verify_or_falsify"],
    )
    claim(
        "H01",
        python_case["run_identity"],
        [["badcase", "hypotheses", 0], ["badcase", "root_cause"]],
        hypothesis.statement,
        (
            LIMITATIONS[5],
            "A public-contract clarification would require a separately authorized causal control; it is not performed or required for this factual synthesis.",
        ),
        "ATTRIBUTION_HYPOTHESIS",
        hypothesis,
    )

    source_paths = set(sources) | {
        "release/core-real-matrix-v6-analysis-dataset.jsonl",
        "release/core-real-matrix-v6-control.json",
        "release/core-real-matrix-v6-final-analysis.md",
        "release/core-real-matrix-v6-gpt-relay-attribution-source-audit.json",
        "release/core-real-matrix-v6-gpt-relay-match-map.jsonl",
        *PINS,
        "docs/ANALYST.md",
        "docs/EVAL_METHODOLOGY.md",
        "docs/EVAL_METHODOLOGY_V2.md",
        "docs/FAIRNESS_CONTRACT.md",
        "docs/HARNESS_COMPARABILITY.md",
        "docs/EXPERIMENT_STATISTICS.md",
        "docs/BADCASES.md",
        "src/harnesslab/analyst/models.py",
        "src/harnesslab/analyst/report.py",
        "scripts/build_kb4_final_attribution.py",
    }
    ablation_state = "ABLATION_EVIDENCE_PRESENT_WITH_LIMITATIONS"
    requirements = [
        {
            "requirement": "Codex medium/high reasoning ablation",
            "status": ablation_state,
            "claim_ids": ["F05", "F06"],
            "evidence_refs": [ablation_ref],
            "limitations": [LIMITATIONS[1], LIMITATIONS[2]],
        },
        {
            "requirement": "Three real verifier-backed BadCases",
            "status": "FROZEN_VERIFIED",
            "claim_ids": ["B01", "B02", "B03"],
            "evidence_refs": [CANONICAL, RECEIPT],
            "limitations": [LIMITATIONS[5]],
        },
        {
            "requirement": "Failure taxonomy",
            "status": "EVIDENCE_PRESENT",
            "claim_ids": ["F10", "A01"],
            "evidence_refs": [DISCORDANT],
            "limitations": ["Diagnostic associations do not establish causes."],
        },
        {
            "requirement": "Trace diagnosis",
            "status": "EVIDENCE_PRESENT_WITH_LIMITATIONS",
            "claim_ids": ["F11", "B01", "B02", "B03"],
            "evidence_refs": [DISCORDANT, CANONICAL],
            "limitations": [LIMITATIONS[2], LIMITATIONS[3], LIMITATIONS[9]],
        },
        {
            "requirement": "Attribution report",
            "status": "REPORT_COMPLETE",
            "claim_ids": [c["claim_id"] for c in claims],
            "evidence_refs": [OUTPUT + ".json", OUTPUT + ".md"],
            "limitations": [
                "Evidence reconciliation only; K-B4 is not approved and the Final Gate is not run."
            ],
        },
    ]
    return {
        "schema_version": 1,
        "phase": "K-B4.4",
        "base_commit": BASE_COMMIT,
        "status": "READY_FOR_KB4_FINAL_GATE",
        "kb4_approved": False,
        "final_gate": "NOT_RUN",
        "kc": "NOT_RUN",
        "new_experimental_evidence": False,
        "provenance": {
            "experiment_id": sources[DATA]["experiment_id"],
            "plan_digest": sources[DATA]["plan_digest"],
            "dataset_sha256": sources[DATA]["dataset_sha256"],
            "as_of": timeout["provenance"]["as_of"],
            "catalog_mode": "Offline projection into native Analyst tool namespaces; no tool or backend execution.",
            "sources_sha256": {p: sha256_file(root / p) for p in sorted(source_paths)},
        },
        "statistical_authority": {
            "frozen_method": matrix["metadata"],
            "new_statistics_computed": False,
            "interpretation_control": "Comparability eligibility controls interpretation authority; numerical significance is not causal evidence.",
        },
        "core_results": cell_views,
        "comparisons": comparisons,
        "ablation": {
            "status": ablation_state,
            "declaration": sources[V6_SOURCE],
            "comparable_discordances": [
                {
                    k: p[k]
                    for k in (
                        "pair_id",
                        "task_id",
                        "task_version",
                        "repeat_index",
                        "current_task_comparable_n",
                        "current_task_evidence_tier",
                        "both_member_bundles_verified",
                    )
                }
                for p in comparable
            ],
            "formal_eligible": False,
            "controlled_attribution_claims": 0,
        },
        "timeout_sensitivity": {
            "observed_primary_infra_timeouts": observed_timeouts,
            "recovered_to_capability": observed_timeouts - unresolved,
            "unresolved": unresolved,
            "unknown_physical_primary_timeout_facts": unknown,
            "counterfactual_status": timeout["counterfactual_status"],
            "execution_scopes": timeout["plan_budget_contract_source_defined"],
        },
        "badcases": badcase_refs,
        "canonical_badcase_model_digest": sources[RECEIPT]["canonical_model_digest"],
        "catalog_bindings": bindings,
        "claim_ledger": claims,
        "controlled_attribution_claim_count": 0,
        "limitations": LIMITATIONS,
        "requirement_reconciliation": requirements,
        "external_execution": {
            k: 0 for k in ("provider", "harness", "judge", "matrix", "ablation", "analyst_llm")
        },
        "reproduce": "uv run --locked python -m scripts.build_kb4_final_attribution --check",
    }


def validate(report: dict[str, Any], root: Path) -> None:
    sources = load_sources(root)
    entries = {}
    for ref, binding in report["catalog_bindings"].items():
        namespaces = binding.get("namespaces", [binding])
        tools = tuple(ToolName(n["tool"]) for n in namespaces)
        entries[ref] = EvidenceEntry(
            ref=EvidenceRef(id=ref),
            tools=tools,
            digest_bindings=tuple(sorted({d for n in namespaces for d in n["digest_bindings"]})),
            data_by_tool={
                n["tool"]: {
                    field: select(sources[b["source"]], b["path"])
                    for field, b in n["fields"].items()
                }
                for n in namespaces
            },
        )
    ids = []
    for raw in report["claim_ledger"]:
        c = ReportClaim.model_validate(raw)
        ids.append(c.claim_id)
        for assertion in c.proof.assertions:
            require(assertion.evidence_ref in entries, "claim reference absent")
            _validate_assertion(assertion, entries[assertion.evidence_ref])
        if c.hypothesis:
            require(c.level == "ATTRIBUTION_HYPOTHESIS", "hypothesis level upgraded")
            require(
                all(ref in entries for ref in c.hypothesis.evidence_refs),
                "hypothesis reference absent",
            )
    require(len(ids) == len(set(ids)), "duplicate claim id")
    require(encoded(report) == encoded(build(root)), "report derivation drift")


def markdown(report: dict[str, Any]) -> str:
    claims = {c["claim_id"]: c for c in report["claim_ledger"]}
    method = report["statistical_authority"]["frozen_method"]
    lines = [
        "# K-B4 Final Attribution Report",
        "",
        f"**{report['status']}** — evidence reconciliation only; K-B4 is not approved. Final Gate and K-C are NOT_RUN.",
        "",
        "## 1. Evidence scope",
        "",
        claims["F07"]["statement"] + " [F07]",
        "",
        f"Experiment `{report['provenance']['experiment_id']}`; plan `{report['provenance']['plan_digest']}`; dataset `{report['provenance']['dataset_sha256']}`. The JSON binds exact source hashes and Analyst FactAssertion paths. This deterministic synthesis creates no new experimental evidence or statistics.",
        "",
        "## 2. Core observed results",
        "",
        "| Configuration | Planned | Pass/fail | Capability n | Capability pass rate | Infra | Cancelled | Missing capability | Recoveries |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for cell in CELLS:
        c = report["core_results"][cell]
        o, e = c["outcomes"], c["attempts"]["effective"]
        lines.append(
            f"| {LABELS[cell]} | {c['attempts']['planned']} | {o['capability_pass']}/{o['capability_fail']} | {o['capability_evaluable']} | {100 * o['capability_pass_rate']:.1f}% | {o['infra_missing']} | {o['cancelled']} | {e['missing_count']} | {e['recovery_attempt_count']} |"
        )
    lines += [
        "",
        "Capability n is pass+fail; missing capability includes infrastructure and cancellations. Operational rates retain all planned slots. Primary/recovery outcomes, Wilson intervals and observed usage coverage remain in JSON; missing values stay null. These are frozen configuration observations, not a causal ranking. [F01–F03]",
        "",
        "## 3. Direct GPT versus Codex medium",
        "",
        claims["F04"]["statement"] + " [F04]",
        "",
        report["limitations"][0],
        "",
        "## 4. Codex medium versus high reasoning",
        "",
        f"**{report['ablation']['status']}**. " + claims["F06"]["statement"] + " [F06]",
        "",
        "Of 83 complete pairs, 42 are COMPARABLE and 41 NOT_COMPARABLE. Of 34 discordances, two are COMPARABLE (both medium PASS/high FAIL); 32 are NOT_COMPARABLE (23 medium PASS/high FAIL, nine reverse). The comparable cases are Java settings-merge repeat 0 and Python deduplicate repeat 2. Their task comparable n values are 2 and 4, and passing comparator trees are incomplete. No task reaches the five-comparable-repeat formal requirement. [F05–F06, F11]",
        "",
        "### Frozen descriptive paired statistics",
        "",
        f"Deltas are variant minus baseline, in percentage points; capability deltas use equal task weighting. The original {method['bootstrap_replicates']:,} task-cluster bootstrap replicates, seed {method['bootstrap_seed']}, and secondary exact McNemar results are retained without recomputation.",
        "",
        "| Baseline → variant | Capability delta [95% CI], pp | Operational delta [95% CI], pp | McNemar exact p |",
        "|---|---|---|---:|",
    ]
    for name, *_ in PAIR_DEFINITIONS:
        c = report["comparisons"][name]
        cap, op = (c["descriptive_statistics"][k] for k in ("capability", "operational"))

        def interval(v: dict[str, Any]) -> str:
            return f"{100 * v['delta']:.2f} [{100 * v['cluster_bootstrap_ci']['low']:.2f}, {100 * v['cluster_bootstrap_ci']['high']:.2f}]"

        lines.append(
            f"| {LABELS[c['left_cell']]} → {LABELS[c['right_cell']]} | {interval(cap)} | {interval(op)} | {cap['mcnemar_exact_p']:.12g} |"
        )
    lines += [
        "",
        "These estimates include partially/not-comparable complete observations. Their intervals and p-values do not override Comparability or establish a formal Harness/reasoning effect. Row-weighted deltas, separate operational estimands, overlapping exclusion flags and paired latency coverage remain inspectable in JSON. Controlled-attribution claims: **0**. [F04–F06]",
        "",
        "## 5. Timeout sensitivity",
        "",
        claims["F08"]["statement"] + " [F08]",
        "",
        claims["F09"]["statement"] + " [F09]",
        "",
        "The five timeouts comprise four medium and one high observation. All five entered one bounded recovery; three medium slots passed, while medium Java deduplicate repeat 4 and high Python clamp repeat 2 ended with protocol errors. Across GPT/Codex, 269 of 274 physical primaries have authoritative timeout facts. The provider-request, Codex-process, task, verifier and plan deadlines have different scopes (180/180/90/15/300 seconds); provider metadata is not proof of a Codex-wide token ceiling.",
        "",
        "## 6. Failure taxonomy and trace diagnosis",
        "",
        claims["F10"]["statement"] + " [F10]",
        "",
        claims["F11"]["statement"] + " [F11]",
        "",
        "Deterministic verifier/build/source evidence outranks structured tool evidence, which outranks agent self-report. The Java agent's workspace-unavailable statement does not prove a runtime cause; incidental git errors and issued local-check syntax do not supersede verifier failure. Direct's lack of an agent trace remains explicit.",
        "",
        "## 7. Three factual BadCases",
        "",
        "The canonical payload is [badcases.json](badcases.json), bound by [kb4-badcase-freeze.json](kb4-badcase-freeze.json). No cases are reselected or rewritten.",
        "",
    ]
    for b in report["badcases"]:
        c = claims[b["claim_id"]]
        lines += [
            f"- **{b['slot_id']}** ({c['level']}): {c['statement']} Evidence `{b['run_identity']}`, `{b['manifest_digest']}`; canonical `{b['json_pointer']}`. Trace: `{b['trace_status']}`. Lesson: {b['engineering_lesson']} Limits: {' '.join(c['limitations'][3:])} [{b['claim_id']}]"
        ]
    lines += [
        "",
        "Java's trace contains no commands or edits. High Python has public edit/check evidence; Direct Python has verifier/source evidence only. All root causes remain null; the three cases represent two failure signatures. A factual failure does not establish a causal mechanism, Harness uplift or a formal reasoning-effort effect. These shared limits and the case-specific limits are bound in the JSON ledger.",
        "",
        "## 8. Attribution claim ledger",
        "",
        "Every JSON claim carries a stable ID, level, human-readable statement, native VerifiedFact assertions/canonical rendering, evidence references, limitations and causal-language permission=false. Repository OBSERVED_FACT BadCases map to VERIFIED_FACT assertion semantics without upgrading attribution.",
        "",
        f"- **F06 — DIAGNOSTIC_ASSOCIATION:** {claims['F06']['statement']}",
        f"- **A01 — DIAGNOSTIC_ASSOCIATION:** {claims['A01']['statement']}",
        f"- **H01 — ATTRIBUTION_HYPOTHESIS:** {claims['H01']['statement']}",
        f"  Required evidence: {claims['H01']['hypothesis']['additional_evidence_needed']}",
        "- **CONTROLLED_ATTRIBUTION: 0.** COMPARABLE pair-level contrasts remain controlled-ablation associations with their original small-n and integrity limits.",
        "",
        "## 9. Limitations and forbidden claims",
        "",
    ]
    lines += ["- " + limitation for limitation in report["limitations"]]
    lines += [
        "",
        "## 10. K-B4 requirement reconciliation",
        "",
        "| Requirement | Evidence status | Claims |",
        "|---|---|---|",
    ]
    lines += [
        f"| {r['requirement']} | {r['status']} | {', '.join(r['claim_ids'])} |"
        for r in report["requirement_reconciliation"]
    ]
    lines += [
        "",
        "These statuses reconcile available evidence; they do not approve K-B4 or authorize its Final Gate.",
        "",
        "Reproduce:",
        "",
        "```sh",
        report["reproduce"],
        "```",
        "",
        "**NOT RUN:** provider, Harness, Judge, Matrix, ablation and Analyst LLM calls (all zero); subject reruns; qualification regeneration; Full Release CI; K-B4 Final Gate; K-C.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    report = build(args.repo_root)
    validate(report, args.repo_root)
    for suffix, content in ((".json", encoded(report)), (".md", markdown(report))):
        path = args.repo_root / (OUTPUT + suffix)
        if args.check:
            require(path.read_text() == content, f"generated report drift: {path.name}")
        else:
            path.write_text(content)
    print(report["status"])


if __name__ == "__main__":
    main()
