from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from harnesslab.cli import app
from harnesslab.comparability.engine import ComparabilityEngine, capability_pair_eligible
from harnesslab.comparability.manifest import facts_from_manifest, load_manifest_facts
from harnesslab.comparability.models import (
    ComparabilityIntent,
    ComparabilityStatus,
    ComparisonFacts,
    FieldState,
    ReasonCode,
    canonical_digest,
)
from harnesslab.contracts.common import Protocol
from harnesslab.contracts.model import ModelProfile, ReasoningProfile
from harnesslab.harness_lane.fake import FakeCodexBackend
from harnesslab.harness_lane.profile import canonical_codex_profile
from harnesslab.harness_lane.runner import CodexHarnessRunner
from harnesslab.model_lane.fake import FakeDirectProvider
from harnesslab.model_lane.runner import DirectModelRunner
from harnesslab.multi_harness.adapter import ClaudeCodeAdapter, DeepSeekHarnessAdapter
from harnesslab.multi_harness.fake import FakeMultiHarnessBackend
from harnesslab.multi_harness.profile import canonical_claude_profile, canonical_deepseek_profile
from harnesslab.multi_harness.runner import MultiHarnessRunner
from harnesslab.sandbox.models import ImageIdentity
from harnesslab.sandbox.runner import DockerSandbox
from harnesslab.tasks.package import TaskPackage

ROOT = Path(__file__).resolve().parents[1]
PYTHON_TASK = ROOT / "tasks" / "micro-python-clamp" / "1.0.0"
SHARED_REQUESTED_MODEL = "deterministic-comparison-model"


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
        "resource_envelope_identity": "sha256:" + "b" * 64,
        "network_policy": "deny",
        "harness": "left-harness",
        "harness_version": "1.0.0",
        "harness_profile_identity": "sha256:" + "6" * 64,
        "reasoning_effort": "medium",
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
        "verifier_control_identity",
        "requested_model",
        "provider_route",
        "budget_identity",
        "network_policy",
        "reasoning_effort",
    ),
)
def test_harness_uplift_hard_control_mutation_is_not_comparable(field: str) -> None:
    right = facts(evidence_identity="sha256:" + "8" * 64, **{field: "mutated"})
    report = ComparabilityEngine().assess(facts(), right, intent=ComparabilityIntent.HARNESS_UPLIFT)
    assert report.status is ComparabilityStatus.NOT_COMPARABLE
    expected_field = "verifier_control_identity" if field == "verifier_identity" else field
    assert any(
        reason.code is ReasonCode.HARD_CONTROL_MISMATCH and reason.field == expected_field
        for reason in report.reasons
    )


def test_harness_uplift_reasoning_effort_drift_is_a_blocking_hard_control() -> None:
    report = ComparabilityEngine().assess(
        facts(),
        facts(evidence_identity="sha256:" + "8" * 64, reasoning_effort="high"),
        intent=ComparabilityIntent.HARNESS_UPLIFT,
    )

    assert report.status is ComparabilityStatus.NOT_COMPARABLE
    assert any(
        reason.code is ReasonCode.HARD_CONTROL_MISMATCH and reason.field == "reasoning_effort"
        for reason in report.reasons
    )


def test_early_capability_without_verifier_execution_remains_pair_eligible() -> None:
    control = "sha256:" + "4" * 64
    execution = "sha256:" + "a" * 64
    early_failure = facts(
        verifier_identity=None,
        verifier_control_identity=control,
        verifier_execution_identity=None,
        verifier_execution_status="NOT_EXECUTED",
        verifier_control_execution_status="NOT_EXECUTED",
    )
    verified = facts(
        evidence_identity="sha256:" + "8" * 64,
        verifier_identity=execution,
        verifier_control_identity=control,
        verifier_execution_identity=execution,
        verifier_execution_status="EXECUTED",
        verifier_control_execution_status="MATCH",
    )

    report = ComparabilityEngine().assess(
        early_failure, verified, intent=ComparabilityIntent.HARNESS_UPLIFT
    )

    assert report.status is ComparabilityStatus.COMPARABLE
    assert capability_pair_eligible(report)
    execution_field = next(
        field for field in report.fields if field.field == "verifier_execution_status"
    )
    assert execution_field.state is FieldState.DIFFER


