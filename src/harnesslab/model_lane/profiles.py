from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode

from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.model import ModelProfile
from harnesslab.model_lane.models import GenerationSettings


class ModelProfileError(ValueError):
    """A model profile is malformed or cannot identify a safe route."""


def effective_model_profile_identity(profile: ModelProfile) -> str:
    """Identify the complete executable profile, including the model treatment."""

    return canonical_digest(profile.model_dump(mode="json"))


def model_profile_control_identity(profile: ModelProfile) -> str:
    """Identify Direct-model controls while excluding the requested-model treatment."""

    generation = GenerationSettings(
        effort=profile.reasoning.effort,
        temperature=profile.reasoning.temperature,
        max_output_tokens=profile.reasoning.max_output_tokens,
        request_timeout_seconds=profile.request_timeout_seconds,
    )
    controls: dict[str, object] = {
        "provider": profile.provider,
        "endpoint_identity": profile.provider_route_identity,
        "protocol": profile.protocol.value,
        "generation_settings": generation.model_dump(mode="json"),
    }
    if profile.thinking_mode is not None:
        controls["thinking_mode"] = profile.thinking_mode
        controls["thinking_transport"] = profile.thinking_transport
    return canonical_digest(controls)


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _UniqueKeyLoader, node: MappingNode, deep: bool = False
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def load_model_profile(path: Path) -> ModelProfile:
    try:
        raw = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ModelProfileError(f"invalid profile file: {type(exc).__name__}") from exc
    if not isinstance(raw, dict):
        raise ModelProfileError("model profile must contain a mapping")
    try:
        return ModelProfile.model_validate(raw)
    except ValidationError as exc:
        count = len(exc.errors(include_url=False, include_context=False, include_input=False))
        raise ModelProfileError(
            f"invalid model profile: {count} field validation error(s)"
        ) from exc
