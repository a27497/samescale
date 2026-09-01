from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from harnesslab.comparability.models import ComparisonFacts, canonical_digest
from harnesslab.experiment.methodology import (
    BudgetContract,
    BudgetFairnessClass,
    classify_budget_fairness,
)


class ComparabilityInputError(ValueError):
    """An evidence manifest cannot supply a trustworthy comparison input."""


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ComparabilityInputError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _context_identity(raw: dict[str, Any]) -> str | None:
    if "context_digest" not in raw:
        return None
    return _string(raw.get("context_digest")) or "NONE"


def _verifier_execution_identity(raw: dict[str, Any]) -> str | None:
    definition = _string(raw.get("verifier_definition_digest"))
    manifest = _mapping(raw.get("verifier_sandbox_manifest"))
    image = _mapping(manifest.get("image"))
    image_id = _string(image.get("image_id"))
    if definition is None or image_id is None:
        return None
    return canonical_digest(
        {
            "definition_digest": definition,
            "image_id": image_id,
            "role": _string(manifest.get("role")),
        }
    )


def _profile_identity(raw: dict[str, Any], profile: dict[str, Any]) -> str | None:
    if profile:
        controls = dict(profile)
        controls.pop("requested_model", None)
        # reasoning_effort is compared explicitly by intent: a hard control for
        # HARNESS_UPLIFT and the sole treatment for CONTROLLED_ABLATION. The
        # complete executable profile remains bound by profile_hash.
        controls.pop("reasoning_effort", None)
        return canonical_digest(controls)
    if "provider" not in raw:
        return None
    controls = {
        "provider": raw.get("provider"),
        "endpoint_identity": raw.get("endpoint_identity", raw.get("endpoint")),
        "protocol": raw.get("protocol"),
        "generation_settings": raw.get("generation_settings"),
    }
    return canonical_digest(controls)


def _provider_config_identity(raw: dict[str, Any], profile: dict[str, Any]) -> str | None:
    configured = _string(profile.get("provider_config_digest"))
    if configured is not None:
        return configured
    provider = _string(raw.get("provider"))
    route = _string(raw.get("provider_route"))
    protocol = _string(raw.get("protocol"))
    if provider is None and route is None:
        return None
    return canonical_digest({"provider": provider, "route": route, "protocol": protocol})


def _harness_image_identity(profile: dict[str, Any]) -> str | None:
    for name in ("codex_image", "claude_image", "deepseek_image", "image"):
        image = _mapping(profile.get(name))
        if image:
            return canonical_digest(image)
    return None


def _tool_policy_identity(profile: dict[str, Any]) -> str | None:
    names = (
        "tool_network_policy",
        "web_search_policy",
        "effective_filesystem_policy",
        "filesystem_enforcement",
        "codex_inner_filesystem_policy",
        "codex_inner_network_policy",
        "codex_inner_network_enforcement",
        "shell_tool_environment_policy",
        "subject_toolchain_profile",
    )
    controls = {name: profile[name] for name in names if name in profile}
    return canonical_digest(controls) if controls else None


def _mcp_policy_identity(profile: dict[str, Any]) -> str | None:
    names = ("mcp_profile", "external_skill_plugin_profile")
    controls = {name: profile[name] for name in names if name in profile}
    return canonical_digest(controls) if controls else None


def _effective_network_policy(profile: dict[str, Any]) -> str | None:
    declared = _string(profile.get("network_policy")) or _string(profile.get("tool_network_policy"))
    split_controls = (
        "codex_inner_network_policy",
        "codex_inner_network_enforcement",
        "filesystem_enforcement",
    )
    if not any(name in profile for name in split_controls):
        return declared
    if (
        declared != "deny"
        or _string(profile.get("codex_inner_network_policy")) != "deny"
        or _string(profile.get("codex_inner_network_enforcement")) != "seccomp"
    ):
        return None
    return declared


def _resource_envelope_identity(raw: dict[str, Any]) -> str | None:
    envelope = raw.get("resource_budget_contract")
    if not isinstance(envelope, dict):
        return None
    try:
        contract = BudgetContract.model_validate(envelope)
    except ValueError:
        return None
    if (
        classify_budget_fairness(contract, contract)
        is not BudgetFairnessClass.RESOURCE_NORMALIZED_COMPARISON
    ):
        return None
    return contract.identity