def test_harness_uplift_requires_matching_scoped_resource_envelope_identity() -> None:
    missing = ComparabilityEngine().assess(
        facts(resource_envelope_identity=None),
        facts(evidence_identity="sha256:" + "8" * 64, resource_envelope_identity=None),
        intent=ComparabilityIntent.HARNESS_UPLIFT,
    )
    mismatched = ComparabilityEngine().assess(
        facts(),
        facts(
            evidence_identity="sha256:" + "8" * 64,
            resource_envelope_identity="sha256:" + "c" * 64,
        ),
        intent=ComparabilityIntent.HARNESS_UPLIFT,
    )

    assert missing.status is ComparabilityStatus.NOT_COMPARABLE
    assert mismatched.status is ComparabilityStatus.NOT_COMPARABLE
    assert any(reason.code is ReasonCode.RESOURCE_ENVELOPE_MISSING for reason in missing.reasons)
    assert any(
        reason.code is ReasonCode.RESOURCE_ENVELOPE_MISMATCH for reason in mismatched.reasons
    )


def test_missing_verifier_control_remains_conservatively_blocking() -> None:
    missing_control = facts(
        verifier_identity=None,
        verifier_control_identity=None,
        verifier_execution_identity=None,
        verifier_execution_status="NOT_EXECUTED",
        verifier_control_execution_status="NOT_EXECUTED",
    )
    report = ComparabilityEngine().assess(
        missing_control,
        facts(evidence_identity="sha256:" + "8" * 64),
        intent=ComparabilityIntent.HARNESS_UPLIFT,
    )

    assert report.status is ComparabilityStatus.NOT_COMPARABLE
    assert not capability_pair_eligible(report)
    assert any(
        reason.code is ReasonCode.HARD_CONTROL_MISSING
        and reason.field == "verifier_control_identity"
        for reason in report.reasons
    )


def test_actual_verifier_drift_blocks_even_when_frozen_controls_match() -> None:
    control = "sha256:" + "4" * 64
    left = facts(
        verifier_control_identity=control,
        verifier_execution_identity="sha256:" + "a" * 64,
        verifier_execution_status="EXECUTED",
        verifier_control_execution_status="MATCH",
    )
    right = facts(
        evidence_identity="sha256:" + "8" * 64,
        verifier_control_identity=control,
        verifier_execution_identity="sha256:" + "b" * 64,
        verifier_execution_status="EXECUTED",
        verifier_control_execution_status="MATCH",
    )
    report = ComparabilityEngine().assess(left, right, intent=ComparabilityIntent.HARNESS_UPLIFT)

    assert report.status is ComparabilityStatus.NOT_COMPARABLE
    assert not capability_pair_eligible(report)
    assert any(reason.code is ReasonCode.VERIFIER_EXECUTION_MISMATCH for reason in report.reasons)


def test_executed_verifier_disagreeing_with_control_blocks() -> None:
    report = ComparabilityEngine().assess(
        facts(verifier_control_execution_status="MISMATCH"),
        facts(evidence_identity="sha256:" + "8" * 64),
        intent=ComparabilityIntent.HARNESS_UPLIFT,
    )

    assert report.status is ComparabilityStatus.NOT_COMPARABLE
    assert any(
        reason.code is ReasonCode.VERIFIER_CONTROL_EXECUTION_MISMATCH for reason in report.reasons
    )


