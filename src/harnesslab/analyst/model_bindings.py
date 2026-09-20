"""Resolve exact local Analyst selections without invoking a provider."""

from collections.abc import Mapping
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from harnesslab.analyst.real_backend import AnalystProfile, resolve_analyst_profile
from harnesslab.budget.models import AnalystSpendLimits
from harnesslab.registry.connections import list_connections
from harnesslab.registry.local_models import configurations, effective_catalog
from harnesslab.registry.model_bindings import ModelRoleBinding, freeze_model_role
from harnesslab.registry.service import registry_catalog
from harnesslab.registry.vault import CredentialVault


async def local_analyst_profile(
    session: AsyncSession,
    *,
    root: Path,
    environment: Mapping[str, str],
    vault: CredentialVault,
    profile_id: str,
    budget: AnalystSpendLimits,
) -> tuple[AnalystProfile, ModelRoleBinding]:
    builtin = registry_catalog(root, environment)
    items = await configurations(session)
    selected = next((item for item in items if item.profile.profile_id == profile_id), None)
    if selected is None:
        raise ValueError(
            "local Analyst selection is stale or unavailable; create a new investigation"
        )
    binding = await freeze_model_role(
        session,
        builtin,
        configuration_id=selected.configuration_id,
        revision=selected.revision,
        purpose="ANALYST",
        output_tokens=budget.output_tokens_per_request,
        timeout_seconds=budget.timeout_seconds,
        environment=environment,
        vault=vault,
    )
    catalog = effective_catalog(builtin, items, await list_connections(session, environment, vault))
    profile = resolve_analyst_profile(catalog, profile_id, root)
    return profile.model_copy(update={"runtime": binding.runtime}), binding
