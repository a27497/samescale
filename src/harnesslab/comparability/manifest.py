from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from harnesslab.comparability.models import ComparisonFacts, canonical_digest


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


def _verifier_identity(raw: dict[str, Any]) -> str | None:
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


def facts_from_manifest(raw: dict[str, Any]) -> ComparisonFacts:
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
        network = _string(profile.get("network_policy")) or _string(
            profile.get("tool_network_policy")
        )
    observed = _string(raw.get("observed_model"))
    return ComparisonFacts(
        evidence_identity=canonical_digest(raw),
        task_id=_string(raw.get("task_id")),
        task_version=_string(raw.get("task_version")),
        task_digest=_string(raw.get("task_digest")),
        workspace_input_digest=_string(raw.get("workspace_input_digest")),
        context_identity=_context_identity(raw),
        verifier_identity=_verifier_identity(raw),
        requested_model=_string(raw.get("requested_model")),
        observed_model=observed,
        provider_route=route,
        budget_identity=canonical_digest(budget) if isinstance(budget, dict) else None,
        network_policy=network,
        harness=harness,
        harness_version=version,
        harness_profile_identity=_profile_identity(raw, profile),
        prompt_identity=_string(raw.get("prompt_hash")),
        trace_coverage=_string(raw.get("trace_coverage")),
    )


def load_manifest_facts(path: Path) -> ComparisonFacts:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except ComparabilityInputError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ComparabilityInputError(f"invalid evidence manifest: {type(exc).__name__}") from exc
    if not isinstance(raw, dict):
        raise ComparabilityInputError("evidence manifest must contain a JSON object")
    try:
        return facts_from_manifest(raw)
    except (TypeError, ValueError) as exc:
        raise ComparabilityInputError(f"invalid evidence facts: {type(exc).__name__}") from exc
