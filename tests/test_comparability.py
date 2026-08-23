from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from harnesslab.cli import app
from harnesslab.comparability.engine import ComparabilityEngine
from harnesslab.comparability.manifest import facts_from_manifest, load_manifest_facts
from harnesslab.comparability.models import (
    ComparabilityIntent,
    ComparabilityStatus,
    ComparisonFacts,
    FieldState,
    ReasonCode,
    canonical_digest,
)


def facts(**changes: str | None) -> ComparisonFacts:
    values: dict[str, str | None] = {
        "evidence_identity": "sha256:" + "1" * 64,
        "task_id": "micro-python-clamp",
        "task_version": "1.0.0",
        "task_digest": "sha256:" + "2" * 64,
        "workspace_input_digest": "sha256:" + "3" * 64,
        "context_identity": "NONE",
        "verifier_identity": "sha256:" + "4" * 64,
        "requested_model": "same-model",
        "observed_model": "same-model",
        "provider_route": "same-provider-route",
        "budget_identity": "sha256:" + "5" * 64,
        "network_policy": "deny",
        "harness": "left-harness",
        "harness_version": "1.0.0",
        "harness_profile_identity": "sha256:" + "6" * 64,
        "prompt_identity": "sha256:" + "7" * 64,
        "trace_coverage": "FULL_STREAM",
    }
    values.update(changes)
    return ComparisonFacts.model_validate(values)


def test_harness_uplift_treatments_are_comparable_when_controls_match() -> None:
    right = facts(
        evidence_identity="sha256:" + "8" * 64,
        harness="right-harness",
        harness_version="2.0.0",
        harness_profile_identity="sha256:" + "9" * 64,
        prompt_identity="sha256:" + "a" * 64,
    )
    report = ComparabilityEngine().assess(facts(), right, intent=ComparabilityIntent.HARNESS_UPLIFT)

    assert report.status is ComparabilityStatus.COMPARABLE
    treatment_fields = {
        field.field for field in report.fields if field.state is FieldState.INTENDED_DIFFERENCE
    }
    assert treatment_fields == {
        "harness",
        "harness_version",
        "harness_profile_identity",
        "prompt_identity",
    }


@pytest.mark.parametrize(
    "field",
    (
        "task_id",
        "task_version",
        "task_digest",
        "workspace_input_digest",
        "context_identity",
        "verifier_identity",
        "requested_model",
        "provider_route",
        "budget_identity",
        "network_policy",
    ),
)
def test_harness_uplift_hard_control_mutation_is_not_comparable(field: str) -> None:
    right = facts(evidence_identity="sha256:" + "8" * 64, **{field: "mutated"})
    report = ComparabilityEngine().assess(facts(), right, intent=ComparabilityIntent.HARNESS_UPLIFT)
    assert report.status is ComparabilityStatus.NOT_COMPARABLE
    assert any(
        reason.code is ReasonCode.HARD_CONTROL_MISMATCH and reason.field == field
        for reason in report.reasons
    )


def test_missing_observed_model_is_partial_but_mismatch_blocks_uplift() -> None:
    partial = ComparabilityEngine().assess(
        facts(),
        facts(evidence_identity="sha256:" + "8" * 64, observed_model=None),
        intent=ComparabilityIntent.HARNESS_UPLIFT,
    )
    blocked = ComparabilityEngine().assess(
        facts(),
        facts(evidence_identity="sha256:" + "8" * 64, observed_model="another-model"),
        intent=ComparabilityIntent.HARNESS_UPLIFT,
    )
    assert partial.status is ComparabilityStatus.PARTIALLY_COMPARABLE
    assert blocked.status is ComparabilityStatus.NOT_COMPARABLE
    assert any(reason.code is ReasonCode.OBSERVED_MODEL_MISSING for reason in partial.reasons)
    assert any(reason.code is ReasonCode.OBSERVED_MODEL_MISMATCH for reason in blocked.reasons)


def test_requested_observed_mismatch_blocks_uplift_even_when_both_sides_match() -> None:
    report = ComparabilityEngine().assess(
        facts(observed_model="routed-other"),
        facts(evidence_identity="sha256:" + "8" * 64, observed_model="routed-other"),
        intent=ComparabilityIntent.HARNESS_UPLIFT,
    )
    assert report.status is ComparabilityStatus.NOT_COMPARABLE
    assert any(reason.code is ReasonCode.REQUESTED_OBSERVED_MISMATCH for reason in report.reasons)