def test_codex_split_sandbox_network_control_fails_closed_on_actual_policy_drift() -> None:
    manifest = {
        "schema_version": 1,
        "harness": "codex",
        "profile": {
            "harness": "codex",
            "tool_network_policy": "deny",
            "codex_inner_network_policy": "deny",
            "codex_inner_network_enforcement": "seccomp",
            "filesystem_enforcement": "outer-docker",
        },
    }
    controlled = facts_from_manifest(manifest)
    assert controlled.network_policy == "deny"

    broadened = json.loads(json.dumps(manifest))
    broadened["profile"]["codex_inner_network_policy"] = "allowlist"
    broadened_facts = facts_from_manifest(broadened)
    assert broadened_facts.network_policy is None
    report = ComparabilityEngine().assess(
        facts(), broadened_facts, intent=ComparabilityIntent.HARNESS_UPLIFT
    )
    assert report.status is ComparabilityStatus.NOT_COMPARABLE
    assert any(
        reason.code is ReasonCode.HARD_CONTROL_MISSING and reason.field == "network_policy"
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


def test_native_harness_system_comparison_remains_reportable_without_aggregate_envelope() -> None:
    report = ComparabilityEngine().assess(
        facts(resource_envelope_identity=None),
        facts(
            evidence_identity="sha256:" + "8" * 64,
            harness="right-harness",
            harness_version="2.0.0",
            harness_profile_identity="sha256:" + "9" * 64,
            prompt_identity="sha256:" + "a" * 64,
            resource_envelope_identity=None,
        ),
        intent=ComparabilityIntent.NATIVE_HARNESS_SYSTEM_COMPARISON,
    )

    assert report.status is not ComparabilityStatus.NOT_COMPARABLE
    assert not any(reason.code is ReasonCode.RESOURCE_ENVELOPE_MISSING for reason in report.reasons)


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


def controlled_facts(**changes: str | None) -> ComparisonFacts:
    values: dict[str, object] = {
        **facts().model_dump(mode="python"),
        "verifier_control_identity": "sha256:" + "4" * 64,
        "verifier_execution_identity": "sha256:" + "d" * 64,
        "verifier_execution_status": "EXECUTED",
        "verifier_control_execution_status": "MATCH",
        "provider_config_identity": "sha256:" + "e" * 64,
        "harness_image_identity": "sha256:" + "f" * 64,
        "runner_contract": "phase-k-real-codex-v1",
        "credential_reference_identity": "HARNESSLAB_GPT56_RELAY_API_KEY",
        "tool_policy_identity": "sha256:" + "a" * 64,
        "mcp_policy_identity": "sha256:" + "c" * 64,
        "reasoning_effort": "medium",
    }
    values.update(changes)
    return ComparisonFacts.model_validate(values)


def test_controlled_ablation_models_reasoning_effort_as_the_only_treatment() -> None:
    left = controlled_facts(observed_model=None)
    right = controlled_facts(
        evidence_identity="sha256:" + "8" * 64,
        observed_model=None,
        reasoning_effort="high",
    )
    report = ComparabilityEngine().assess(
        left, right, intent=ComparabilityIntent.CONTROLLED_ABLATION
    )

    assert report.status is ComparabilityStatus.COMPARABLE
    assert any(
        field.field == "reasoning_effort" and field.state is FieldState.INTENDED_DIFFERENCE
        for field in report.fields
    )
    assert any(
        reason.code is ReasonCode.OPERATOR_TRUSTED_ROUTE_MODEL_NOT_RUNTIME_EXPOSED
        for reason in report.reasons
    )
    assert left.observed_model is None and right.observed_model is None


@pytest.mark.parametrize(
    "field",
    (
        "task_id",
        "task_version",
        "task_digest",
        "workspace_input_digest",
        "context_identity",
        "verifier_control_identity",
        "verifier_execution_identity",
        "requested_model",
        "provider_route",
        "provider_config_identity",
        "budget_identity",
        "resource_envelope_identity",
        "network_policy",
        "harness",
        "harness_version",
        "harness_profile_identity",
        "harness_image_identity",
        "runner_contract",
        "prompt_identity",
        "credential_reference_identity",
        "tool_policy_identity",
        "mcp_policy_identity",
        "trace_coverage",
    ),
)
def test_controlled_ablation_blocks_every_non_treatment_hard_control_drift(
    field: str,
) -> None:
    left = controlled_facts(observed_model=None)
    right = controlled_facts(
        evidence_identity="sha256:" + "8" * 64,
        observed_model=None,
        reasoning_effort="high",
        **{field: "mutated"},
    )
    report = ComparabilityEngine().assess(
        left, right, intent=ComparabilityIntent.CONTROLLED_ABLATION
    )
    assert report.status is ComparabilityStatus.NOT_COMPARABLE


def test_controlled_ablation_blocks_explicit_or_asymmetric_observed_model_identity() -> None:
    left = controlled_facts(observed_model="same-model")
    exposed_mismatch = controlled_facts(
        evidence_identity="sha256:" + "8" * 64,
        reasoning_effort="high",
        observed_model="other-model",
    )
    asymmetric = exposed_mismatch.model_copy(update={"observed_model": None})

    for right in (exposed_mismatch, asymmetric):
        report = ComparabilityEngine().assess(
            left, right, intent=ComparabilityIntent.CONTROLLED_ABLATION
        )
        assert report.status is ComparabilityStatus.NOT_COMPARABLE


@pytest.mark.parametrize("missing_side", ("left", "right", "both"))
def test_model_comparison_missing_requested_model_is_not_comparable(missing_side: str) -> None:
    left = facts(requested_model=None) if missing_side in {"left", "both"} else facts()
    right = facts(evidence_identity="sha256:" + "8" * 64)
    if missing_side in {"right", "both"}:
        right = facts(evidence_identity="sha256:" + "8" * 64, requested_model=None)

    report = ComparabilityEngine().assess(left, right, intent=ComparabilityIntent.MODEL_COMPARISON)

    assert report.status is ComparabilityStatus.NOT_COMPARABLE
    assert any(
        reason.code is ReasonCode.REQUESTED_MODEL_MISSING and reason.field == "requested_model"
        for reason in report.reasons
    )


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
        "resource_budget_contract": {
            "max_wall_time": {
                "status": "ENFORCED",
                "value": 60,
                "unit": "seconds",
                "scopes": ["PER_LOGICAL_RUN"],
            },
            "max_output_tokens": {
                "status": "ENFORCED",
                "value": 1000,
                "unit": "tokens",
                "scopes": ["PER_PROVIDER_REQUEST", "PER_LOGICAL_RUN"],
            },
            "max_model_turns": {
                "status": "ENFORCED",
                "value": 1,
                "unit": "turns",
                "scopes": ["PER_LOGICAL_RUN"],
            },
            "max_tool_calls": {
                "status": "ENFORCED",
                "value": 0,
                "unit": "calls",
                "scopes": ["PER_LOGICAL_RUN"],
            },
            "max_provider_requests": {
                "status": "ENFORCED",
                "value": 1,
                "unit": "requests",
                "scopes": ["PER_LOGICAL_RUN"],
            },
            "max_cost": {
                "status": "NOT_AVAILABLE",
                "value": None,
                "unit": "USD",
                "scopes": ["NOT_AVAILABLE"],
            },
        },
        "workspace_input_digest": "sha256:" + "4" * 64,
        "context_digest": None,
        "prompt_hash": "sha256:" + ("5" if harness == "left" else "6") * 64,
        "harness": harness,
        "profile": {
            "cli_version": "1.0.0" if harness == "left" else "2.0.0",
            "network_policy": "deny",
            "provider_route": "same-route",
            "requested_model": "same-model",
            "reasoning_effort": "medium",
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
    planned = facts_from_manifest(old_direct, verifier_control_identity="sha256:" + "a" * 64)
    assert planned.verifier_control_identity == "sha256:" + "a" * 64
    assert planned.verifier_execution_identity is None
    assert planned.verifier_execution_status == "NOT_EXECUTED"
    assert planned.verifier_control_execution_status == "NOT_EXECUTED"
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(phase_f_manifest("left")), encoding="utf-8")
    assert load_manifest_facts(path).verifier_identity is not None


def test_manifest_loader_exposes_executed_verifier_control_drift() -> None:
    manifest = phase_f_manifest("left")
    facts = facts_from_manifest(manifest, verifier_control_identity="sha256:" + "a" * 64)

    assert facts.verifier_execution_identity is not None
    assert facts.verifier_execution_status == "EXECUTED"
    assert facts.verifier_control_execution_status == "MISMATCH"


def test_new_codex_manifest_trace_coverage_is_consumed_without_inference() -> None:
    manifest = phase_f_manifest("codex")
    manifest["trace_coverage"] = "FULL_STREAM"
    assert facts_from_manifest(manifest).trace_coverage == "FULL_STREAM"


@pytest.mark.asyncio
async def test_real_runner_persisted_manifests_supply_comparability_controls(
    tmp_path: Path,
) -> None:
    package = TaskPackage.load(PYTHON_TASK)
    sandbox = DockerSandbox(
        artifact_root=tmp_path / "sandbox-artifacts",
        runtime_root=tmp_path / "sandbox-runtime",
    )
    direct_patch = json.dumps(
        {
            "schema_version": 1,
            "operations": [
                {
                    "op": "write",
                    "path": "calculator.py",
                    "content": (
                        "def clamp(value: int, lower: int, upper: int) -> int:\n"
                        "    return max(lower, min(value, upper))\n"
                    ),
                }
            ],
        },
        separators=(",", ":"),
    )
    direct_profile = ModelProfile(
        requested_model=SHARED_REQUESTED_MODEL,
        provider="fake-direct-provider",
        base_url="https://fake-provider.invalid/v1",
        route="/responses",
        protocol=Protocol.RESPONSES,
        reasoning=ReasoningProfile(effort="low", max_output_tokens=1000),
    )
    phase_d = await DirectModelRunner(
        artifact_root=tmp_path / "phase-d-artifacts",
        runtime_root=tmp_path / "phase-d-runtime",
        sandbox=sandbox,
        environment={},
    ).run(
        PYTHON_TASK,
        direct_profile,
        adapter=FakeDirectProvider(direct_patch, observed_model=SHARED_REQUESTED_MODEL),
        run_id="comparability-phase-d",
    )

    phase_e = await CodexHarnessRunner(
        artifact_root=tmp_path / "phase-e-artifacts",
        runtime_root=tmp_path / "phase-e-runtime",
        sandbox=sandbox,
    ).run(
        PYTHON_TASK,
        canonical_codex_profile(
            ImageIdentity(
                reference="fake-codex:phase-e",
                image_id="sha256:" + "1" * 64,
            ),
            requested_model=SHARED_REQUESTED_MODEL,
            execution_timeout_seconds=30,
        ),
        backend=FakeCodexBackend(),
        run_id="comparability-phase-e-codex",
    )

    phase_f_runner = MultiHarnessRunner(
        artifact_root=tmp_path / "phase-f-artifacts",
        runtime_root=tmp_path / "phase-f-runtime",
        sandbox=sandbox,
    )
    claude_profile = canonical_claude_profile(
        ImageIdentity(
            reference="fake-claude:phase-f",
            image_id="sha256:" + "2" * 64,
        ),
        requested_model=SHARED_REQUESTED_MODEL,
        execution_timeout_seconds=30,
    )
    phase_f_claude = await phase_f_runner.run(
        PYTHON_TASK,
        claude_profile,
        adapter=ClaudeCodeAdapter(),
        backend=FakeMultiHarnessBackend(),
        run_id="comparability-phase-f-claude",
    )
    deepseek_config_digest = "sha256:" + "4" * 64
    deepseek_profile = canonical_deepseek_profile(
        ImageIdentity(
            reference="fake-deepseek:phase-f",
            image_id="sha256:" + "3" * 64,
        ),
        deepseek_config_digest,
        requested_model=SHARED_REQUESTED_MODEL,
        execution_timeout_seconds=30,
    )
    phase_f_deepseek = await phase_f_runner.run(
        PYTHON_TASK,
        deepseek_profile,
        adapter=DeepSeekHarnessAdapter(observed_config_digest=deepseek_config_digest),
        backend=FakeMultiHarnessBackend(),
        run_id="comparability-phase-f-deepseek",
    )

    assert phase_d.evidence.verifier_passed is True
    assert phase_e.evidence.verifier_passed is True
    assert phase_f_claude.evidence.verifier_passed is True
    assert phase_f_deepseek.evidence.verifier_passed is True
    manifest_paths = {
        "phase-d": phase_d.artifact_directory / "manifest.json",
        "phase-e-codex": phase_e.artifact_directory / "manifest.json",
        "phase-f-claude": phase_f_claude.artifact_directory / "manifest.json",
        "phase-f-deepseek": phase_f_deepseek.artifact_directory / "manifest.json",
    }
    loaded: dict[str, ComparisonFacts] = {}
    for name, manifest_path in manifest_paths.items():
        assert manifest_path.is_file(), name
        loaded[name] = load_manifest_facts(manifest_path)

    common_fields = (
        "task_id",
        "task_version",
        "task_digest",
        "workspace_input_digest",
        "context_identity",
        "verifier_identity",
        "budget_identity",
        "network_policy",
        "requested_model",
    )
    for field in common_fields:
        values = {getattr(item, field) for item in loaded.values()}
        assert None not in values, field
        assert len(values) == 1, (field, values)
    assert loaded["phase-d"].task_id == package.definition.id
    assert loaded["phase-d"].task_version == package.definition.version
    assert loaded["phase-d"].task_digest == package.definition.content_digest
    assert loaded["phase-d"].requested_model == SHARED_REQUESTED_MODEL

    pairs = (
        ("phase-d", "phase-e-codex"),
        ("phase-d", "phase-f-claude"),
        ("phase-e-codex", "phase-f-claude"),
        ("phase-f-claude", "phase-f-deepseek"),
    )
    for left, right in pairs:
        report = ComparabilityEngine().assess(
            loaded[left], loaded[right], intent=ComparabilityIntent.HARNESS_UPLIFT
        )
        assert report.status is ComparabilityStatus.NOT_COMPARABLE
        assert any(
            reason.field == "reasoning_effort"
            and reason.code in {ReasonCode.HARD_CONTROL_MISSING, ReasonCode.HARD_CONTROL_MISMATCH}
            for reason in report.reasons
        )
        assert any(
            reason.code is ReasonCode.HARD_CONTROL_MISMATCH and reason.field == "provider_route"
            for reason in report.reasons
        )

    assert any(
        reason.code is ReasonCode.OBSERVED_MODEL_MISMATCH
        for reason in ComparabilityEngine()
        .assess(
            loaded["phase-d"],
            loaded["phase-f-claude"],
            intent=ComparabilityIntent.HARNESS_UPLIFT,
        )
        .reasons
    )
    assert any(
        reason.code is ReasonCode.OBSERVED_MODEL_MISSING
        for reason in ComparabilityEngine()
        .assess(
            loaded["phase-e-codex"],
            loaded["phase-f-claude"],
            intent=ComparabilityIntent.HARNESS_UPLIFT,
        )
        .reasons
    )


def test_actual_profile_requested_model_is_not_double_counted_as_a_control() -> None:
    left = phase_f_manifest("left")
    right = json.loads(json.dumps(left))
    right["requested_model"] = "other-requested"
    right["observed_model"] = "other-observed"
    right_profile = right["profile"]
    assert isinstance(right_profile, dict)
    right_profile["requested_model"] = "other-requested"
    right["profile_hash"] = "sha256:" + "a" * 64

    report = ComparabilityEngine().assess(
        facts_from_manifest(left),
        facts_from_manifest(right),
        intent=ComparabilityIntent.MODEL_COMPARISON,
    )

    assert report.status is ComparabilityStatus.COMPARABLE
    profile_field = next(
        field for field in report.fields if field.field == "harness_profile_identity"
    )
    assert profile_field.state is FieldState.MATCH


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
