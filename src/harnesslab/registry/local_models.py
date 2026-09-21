"""Versioned local model configurations; built-ins and saved plans stay immutable."""

from __future__ import annotations

from typing import Literal, TypedDict

from pydantic import ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from harnesslab.api.workbench_errors import WorkbenchAPIError
from harnesslab.contracts.common import Identifier, Sha256Digest
from harnesslab.db.models.registry import LocalModelConfigurationRecord
from harnesslab.registry.connections import ConnectionMetadata, connection_provider
from harnesslab.registry.models import (
    ProviderModelProfile,
    RegistryCatalog,
    RegistryModel,
    freeze_provider_model_profile,
)


class LocalModelInput(RegistryModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    name: str = Field(min_length=1, max_length=100, pattern=r".*\S.*")
    template_profile_id: Identifier
    request_timeout_seconds: int = Field(ge=1, le=600)
    enabled: bool = True
    purpose: Literal["SUBJECT", "ANALYST", "JUDGE"] = Field(
        default="SUBJECT", exclude_if=lambda value: value == "SUBJECT"
    )
    max_output_tokens: int | None = Field(
        default=None, ge=1, le=32768, exclude_if=lambda value: value is None
    )
    reasoning_effort: Literal["low", "medium", "high"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    temperature: float | None = Field(
        default=None, ge=0, le=2, exclude_if=lambda value: value is None
    )
    connection_id: str | None = Field(
        default=None, pattern=r"^[a-z][a-z0-9-]{0,31}$", exclude_if=lambda value: value is None
    )
    connection_revision: int | None = Field(
        default=None, ge=1, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def connection_is_pinned(self) -> LocalModelInput:
        if (self.connection_id is None) != (self.connection_revision is None):
            raise ValueError("connection selection requires its exact revision")
        return self


class LocalModelConfiguration(LocalModelInput):
    configuration_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,39}$")
    revision: int = Field(ge=1)
    profile: ProviderModelProfile
    template_digest: Sha256Digest
    origin: Literal["LOCAL"] = "LOCAL"

    @model_validator(mode="after")
    def profile_matches_revision(self) -> LocalModelConfiguration:
        if (
            self.profile.profile_id != f"local-{self.configuration_id}-v{self.revision}"
            or self.profile.enabled != self.enabled
            or self.profile.purpose != self.purpose
            or self.profile.max_output_tokens_limit != self.max_output_tokens
            or (
                self.reasoning_effort is not None
                and self.profile.reasoning_effort != self.reasoning_effort
            )
            or self.profile.temperature != self.temperature
            or self.profile.request_timeout_seconds != self.request_timeout_seconds
        ):
            raise ValueError("local configuration revision does not match its profile")
        return self


class LocalModelWrite(LocalModelInput):
    expected_revision: int = Field(ge=0, lt=2_147_483_647)


async def configurations(session: AsyncSession) -> tuple[LocalModelConfiguration, ...]:
    records = (await session.scalars(select(LocalModelConfigurationRecord))).all()
    latest: dict[str, LocalModelConfigurationRecord] = {}
    for record in records:
        previous = latest.get(record.configuration_id)
        if previous is None or record.revision > previous.revision:
            latest[record.configuration_id] = record
    try:
        items = []
        for _, record in sorted(latest.items()):
            item = LocalModelConfiguration.model_validate(record.configuration_json)
            if item.configuration_id != record.configuration_id or item.revision != record.revision:
                raise ValueError("stored revision identity mismatch")
            items.append(item)
        return tuple(items)
    except ValueError:
        raise WorkbenchAPIError(
            409, "LOCAL_CONFIGURATION_INVALID", "Stored configuration failed validation."
        ) from None


async def save_configuration(
    session: AsyncSession,
    catalog: RegistryCatalog,
    configuration_id: str,
    request: LocalModelWrite,
    connections: tuple[ConnectionMetadata, ...] = (),
) -> LocalModelConfiguration:
    latest = next(
        (
            item
            for item in await configurations(session)
            if item.configuration_id == configuration_id
        ),
        None,
    )
    if request.expected_revision != (latest.revision if latest else 0):
        raise WorkbenchAPIError(
            409, "CONFIGURATION_REVISION_CONFLICT", "Configuration changed; reload before saving."
        )
    template = next(
        (p for p in catalog.provider_model_profiles if p.profile_id == request.template_profile_id),
        None,
    )
    direct = next(h for h in catalog.harnesses if h.harness_id == "direct-model")
    if template is None or not any(
        template.profile_id in p.supported_provider_profile_ids for p in direct.profiles
    ):
        raise WorkbenchAPIError(
            422, "UNSUPPORTED_CONFIGURATION_TEMPLATE", "Select a registered Direct model template."
        )
    options = generation_options(catalog, template)
    if (
        (
            request.max_output_tokens is not None
            and request.max_output_tokens > options["max_output_tokens"]
        )
        or (
            request.reasoning_effort is not None
            and request.reasoning_effort not in options["reasoning_efforts"]
        )
        or (request.temperature is not None and not options["temperature_supported"])
    ):
        raise WorkbenchAPIError(
            422,
            "UNSUPPORTED_GENERATION_CONTROL",
            "Use the template's supported generation controls.",
        )
    revision = request.expected_revision + 1
    values = template.model_dump(exclude={"profile_identity"})
    values.update(
        profile_id=f"local-{configuration_id}-v{revision}",
        enabled=request.enabled,
        purpose=request.purpose,
        temperature=request.temperature,
        max_output_tokens_limit=request.max_output_tokens,
        max_output_tokens=request.max_output_tokens or template.max_output_tokens,
        reasoning_effort=request.reasoning_effort or template.reasoning_effort,
        request_timeout_seconds=request.request_timeout_seconds,
    )
    if request.connection_id is not None:
        connection = next(
            (c for c in connections if c.connection_id == request.connection_id), None
        )
        if connection is None or connection.revision != request.connection_revision:
            raise WorkbenchAPIError(
                409,
                "CONNECTION_REVISION_CONFLICT",
                "Connection changed or is missing; reload before saving.",
            )
        if (
            connection.template_provider_id != template.provider_id
            or connection.protocol != template.protocol
        ):
            raise WorkbenchAPIError(
                422,
                "CONNECTION_TEMPLATE_MISMATCH",
                "Connection provider and protocol must match the model template.",
            )
        provider = connection_provider(connection, catalog)
        values.update(
            provider_id=provider.provider_id,
            provider_route_identity=f"{provider.provider_id}|{template.protocol.value}|env:{connection.endpoint_reference}{template.route}",
            credential_reference=connection.credential_reference,
            runtime_endpoint_fingerprint=connection.endpoint_fingerprint,
            pricing_snapshot_reference=None,
        )
    item = LocalModelConfiguration(
        **request.model_dump(exclude={"expected_revision"}),
        configuration_id=configuration_id,
        revision=revision,
        profile=freeze_provider_model_profile(**values),
        template_digest=template.profile_identity,
    )
    session.add(
        LocalModelConfigurationRecord(
            configuration_id=configuration_id,
            revision=revision,
            configuration_json=item.model_dump(mode="json"),
        )
    )
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise WorkbenchAPIError(
            409, "CONFIGURATION_REVISION_CONFLICT", "Configuration changed; reload before saving."
        ) from None
    return item


def effective_catalog(
    builtin: RegistryCatalog,
    items: tuple[LocalModelConfiguration, ...],
    connections: tuple[ConnectionMetadata, ...] = (),
) -> RegistryCatalog:
    """Expose current revisions only, with independently bounded Direct compatibility.

    A copied model profile does not establish that a CLI Harness can consume it.
    Template drift blocks new planning until an operator explicitly saves a revision.
    Existing snapshot reads resolve their own frozen sources, never this catalog.
    """
    templates = {p.profile_id: p for p in builtin.provider_model_profiles}
    model_ids = {m.model_id for m in builtin.models}
    local_providers = tuple(
        connection_provider(c, builtin)
        for c in connections
        if any(p.provider_id == c.template_provider_id for p in builtin.providers)
    )
    provider_ids = {p.provider_id for p in (*builtin.providers, *local_providers)}
    profiles = []
    direct = next(h for h in builtin.harnesses if h.harness_id == "direct-model")
    direct_profiles = list(direct.profiles)
    for item in items:
        template = templates.get(item.template_profile_id)
        connection_ready = True
        if item.connection_id:
            connection = next(
                (c for c in connections if c.connection_id == item.connection_id), None
            )
            if connection is None or connection.revision != item.connection_revision:
                continue
            connection_ready = connection.ready_for_planning
        if (
            template is None
            or item.profile.model_id not in model_ids
            or item.profile.provider_id not in provider_ids
        ):
            # Keep the editable revision in storage, but never introduce dangling
            # references when an environment-backed template has been removed.
            continue
        template_matches = (
            template is not None and template.profile_identity == item.template_digest
        )
        profile = item.profile.model_copy(
            update={
                "enabled": item.enabled
                and template_matches
                and connection_ready
                and bool(template and template.enabled)
            }
        )
        profiles.append(profile)
        source = next(
            (
                p
                for p in direct.profiles
                if item.template_profile_id in p.supported_provider_profile_ids
            ),
            None,
        )
        if source is not None:
            direct_profiles.append(
                source.model_copy(
                    update={
                        "profile_id": f"direct-{profile.profile_id}",
                        "supported_provider_profile_ids": (profile.profile_id,),
                        "reasoning_effort": profile.reasoning_effort,
                    }
                )
            )
    return RegistryCatalog.model_validate(
        {
            **builtin.model_dump(),
            "providers": (*builtin.providers, *local_providers),
            "provider_model_profiles": (*builtin.provider_model_profiles, *profiles),
            "harnesses": tuple(
                h.model_copy(update={"profiles": tuple(direct_profiles)})
                if h.harness_id == "direct-model"
                else h
                for h in builtin.harnesses
            ),
        }
    )


class GenerationOptions(TypedDict):
    profile_id: str
    max_output_tokens: int
    reasoning_efforts: list[str]
    temperature_supported: bool


def generation_options(
    catalog: RegistryCatalog, profile: ProviderModelProfile
) -> GenerationOptions:
    model = next(m for m in catalog.models if m.model_id == profile.model_id)
    return {
        "profile_id": profile.profile_id,
        "max_output_tokens": min(profile.max_output_tokens, 32768),
        "reasoning_efforts": ["low", "medium", "high"]
        if model.reasoning_controls.effort
        else ([profile.reasoning_effort] if profile.reasoning_effort else []),
        "temperature_supported": model.reasoning_controls.temperature,
    }
