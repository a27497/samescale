from __future__ import annotations

import copy
import subprocess
from pathlib import Path
from typing import Any

import pytest
from scripts import build_kb4_final_attribution as final
from scripts.analyze_kb4_timeout_sensitivity import PAIR_DEFINITIONS

from harnesslab.analyst.models import FactAssertion, canonical_fact_statement
from harnesslab.analyst.report import AttributionValidationError
from harnesslab.release.badcases import CANONICAL, encoded, read_object

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def report() -> dict[str, Any]:
    return read_object(ROOT / (final.OUTPUT + ".json"))


def test_report_reproduces_from_frozen_sources_without_executing_a_backend(
    report: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("deterministic report attempted a subprocess")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    final.validate(report, ROOT)
    assert encoded(final.build(ROOT)) == (ROOT / (final.OUTPUT + ".json")).read_text()
    assert final.markdown(report) == (ROOT / (final.OUTPUT + ".md")).read_text()
    assert set(report["external_execution"].values()) == {0}
    assert report["new_experimental_evidence"] is False


def test_statistics_are_preserved_separately_from_comparability(report: dict[str, Any]) -> None:
    matrix = read_object(ROOT / final.MATRIX)
    timeout = read_object(ROOT / final.TIMEOUT)
    for (name, *_), matrix_name in zip(PAIR_DEFINITIONS, final.MATRIX_PAIRS, strict=True):
        comparison = report["comparisons"][name]
        original = matrix["paired_comparisons"][matrix_name]
        for estimand in ("capability", "operational", "missingness", "latency"):
            assert comparison["descriptive_statistics"][estimand] == original[estimand]
        assert comparison["comparability"] == timeout["pairs"][name]["summary"]["effective"]
        assert comparison["comparability"]["formal_eligible"] is False
        assert comparison["causal_interpretation_permitted"] is False
    assert report["statistical_authority"]["frozen_method"] == matrix["metadata"]
    for cell in final.CELLS:
        view = report["core_results"][cell]
        assert view["usage"] == matrix["usage"][cell]
        outcomes = view["outcomes"]
        assert outcomes == matrix["cell_summaries"][cell]
        assert (
            outcomes["capability_evaluable"]
            == outcomes["capability_pass"] + outcomes["capability_fail"]
        )
        assert outcomes["capability_evaluable"] < view["attempts"]["planned"]
    assert report["timeout_sensitivity"]["unknown_physical_primary_timeout_facts"] == 5
    assert report["timeout_sensitivity"]["unresolved"] == 2


def test_ablation_and_badcases_keep_accepted_classification_and_integrity_limits(
    report: dict[str, Any],
) -> None:
    ablation = report["ablation"]
    assert ablation["status"] == "ABLATION_EVIDENCE_PRESENT_WITH_LIMITATIONS"
    assert ablation["declaration"] == final.declaration(ROOT)
    assert ablation["formal_eligible"] is False
    assert (
        report["controlled_attribution_claim_count"]
        == ablation["controlled_attribution_claims"]
        == 0
    )
    assert [
        (p["current_task_comparable_n"], p["current_task_evidence_tier"])
        for p in ablation["comparable_discordances"]
    ] == [(2, "INSUFFICIENT"), (4, "INFORMAL")]
    assert all(not p["both_member_bundles_verified"] for p in ablation["comparable_discordances"])
    claims = {c["claim_id"]: c for c in report["claim_ledger"]}
    assert claims["F06"]["level"] == claims["A01"]["level"] == "DIAGNOSTIC_ASSOCIATION"
    assert claims["H01"]["level"] == "ATTRIBUTION_HYPOTHESIS"
    assert claims["H01"]["hypothesis"]["additional_evidence_needed"]
    cases = read_object(ROOT / CANONICAL)["slots"]
    assert len(report["badcases"]) == len(cases) == 3
    for reference, case in zip(report["badcases"], cases, strict=True):
        assert reference["run_identity"] == case["run_identity"]
        assert reference["manifest_digest"] == case["frozen_evidence"]["manifest_digest"]
        assert reference["trace_status"] == case["frozen_evidence"]["trace_status"]
        assert reference["engineering_lesson"] == case["mitigation_lesson"]
        assert "frozen_evidence" not in reference
        assert case["root_cause"] is None and case["attribution_classification"] == "OBSERVED_FACT"
        assert claims[reference["claim_id"]]["limitations"] == case["limitations"]
    assert report["badcases"][2]["trace_status"] == "NOT_REPORTED"


@pytest.mark.parametrize("mutation", ["value", "reference", "field", "root_cause"])
def test_native_assertions_reject_fabricated_evidence_even_with_canonical_prose(
    report: dict[str, Any], mutation: str
) -> None:
    altered = copy.deepcopy(report)
    claim = next(
        c
        for c in altered["claim_ledger"]
        if c["claim_id"] == ("B01" if mutation == "root_cause" else "F01")
    )
    proof = claim["proof"]
    if mutation == "root_cause":
        assertion = next(a for a in proof["assertions"] if a["field_path"][-1] == "root_cause")
        assertion["expected_value"] = "Reasoning caused failure"
    else:
        assertion = proof["assertions"][0]
        if mutation == "value":
            assertion["expected_value"]["capability_pass"] = 90
        elif mutation == "reference":
            for item in proof["assertions"]:
                item["evidence_ref"] = "cell:core-real-matrix-v6:invented"
            proof["evidence_refs"] = ["cell:core-real-matrix-v6:invented"]
        else:
            assertion["field_path"] = ["invented_outcomes"]
    proof["statement"] = canonical_fact_statement(
        tuple(FactAssertion.model_validate(a) for a in proof["assertions"])
    )
    with pytest.raises((ValueError, AttributionValidationError)):
        final.validate(altered, ROOT)


@pytest.mark.parametrize(
    "path,value",
    [
        (["claim_ledger", 0, "statement"], "Harness uplift is causally proven."),
        (["claim_ledger", 0, "causal_language_permitted"], True),
        (["claim_ledger", 0, "limitations"], []),
        (["claim_ledger", 5, "level"], "VERIFIED_FACT"),
        (["claim_ledger", 15, "level"], "VERIFIED_FACT"),
        (["controlled_attribution_claim_count"], 1),
        (["ablation", "formal_eligible"], True),
        (["kb4_approved"], True),
        (["final_gate"], "PASS"),
        (
            [
                "comparisons",
                "gpt56-relay-direct-vs-codex",
                "descriptive_statistics",
                "capability",
                "delta",
            ],
            0,
        ),
        (["timeout_sensitivity", "unknown_physical_primary_timeout_facts"], 0),
    ],
)
def test_report_rejects_prose_promotion_statistics_drift_and_silent_missingness_changes(
    report: dict[str, Any], path: list[str | int], value: Any
) -> None:
    altered = copy.deepcopy(report)
    final.select(altered, path[:-1])[path[-1]] = value
    with pytest.raises(ValueError):
        final.validate(altered, ROOT)


def test_requirement_checklist_resolves_evidence_without_approving_kb4(
    report: dict[str, Any],
) -> None:
    expected = {
        "Codex medium/high reasoning ablation": "ABLATION_EVIDENCE_PRESENT_WITH_LIMITATIONS",
        "Three real verifier-backed BadCases": "FROZEN_VERIFIED",
        "Failure taxonomy": "EVIDENCE_PRESENT",
        "Trace diagnosis": "EVIDENCE_PRESENT_WITH_LIMITATIONS",
        "Attribution report": "REPORT_COMPLETE",
    }
    assert {r["requirement"]: r["status"] for r in report["requirement_reconciliation"]} == expected
    ids = {c["claim_id"] for c in report["claim_ledger"]}
    for requirement in report["requirement_reconciliation"]:
        assert requirement["limitations"] and set(requirement["claim_ids"]) <= ids
        for ref in requirement["evidence_refs"]:
            assert ref in report["catalog_bindings"] or (ROOT / ref).is_file()
    assert report["status"] == "READY_FOR_KB4_FINAL_GATE"
    assert report["kb4_approved"] is False
    assert report["final_gate"] == report["kc"] == "NOT_RUN"


@pytest.mark.parametrize("changed", [final.MATRIX, final.TIMEOUT, CANONICAL])
def test_frozen_source_byte_drift_blocks_regeneration(tmp_path: Path, changed: str) -> None:
    # A shallow linked checkout exercises actual byte hashing without changing original evidence.
    for path in ROOT.iterdir():
        if path.name not in {"release", ".git", ".venv"}:
            (tmp_path / path.name).symlink_to(path, target_is_directory=path.is_dir())
    (tmp_path / "release").mkdir()
    for path in (ROOT / "release").iterdir():
        target = tmp_path / "release" / path.name
        if path == ROOT / changed:
            target.write_bytes(path.read_bytes() + b" ")
        else:
            target.symlink_to(path, target_is_directory=path.is_dir())
    with pytest.raises(ValueError, match="drift"):
        final.build(tmp_path)