def test_trace_coverage_mismatch_is_partial_not_automatic_invalidation() -> None:
    report = ComparabilityEngine().assess(
        facts(),
        facts(
            evidence_identity="sha256:" + "8" * 64,
            trace_coverage="FINAL_OUTPUT_ONLY",
        ),
        intent=ComparabilityIntent.HARNESS_UPLIFT,
    )
    assert report.status is ComparabilityStatus.PARTIALLY_COMPARABLE
    assert any(reason.code is ReasonCode.TRACE_COVERAGE_LIMITED for reason in report.reasons)


def test_model_comparison_treats_model_identity_difference_as_intended() -> None:
    report = ComparabilityEngine().assess(
        facts(),
        facts(
            evidence_identity="sha256:" + "8" * 64,
            requested_model="other-requested",
            observed_model="other-observed",
        ),
        intent=ComparabilityIntent.MODEL_COMPARISON,
    )
    assert report.status is ComparabilityStatus.COMPARABLE


def phase_f_manifest(harness: str) -> dict[str, object]:
    return {
        "task_id": "micro-python-clamp",
        "task_version": "1.0.0",
        "task_digest": "sha256:" + "2" * 64,
        "verifier_definition_digest": "sha256:" + "3" * 64,
        "resource_budget": {
            "timeout_seconds": 60,
            "max_output_tokens": 1000,
            "network_policy": "deny",
        },
        "workspace_input_digest": "sha256:" + "4" * 64,
        "context_digest": None,
        "prompt_hash": "sha256:" + ("5" if harness == "left" else "6") * 64,
        "harness": harness,
        "profile": {
            "cli_version": "1.0.0" if harness == "left" else "2.0.0",
            "network_policy": "deny",
        },
        "profile_hash": "sha256:" + ("7" if harness == "left" else "8") * 64,
        "requested_model": "same-model",
        "observed_model": "same-model",
        "provider_route": "same-route",
        "trace_coverage": "FULL_STREAM",
        "verifier_sandbox_manifest": {
            "role": "verifier",
            "image": {"image_id": "sha256:" + "9" * 64},
        },
    }


def test_manifest_loader_consumes_phase_f_and_older_lane_shapes_without_inference(
    tmp_path: Path,
) -> None:
    old_direct = {
        "task_id": "t",
        "task_version": "1.0.0",
        "task_digest": "sha256:" + "1" * 64,
        "workspace_input_digest": "sha256:" + "2" * 64,
        "context_digest": None,
        "prompt_hash": "sha256:" + "3" * 64,
        "requested_model": "model",
        "observed_model": None,
        "provider": "provider",
        "endpoint": "https://provider.invalid/v1/responses",
        "protocol": "responses",
        "generation_settings": {"request_timeout_seconds": 30, "attempt_count": 1},
    }
    parsed = facts_from_manifest(old_direct)
    assert parsed.harness == "direct-model"
    assert parsed.context_identity == "NONE"
    assert parsed.verifier_identity is None
    assert parsed.network_policy is None
    assert parsed.trace_coverage is None
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(phase_f_manifest("left")), encoding="utf-8")
    assert load_manifest_facts(path).verifier_identity is not None


def test_compare_cli_emits_deterministic_json_and_text(tmp_path: Path) -> None:
    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    left.write_text(json.dumps(phase_f_manifest("left")), encoding="utf-8")
    right.write_text(json.dumps(phase_f_manifest("right")), encoding="utf-8")
    runner = CliRunner()

    text_result = runner.invoke(
        app, ["compare", "assess", str(left), str(right), "--intent", "harness-uplift"]
    )
    json_result = runner.invoke(
        app,
        [
            "compare",
            "assess",
            str(left),
            str(right),
            "--intent",
            "harness-uplift",
            "--json",
        ],
    )

    assert text_result.exit_code == 0
    assert "status=COMPARABLE" in text_result.stdout
    payload = json.loads(json_result.stdout)
    assert payload["status"] == "COMPARABLE"
    assert payload["left_evidence_identity"] == canonical_digest(phase_f_manifest("left"))
