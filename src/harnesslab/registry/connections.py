"""Versioned local services and credentials, with explicit reference resolution."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from harnesslab.api.workbench_errors import WorkbenchAPIError
from harnesslab.contracts.common import Protocol
from harnesslab.contracts.provider import validate_provider_base_url
from harnesslab.db.models.registry import LocalConnectionRecord, LocalCredentialRecord
from harnesslab.registry.models import (
    ProviderDefinition,
    RegistryCatalog,
    RegistryModel,
    canonical_digest,
)
from harnesslab.registry.vault import CredentialVault


def conflict() -> WorkbenchAPIError:
    return WorkbenchAPIError(
        409,
        "CONFIGURATION_REVISION_CONFLICT",
        "Referenced configuration changed; reload before saving.",
    )


class CredentialWrite(RegistryModel):
    name: str = Field(min_length=1, max_length=100, pattern=r".*\S.*")
    expected_revision: int = Field(ge=0, lt=2_147_483_647, strict=True)
    enabled: bool = Field(default=True, strict=True)
    value: SecretStr | None = Field(default=None, exclude=True, repr=False)

    @field_validator("value")
    @classmethod
    def value_is_bounded(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None:
            raw = value.get_secret_value()
            if not 1 <= len(raw) <= 8192 or any(ord(c) < 33 or ord(c) > 126 for c in raw):
                raise ValueError("credential must be bounded non-whitespace ASCII")
        return value


class CredentialMetadata(RegistryModel):
    credential_id: str
    revision: int
    name: str
    enabled: bool
    reference: str
    present: bool


class ConnectionWrite(RegistryModel):
    name: str = Field(min_length=1, max_length=100, pattern=r".*\S.*")
    expected_revision: int = Field(ge=0, lt=2_147_483_647, strict=True)
    enabled: bool = Field(default=True, strict=True)
    template_provider_id: str = Field(min_length=1, max_length=100)
    protocol: Literal["responses", "chat_completions", "messages"]
    base_url: SecretStr | None = Field(default=None, exclude=True, repr=False)
    credential_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9-]{0,31}$")
    credential_revision: int | None = Field(default=None, ge=1, strict=True)
    environment_reference: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]*$")

    @field_validator("base_url")
    @classmethod
    def endpoint_is_safe(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None:
            if len(value.get_secret_value()) > 500:
                raise ValueError("endpoint is too long")
            return SecretStr(validate_provider_base_url(value.get_secret_value()))
        return value

    @model_validator(mode="after")
    def credential_source_is_explicit(self) -> ConnectionWrite:
        if (self.credential_id is None) == (self.environment_reference is None):
            raise ValueError("select exactly one credential source")
        if (self.credential_id is None) != (self.credential_revision is None):
            raise ValueError("managed credentials require an exact revision")
        return self


class ConnectionMetadata(RegistryModel):
    connection_id: str
    revision: int
    name: str
    enabled: bool
    template_provider_id: str
    protocol: Protocol
    credential_id: str | None
    credential_revision: int | None
    environment_reference: str | None
    credential_reference: str
    endpoint_reference: str
    endpoint_fingerprint: str
    endpoint_present: bool
    credential_present: bool
    ready_for_planning: bool
    health_status: Literal["NOT_VERIFIED"] = "NOT_VERIFIED"


def credential_reference(credential_id: str, revision: int) -> str:
    return f"HARNESSLAB_LOCAL_KEY_{credential_id.replace('-', '_').upper()}_V{revision}"


def endpoint_reference(connection_id: str, revision: int) -> str:
    return f"HARNESSLAB_LOCAL_URL_{connection_id.replace('-', '_').upper()}_V{revision}"


async def credential_records(session: AsyncSession) -> dict[str, LocalCredentialRecord]:
    rows = (
        await session.scalars(
            select(LocalCredentialRecord).order_by(LocalCredentialRecord.revision)
        )
    ).all()
    return {row.credential_id: row for row in rows}


async def connection_records(session: AsyncSession) -> dict[str, LocalConnectionRecord]:
    rows = (
        await session.scalars(
            select(LocalConnectionRecord).order_by(LocalConnectionRecord.revision)
        )
    ).all()
    return {row.connection_id: row for row in rows}


def public_credential(row: LocalCredentialRecord, vault: CredentialVault) -> CredentialMetadata:
    return CredentialMetadata(
        credential_id=row.credential_id,
        revision=row.revision,
        name=row.name,
        enabled=row.enabled,
        reference=credential_reference(row.credential_id, row.revision),
        present=row.enabled and vault.present(row.storage_reference),
    )


async def save_credential(
    session: AsyncSession, credential_id: str, request: CredentialWrite, vault: CredentialVault
) -> CredentialMetadata:
    previous = (await credential_records(session)).get(credential_id)
    if request.expected_revision != (previous.revision if previous else 0):
        raise conflict()
    if previous is None and request.value is None:
        raise WorkbenchAPIError(422, "CREDENTIAL_VALUE_REQUIRED", "A new credential needs a value.")
    created: str | None = None
    try:
        created = vault.put(request.value.get_secret_value()) if request.value is not None else None
        storage = created or (previous.storage_reference if previous else None)
        if request.enabled and not vault.present(storage):
            raise WorkbenchAPIError(
                503, "CREDENTIAL_STORE_UNAVAILABLE", "Credential is unavailable."
            )
        assert storage is not None
        row = LocalCredentialRecord(
            credential_id=credential_id,
            revision=request.expected_revision + 1,
            name=request.name,
            enabled=request.enabled,
            storage_reference=storage,
        )
        session.add(row)
        await session.commit()
    except Exception as exc:
        await session.rollback()
        if created:
            vault.discard(created)
        if isinstance(exc, IntegrityError):
            raise conflict() from None
        raise
    return public_credential(row, vault)


def describe_connection(
    row: LocalConnectionRecord,
    credentials: dict[str, LocalCredentialRecord],
    environment: Mapping[str, str],
    vault: CredentialVault,
) -> ConnectionMetadata:
    data = row.configuration_json
    credential_id = data["credential_id"]
    credential = credentials.get(credential_id) if credential_id else None
    credential_present = (
        credential is not None
        and credential.revision == data["credential_revision"]
        and credential.enabled
        and vault.present(credential.storage_reference)
        if credential_id
        else bool(environment.get(data["environment_reference"], "").strip())
    )
    try:
        endpoint = validate_provider_base_url(vault.read(row.endpoint_storage_reference))
        endpoint_present = (
            canonical_digest({"runtime_endpoint": endpoint}) == data["endpoint_fingerprint"]
        )
    except (WorkbenchAPIError, ValueError):
        endpoint_present = False
    return ConnectionMetadata(
        **data,
        endpoint_present=endpoint_present,
        credential_present=credential_present,
        ready_for_planning=data["enabled"] and endpoint_present and credential_present,
    )


async def list_connections(
    session: AsyncSession, environment: Mapping[str, str], vault: CredentialVault
) -> tuple[ConnectionMetadata, ...]:
    credentials = await credential_records(session)
    return tuple(
        describe_connection(row, credentials, environment, vault)
        for _, row in sorted((await connection_records(session)).items())
    )


async def save_connection(
    session: AsyncSession,
    catalog: RegistryCatalog,
    connection_id: str,
    request: ConnectionWrite,
    environment: Mapping[str, str],
    vault: CredentialVault,
) -> ConnectionMetadata:
    previous = (await connection_records(session)).get(connection_id)
    if request.expected_revision != (previous.revision if previous else 0):
        raise conflict()
    template = next(
        (p for p in catalog.providers if p.provider_id == request.template_provider_id), None
    )
    protocol = Protocol(request.protocol)
    if template is None or protocol not in template.protocols:
        raise WorkbenchAPIError(
            422, "UNSUPPORTED_CONNECTION", "Select a supported provider and protocol."
        )
    credentials = await credential_records(session)
    if request.credential_id:
        credential = credentials.get(request.credential_id)
        if credential is None or credential.revision != request.credential_revision:
            raise conflict()
        ref = credential_reference(credential.credential_id, credential.revision)
    else:
        if request.environment_reference != template.credential_reference:
            raise WorkbenchAPIError(
                422,
                "INVALID_ENVIRONMENT_REFERENCE",
                "Use the template's existing credential reference.",
            )
        ref = template.credential_reference
    created: str | None = None
    try:
        created = (
            vault.put(request.base_url.get_secret_value()) if request.base_url is not None else None
        )
        storage = created or (previous.endpoint_storage_reference if previous else None)
        if storage is None:
            raise WorkbenchAPIError(
                422, "ENDPOINT_REQUIRED", "A new connection needs an HTTPS endpoint."
            )
        endpoint = validate_provider_base_url(vault.read(storage))
        revision = request.expected_revision + 1
        metadata = {
            **request.model_dump(exclude={"expected_revision"}),
            "connection_id": connection_id,
            "revision": revision,
            "protocol": protocol.value,
            "credential_reference": ref,
            "endpoint_reference": endpoint_reference(connection_id, revision),
            "endpoint_fingerprint": canonical_digest({"runtime_endpoint": endpoint}),
        }
        row = LocalConnectionRecord(
            connection_id=connection_id,
            revision=revision,
            endpoint_storage_reference=storage,
            configuration_json=metadata,
        )
        session.add(row)
        await session.commit()
    except Exception as exc:
        await session.rollback()
        if created:
            vault.discard(created)
        if isinstance(exc, IntegrityError):
            raise conflict() from None
        raise
    return describe_connection(row, credentials, environment, vault)


def connection_provider(item: ConnectionMetadata, catalog: RegistryCatalog) -> ProviderDefinition:
    template = next(p for p in catalog.providers if p.provider_id == item.template_provider_id)
    values = template.model_dump()
    values.update(
        provider_id=f"local-connection-{item.connection_id}-v{item.revision}",
        display_name=item.name,
        protocols=(item.protocol,),
        base_url_reference=item.endpoint_reference,
        protocol_base_url_references={},
        credential_reference=item.credential_reference,
        enabled=item.ready_for_planning and template.enabled,
        health_status="UNKNOWN",
        runtime_endpoint_fingerprint=item.endpoint_fingerprint,
        runtime_endpoint_fingerprints={item.protocol: item.endpoint_fingerprint},
        pricing_snapshot_reference=None,
        configuration_reason_codes=(),
    )
    return ProviderDefinition.model_validate(values)


async def resolve_connection_environment(
    session: AsyncSession,
    connection_id: str,
    revision: int,
    environment: Mapping[str, str],
    vault: CredentialVault,
) -> dict[str, str]:
    """Resolve one pinned active connection for the existing ProviderAdapter boundary.

    Never install these values in process environment, responses or planning data.
    Old snapshots remain readable; stale credentials/connections cannot silently execute.
    """
    row = (await connection_records(session)).get(connection_id)
    if row is None or row.revision != revision:
        raise conflict()
    credentials = await credential_records(session)
    item = describe_connection(row, credentials, environment, vault)
    if not item.ready_for_planning:
        raise WorkbenchAPIError(
            409, "CONNECTION_NOT_READY", "Connection or credential is unavailable."
        )
    key = (
        vault.read(credentials[item.credential_id].storage_reference)
        if item.credential_id
        else environment[item.credential_reference]
    )
    endpoint = validate_provider_base_url(vault.read(row.endpoint_storage_reference))
    if canonical_digest({"runtime_endpoint": endpoint}) != item.endpoint_fingerprint:
        raise WorkbenchAPIError(409, "ENDPOINT_INTEGRITY_ERROR", "Stored endpoint changed.")
    return {item.credential_reference: key, item.endpoint_reference: endpoint}
