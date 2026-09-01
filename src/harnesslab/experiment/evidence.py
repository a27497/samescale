from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from harnesslab.comparability.models import ComparisonFacts
from harnesslab.experiment.plan import ExperimentRunSlot


class ManifestControlMismatch(RuntimeError):
    """Persisted lane evidence does not represent the immutable planned treatment."""

    def __init__(self, mismatches: tuple[str, ...]) -> None:
        self.mismatches = mismatches
        super().__init__(
            "persisted manifest disagrees with immutable plan controls: " + ",".join(mismatches)
        )


def validate_manifest_against_slot(
    raw: Mapping[str, Any], facts: ComparisonFacts, slot: ExperimentRunSlot
) -> None:
    """Apply one control-identity policy at execution and report-read time."""

    expected: dict[str, str | None] = {
        "task_id": slot.task.task_id,
        "task_version": slot.task.task_version,
        "task_digest": slot.task.task_digest,
        "workspace_input_digest": slot.task.workspace_input_digest,
        "context_identity": slot.task.context_identity or "NONE",
        "requested_model": slot.requested_model,
        "provider_route": slot.provider_route,
        "budget_identity": slot.task.budget_identity,
        "network_policy": slot.task.network_policy.value,
        "harness": slot.harness,
        "harness_version": slot.harness_version,
        "harness_profile_identity": slot.profile_identity,
    }
    mismatches: list[str] = []
    for name, value in expected.items():
        actual = getattr(facts, name)
        if name == "harness" and value == "deepseek" and actual == "deepseek-harness":
            # The frozen release plan names the runtime family; Phase F evidence carries the
            # producer's HarnessKind value. This one-way alias does not change logical slot IDs.
            continue
        if actual != value:
            mismatches.append(name)
    if (
        raw.get("verifier_sandbox_manifest") is not None
        and raw.get("verifier_definition_digest") != slot.task.verifier_identity
    ):
        mismatches.append("verifier_control_identity")
    if facts.verifier_control_execution_status == "MISMATCH":
        mismatches.append("verifier_control_execution_identity")
    plan_harness_config_identity = raw.get("plan_harness_config_identity")
    profile_hash = raw.get("profile_hash")
    if plan_harness_config_identity is not None:
        if plan_harness_config_identity != slot.harness_config_identity:
            mismatches.append("harness_config_identity")
    elif profile_hash is not None and profile_hash != slot.harness_config_identity:
        mismatches.append("harness_config_identity")
    generation = raw.get("generation_settings")
    profile = raw.get("profile")
    actual_effort: object = None
    if isinstance(generation, dict):
        actual_effort = generation.get("effort")
    elif isinstance(profile, dict):
        actual_effort = profile.get("reasoning_effort")
    if actual_effort != slot.reasoning_effort:
        mismatches.append("reasoning_effort")
    if mismatches:
        raise ManifestControlMismatch(tuple(sorted(set(mismatches))))
