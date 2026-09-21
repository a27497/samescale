"""Explicit local model role/version binding for existing ProviderAdapter consumers."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from harnesslab.api.workbench_errors import WorkbenchAPIError
from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.common import Sha256Digest
from harnesslab.contracts.model import ModelProfile, ReasoningProfile
from harnesslab.model_lane.models import (
    ProviderFailureCategory,
    ProviderInvocationError,
    ProviderRequest,
    ProviderResult,
)
from harnesslab.model_lane.providers import adapter_for_profile
from harnesslab.registry.connections import list_connections, resolve_connection_environment
from harnesslab.registry.local_models import configurations, effective_catalog
from harnesslab.registry.models import RegistryCatalog
from harnesslab.registry.service import _direct_runtime_source, registry_catalog
from harnesslab.registry.vault import CredentialVault

type ModelPurpose = Literal["SUBJECT", "ANALYST", "JUDGE"]


class ModelBindingError(ValueError):
    """An exact local role/version cannot safely be consumed. Never includes secret values."""


class ModelRoleBinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    purpose: ModelPurpose
    configuration_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,39}$")
    configuration_revision: int = Field(ge=1)
    configuration_digest: Sha256Digest
    provider_profile_identity: Sha256Digest
    connection_id: str | None = None
    connection_revision: int | None = Field(default=None, ge=1)
    runtime: ModelProfile
    runtime_digest: Sha256Digest

    @model_validator(mode="after")
    def identities_match(self) -> ModelRoleBinding:
        if canonical_digest(self.runtime.model_dump(mode="json")) != self.runtime_digest:
            raise ValueError("bound runtime digest mismatch")
        if (self.connection_id is None) != (self.connection_revision is None):
            raise ValueError("bound connection requires an exact revision")
        return self

    @property
    def digest(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))


async def freeze_model_role(
    session: AsyncSession,
    builtin: RegistryCatalog,
    *,
    configuration_id: str,
    revision: int,
    purpose: ModelPurpose,
    output_tokens: int,
    environment: Mapping[str, str],
    vault: CredentialVault,
    timeout_seconds: float | None = None,
) -> ModelRoleBinding:
    """Resolve explicit current metadata only; no credential reads or provider calls."""
    items = await configurations(session)
    selected = next((item for item in items if item.configuration_id == configuration_id), None)
    if selected is None or selected.revision != revision or not selected.enabled:
        raise ModelBindingError("model configuration revision is stale, disabled or unavailable")
    if selected.purpose != purpose:
        raise ModelBindingError("model configuration purpose does not match the consumer role")
    catalog = effective_catalog(
        builtin,
        items,
        await list_connections(session, environment, vault),
    )
    profile = next(
        (p for p in catalog.provider_model_profiles if p.profile_id == selected.profile.profile_id),
        None,
    )
    if profile is None or not profile.enabled or not profile.automation_allowed:
        raise ModelBindingError("model configuration template or connection is unavailable")
    provider = next(p for p in catalog.providers if p.provider_id == profile.provider_id)
    if not provider.enabled or not provider.automation_allowed:
        raise ModelBindingError("model provider is disabled or disallows automation")
    limit = min(
        profile.max_output_tokens, profile.max_output_tokens_limit or profile.max_output_tokens
    )
    if (
        isinstance(output_tokens, bool)
        or not isinstance(output_tokens, int)
        or not 1 <= output_tokens <= limit
    ):
        raise ModelBindingError("output budget exceeds the supported model configuration limit")
    timeout = profile.request_timeout_seconds if timeout_seconds is None else timeout_seconds
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not 0 < timeout <= profile.request_timeout_seconds
    ):
        raise ModelBindingError("request timeout exceeds the model configuration limit")
    source = _direct_runtime_source(provider, profile)
    runtime = ModelProfile(
        **source.model_dump(exclude={"reasoning_effort", "temperature", "max_output_tokens_limit"}),
        reasoning=ReasoningProfile(
            effort=source.reasoning_effort,
            temperature=source.temperature,
            max_output_tokens=output_tokens,
        ),
    ).model_copy(update={"request_timeout_seconds": timeout})
    return ModelRoleBinding(
        purpose=purpose,
        configuration_id=configuration_id,
        configuration_revision=revision,
        configuration_digest=canonical_digest(selected.model_dump(mode="json")),
        provider_profile_identity=profile.profile_identity,
        connection_id=selected.connection_id,
        connection_revision=selected.connection_revision,
        runtime=runtime,
        runtime_digest=canonical_digest(runtime.model_dump(mode="json")),
    )


async def resolve_model_role_environment(
    session: AsyncSession,
    builtin: RegistryCatalog,
    binding: ModelRoleBinding,
    *,
    purpose: ModelPurpose,
    environment: Mapping[str, str],
    vault: CredentialVault,
) -> dict[str, str]:
    """Revalidate this exact role/version before reading its execution-only credentials."""
    if binding.purpose != purpose:
        raise ModelBindingError("bound model purpose does not match the consumer role")
    tokens = binding.runtime.reasoning.max_output_tokens
    if tokens is None:
        raise ModelBindingError("bound model requires an explicit output budget")
    current = await freeze_model_role(
        session,
        builtin,
        configuration_id=binding.configuration_id,
        revision=binding.configuration_revision,
        purpose=purpose,
        output_tokens=tokens,
        timeout_seconds=binding.runtime.request_timeout_seconds,
        environment=environment,
        vault=vault,
    )
    if current.digest != binding.digest:
        raise ModelBindingError("bound model, configuration or provider identity changed")
    if binding.connection_id is not None:
        assert binding.connection_revision is not None
        return await resolve_connection_environment(
            session,
            binding.connection_id,
            binding.connection_revision,
            environment,
            vault,
        )
    references = (binding.runtime.credential_reference, binding.runtime.base_url_reference)
    resolved = {
        name: environment[name] for name in references if name and environment.get(name, "").strip()
    }
    if binding.runtime.credential_reference not in resolved:
        raise ModelBindingError("bound model credential is unavailable")
    if binding.runtime.base_url_reference and binding.runtime.base_url_reference not in resolved:
        raise ModelBindingError("bound model endpoint is unavailable")
    binding.runtime.resolve_base_url(resolved)
    return resolved


class RoleBoundProvider:
    """Existing ProviderAdapter interface with per-call local binding checks, no fallback.

    The consumer still owns its budget and authorization workflow. A separate explicit
    enable flag prevents merely constructing this adapter from granting execution.
    Secret mappings stay in the invocation and are never installed into os.environ.
    """

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        repository_root: Path,
        binding: ModelRoleBinding,
        purpose: ModelPurpose,
        environment: Mapping[str, str],
        vault: CredentialVault,
        execution_enabled: bool = False,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if binding.purpose != purpose:
            raise ModelBindingError("bound model purpose does not match the consumer role")
        self.session_factory = session_factory
        self.root = repository_root
        self.binding = binding
        self.purpose = purpose
        self.environment = environment
        self.vault = vault
        self.execution_enabled = execution_enabled
        self.client = client

    async def invoke(self, request: ProviderRequest) -> ProviderResult:
        if not self.execution_enabled:
            raise ProviderInvocationError(
                ProviderFailureCategory.CONFIGURATION, "bound model execution is not enabled"
            )
        if request.profile != self.binding.runtime:
            raise ProviderInvocationError(
                ProviderFailureCategory.CONFIGURATION,
                "provider request does not match the frozen model binding",
            )
        try:
            async with self.session_factory() as session:
                environment = await resolve_model_role_environment(
                    session,
                    registry_catalog(self.root, self.environment),
                    self.binding,
                    purpose=self.purpose,
                    environment=self.environment,
                    vault=self.vault,
                )
        except (ValueError, WorkbenchAPIError):
            raise ProviderInvocationError(
                ProviderFailureCategory.CONFIGURATION,
                "bound model configuration is no longer executable",
            ) from None

        def public_metadata(value: str | None) -> str | None:
            if value is not None and any(secret in value for secret in environment.values()):
                return None
            return value

        try:
            result = await adapter_for_profile(
                request, client=self.client, environment=environment
            ).invoke(request)
        except ProviderInvocationError as exc:
            raise ProviderInvocationError(
                exc.category,
                "bound provider invocation failed",
                status_code=exc.status_code,
                request_id=public_metadata(exc.request_id),
                response_status=public_metadata(exc.response_status),
                latency_ms=exc.latency_ms,
                timeout_phase=exc.timeout_phase,
                read_timeout_stage=exc.read_timeout_stage,
                response_header_latency_ms=exc.response_header_latency_ms,
                response_body_bytes_received=exc.response_body_bytes_received,
                transport_trace=exc.transport_trace,
                incomplete_reason=exc.incomplete_reason,
            ) from None
        # Consumers need not know vault values to prevent their persistence. Reject
        # leaked output instead of silently rewriting the model's observed answer.
        if public_metadata(result.model_dump_json()) is None:
            raise ProviderInvocationError(
                ProviderFailureCategory.MALFORMED_RESPONSE,
                "bound provider response contained protected connection values",
            )
        return result
