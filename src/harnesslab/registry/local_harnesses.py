"""Append-only local selections of supported, immutable Harness presets."""

from __future__ import annotations

from pydantic import Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from harnesslab.api.workbench_errors import WorkbenchAPIError
from harnesslab.contracts.common import Identifier
from harnesslab.db.models.registry import LocalHarnessConfigurationRecord
from harnesslab.registry.local_models import LocalModelConfiguration
from harnesslab.registry.models import (
    HarnessDefinition,
    HarnessProfileDefinition,
    RegistryCatalog,
    RegistryModel,
    canonical_digest,
)


class LocalHarnessWrite(RegistryModel):
    name: str = Field(min_length=1, max_length=100, pattern=r".*\S.*")
    template_profile_id: Identifier
    provider_profile_ids: list[Identifier] = Field(min_length=1, max_length=50)
    enabled: bool = Field(default=True, strict=True)
    expected_revision: int = Field(ge=0, lt=2_147_483_647, strict=True)

    @model_validator(mode="after")
    def unique_bindings(self) -> LocalHarnessWrite:
        if len(set(self.provider_profile_ids)) != len(self.provider_profile_ids):
            raise ValueError("model bindings must be unique")
        return self


class LocalHarnessConfiguration(RegistryModel):
    configuration_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,39}$")
    revision: int = Field(ge=1)
    name: str
    enabled: bool
    template_profile_id: Identifier
    template_digest: str
    harness_id: Identifier
    profile: HarnessProfileDefinition

    @model_validator(mode="after")
    def revision_is_bound(self) -> LocalHarnessConfiguration:
        if (
            self.profile.profile_id != f"local-harness-{self.configuration_id}-v{self.revision}"
            or self.profile.enabled != self.enabled
        ):
            raise ValueError("stored harness revision mismatch")
        return self


def template(
    catalog: RegistryCatalog, profile_id: str
) -> tuple[HarnessDefinition, HarnessProfileDefinition]:
    for harness in catalog.harnesses:
        for profile in harness.profiles:
            if profile.profile_id == profile_id and not profile_id.startswith("local-"):
                return harness, profile
    raise WorkbenchAPIError(
        422, "UNSUPPORTED_HARNESS_TEMPLATE", "Choose a registered Harness preset."
    )


def template_digest(harness: HarnessDefinition, profile: HarnessProfileDefinition) -> str:
    return canonical_digest(
        {
            "harness": harness.model_dump(mode="json", exclude={"profiles", "runtime_health"}),
            "profile": profile.model_dump(mode="json"),
        }
    )


def allowed_profiles(
    harness: HarnessDefinition,
    profile: HarnessProfileDefinition,
    catalog: RegistryCatalog,
    models: tuple[LocalModelConfiguration, ...],
) -> tuple[str, ...]:
    candidates = set(profile.supported_provider_profile_ids)
    if harness.harness_id == "direct-model":
        candidates.update(
            m.profile.profile_id for m in models if m.template_profile_id in candidates
        )
    return tuple(
        sorted(
            p.profile_id
            for p in catalog.provider_model_profiles
            if p.profile_id in candidates and p.purpose == "SUBJECT"
        )
    )


async def configurations(session: AsyncSession) -> tuple[LocalHarnessConfiguration, ...]:
    records = (
        await session.scalars(
            select(LocalHarnessConfigurationRecord).order_by(
                LocalHarnessConfigurationRecord.revision
            )
        )
    ).all()
    latest = {r.configuration_id: r for r in records}
    try:
        result = []
        for key, row in sorted(latest.items()):
            item = LocalHarnessConfiguration.model_validate(row.configuration_json)
            if item.configuration_id != key or item.revision != row.revision:
                raise ValueError("stored identity mismatch")
            result.append(item)
        return tuple(result)
    except ValueError:
        raise WorkbenchAPIError(
            409, "LOCAL_CONFIGURATION_INVALID", "Stored Harness configuration is invalid."
        ) from None


async def save_configuration(
    session: AsyncSession,
    builtin: RegistryCatalog,
    catalog: RegistryCatalog,
    configuration_id: str,
    request: LocalHarnessWrite,
    models: tuple[LocalModelConfiguration, ...],
) -> LocalHarnessConfiguration:
    previous = next(
        (c for c in await configurations(session) if c.configuration_id == configuration_id), None
    )
    if request.expected_revision != (previous.revision if previous else 0):
        raise WorkbenchAPIError(
            409, "CONFIGURATION_REVISION_CONFLICT", "Reload before saving this configuration."
        )
    harness, source = template(builtin, request.template_profile_id)
    allowed = allowed_profiles(harness, source, catalog, models)
    disabling_existing = (
        previous is not None
        and not request.enabled
        and request.template_profile_id == previous.template_profile_id
        and tuple(sorted(request.provider_profile_ids))
        == previous.profile.supported_provider_profile_ids
    )
    if not disabling_existing and not set(request.provider_profile_ids).issubset(allowed):
        raise WorkbenchAPIError(
            422,
            "UNSUPPORTED_HARNESS_BINDING",
            "Select exact model revisions supported by this preset.",
        )
    revision = request.expected_revision + 1
    item = LocalHarnessConfiguration(
        configuration_id=configuration_id,
        revision=revision,
        name=request.name,
        enabled=request.enabled,
        template_profile_id=request.template_profile_id,
        template_digest=template_digest(harness, source),
        harness_id=harness.harness_id,
        profile=source.model_copy(
            update={
                "profile_id": f"local-harness-{configuration_id}-v{revision}",
                "enabled": request.enabled,
                "reasoning_effort": None
                if harness.harness_id == "direct-model"
                else source.reasoning_effort,
                "supported_provider_profile_ids": tuple(sorted(request.provider_profile_ids)),
            }
        ),
    )
    session.add(
        LocalHarnessConfigurationRecord(
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
            409, "CONFIGURATION_REVISION_CONFLICT", "Reload before saving this configuration."
        ) from None
    return item


def effective_catalog(
    builtin: RegistryCatalog,
    catalog: RegistryCatalog,
    items: tuple[LocalHarnessConfiguration, ...],
    models: tuple[LocalModelConfiguration, ...],
) -> RegistryCatalog:
    additions: dict[str, list[HarnessProfileDefinition]] = {}
    existing = {p.profile_id for p in catalog.provider_model_profiles}
    for item in items:
        try:
            harness, source = template(builtin, item.template_profile_id)
        except WorkbenchAPIError:
            continue
        if item.harness_id != harness.harness_id or not set(
            item.profile.supported_provider_profile_ids
        ).issubset(existing):
            continue
        allowed = allowed_profiles(harness, source, catalog, models)
        ready = (
            item.enabled
            and item.template_digest == template_digest(harness, source)
            and set(item.profile.supported_provider_profile_ids).issubset(allowed)
        )
        additions.setdefault(harness.harness_id, []).append(
            item.profile.model_copy(update={"enabled": ready})
        )
    return RegistryCatalog.model_validate(
        {
            **catalog.model_dump(),
            "harnesses": tuple(
                h.model_copy(update={"profiles": (*h.profiles, *additions.get(h.harness_id, []))})
                for h in catalog.harnesses
            ),
        }
    )