def facts_from_manifest(
    raw: dict[str, Any], *, verifier_control_identity: str | None = None
) -> ComparisonFacts:
    profile = _mapping(raw.get("profile"))
    generation = _mapping(raw.get("generation_settings"))
    harness = _string(raw.get("harness"))
    if harness is None and "provider" in raw:
        harness = "direct-model"
    version = _string(profile.get("cli_version")) or _string(profile.get("codex_cli_version"))
    if version is None and harness == "direct-model":
        schema_version = raw.get("schema_version")
        if isinstance(schema_version, int) and not isinstance(schema_version, bool):
            version = f"evidence-schema-{schema_version}"
    route = _string(raw.get("provider_route"))
    if route is None and "provider" in raw:
        provider = _string(raw.get("provider"))
        endpoint = _string(raw.get("endpoint_identity")) or _string(raw.get("endpoint"))
        protocol = _string(raw.get("protocol"))
        if provider and endpoint and protocol:
            route = endpoint if "|" in endpoint else f"{provider}|{protocol}|{endpoint}"
    budget = raw.get("resource_budget")
    if not isinstance(budget, dict) and generation:
        budget = generation
    network = None
    if isinstance(budget, dict):
        network = _string(budget.get("network_policy"))
    if network is None:
        network = _effective_network_policy(profile)
    elif profile and any(
        name in profile
        for name in (
            "codex_inner_network_policy",
            "codex_inner_network_enforcement",
            "filesystem_enforcement",
        )
    ):
        profile_network = _effective_network_policy(profile)
        if profile_network != network:
            network = None
    observed = _string(raw.get("observed_model"))
    verifier_definition = _string(raw.get("verifier_definition_digest"))
    verifier_execution = _verifier_execution_identity(raw)
    effective_verifier_control: str | None
    verifier_control_execution_status: Literal["MATCH", "MISMATCH", "NOT_EXECUTED"]
    if verifier_control_identity is None and verifier_execution is not None:
        effective_verifier_control = verifier_execution
        verifier_control_execution_status = "MATCH"
    else:
        effective_verifier_control = verifier_control_identity
        if verifier_execution is None:
            verifier_control_execution_status = "NOT_EXECUTED"
        elif verifier_definition == verifier_control_identity:
            verifier_control_execution_status = "MATCH"
        else:
            verifier_control_execution_status = "MISMATCH"
    return ComparisonFacts(
        evidence_identity=canonical_digest(raw),
        task_id=_string(raw.get("task_id")),
        task_version=_string(raw.get("task_version")),
        task_digest=_string(raw.get("task_digest")),
        workspace_input_digest=_string(raw.get("workspace_input_digest")),
        context_identity=_context_identity(raw),
        verifier_identity=verifier_execution,
        verifier_control_identity=effective_verifier_control,
        verifier_execution_identity=verifier_execution,
        verifier_execution_status=(
            "EXECUTED" if verifier_execution is not None else "NOT_EXECUTED"
        ),
        verifier_control_execution_status=verifier_control_execution_status,
        requested_model=_string(raw.get("requested_model")),
        observed_model=observed,
        provider_route=route,
        budget_identity=canonical_digest(budget) if isinstance(budget, dict) else None,
        resource_envelope_identity=_resource_envelope_identity(raw),
        network_policy=network,
        harness=harness,
        harness_version=version,
        harness_profile_identity=(
            _string(raw.get("plan_profile_identity")) or _profile_identity(raw, profile)
        ),
        provider_config_identity=_provider_config_identity(raw, profile),
        harness_image_identity=_harness_image_identity(profile),
        credential_reference_identity=(
            _string(profile.get("provider_credential_reference"))
            or _string(profile.get("credential_reference"))
        ),
        tool_policy_identity=_tool_policy_identity(profile),
        mcp_policy_identity=_mcp_policy_identity(profile),
        reasoning_effort=(
            _string(profile.get("reasoning_effort")) or _string(generation.get("effort"))
        ),
        prompt_identity=_string(raw.get("prompt_hash")),
        trace_coverage=_string(raw.get("trace_coverage")),
    )


def load_manifest_facts(
    path: Path, *, verifier_control_identity: str | None = None
) -> ComparisonFacts:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except ComparabilityInputError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ComparabilityInputError(f"invalid evidence manifest: {type(exc).__name__}") from exc
    if not isinstance(raw, dict):
        raise ComparabilityInputError("evidence manifest must contain a JSON object")
    try:
        return facts_from_manifest(raw, verifier_control_identity=verifier_control_identity)
    except (TypeError, ValueError) as exc:
        raise ComparabilityInputError(f"invalid evidence facts: {type(exc).__name__}") from exc
