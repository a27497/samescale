from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from harnesslab.api.local_configuration import configuration_enabled, local_operator
from harnesslab.api.workbench_dependencies import workbench_session
from harnesslab.api.workbench_errors import WorkbenchAPIError
from harnesslab.productization.assets import distribution_root
from harnesslab.registry import local_harnesses
from harnesslab.registry.connections import (
    ConnectionMetadata,
    ConnectionWrite,
    CredentialMetadata,
    CredentialWrite,
    credential_records,
    list_connections,
    public_credential,
    save_connection,
    save_credential,
)
from harnesslab.registry.local_models import (
    LocalModelConfiguration,
    LocalModelWrite,
    configurations,
    effective_catalog,
    generation_options,
    save_configuration,
)
from harnesslab.registry.service import registry_catalog
from harnesslab.registry.vault import CredentialVault

router = APIRouter(prefix="/local-configuration", tags=["local-configuration"])
Session = Annotated[AsyncSession, Depends(workbench_session)]


@router.get("/status")
async def status(request: Request, response: Response) -> dict[str, bool]:
    response.headers["Cache-Control"] = "no-store"
    return {"enabled": configuration_enabled(request)}


@router.get("/models", dependencies=[Depends(local_operator)])
async def models(
    session: Session, response: Response
) -> dict[str, tuple[LocalModelConfiguration, ...]]:
    response.headers["Cache-Control"] = "no-store"
    return {"items": await configurations(session)}


@router.put("/models/{configuration_id}", dependencies=[Depends(local_operator)])
async def save_model(
    configuration_id: Annotated[str, Path(pattern=r"^[a-z][a-z0-9-]{0,39}$")],
    payload: LocalModelWrite,
    session: Session,
    response: Response,
) -> LocalModelConfiguration:
    response.headers["Cache-Control"] = "no-store"
    return await save_configuration(
        session,
        registry_catalog(distribution_root(), os.environ),
        configuration_id,
        payload,
        await list_connections(session, os.environ, CredentialVault.from_environment()),
    )


@router.get("/credentials", dependencies=[Depends(local_operator)])
async def credentials(
    session: Session, response: Response
) -> dict[str, tuple[CredentialMetadata, ...]]:
    response.headers["Cache-Control"] = "no-store"
    vault = CredentialVault.from_environment()
    return {
        "items": tuple(
            public_credential(row, vault)
            for _, row in sorted((await credential_records(session)).items())
        )
    }


@router.put("/credentials/{credential_id}", dependencies=[Depends(local_operator)])
async def write_credential(
    credential_id: Annotated[str, Path(pattern=r"^[a-z][a-z0-9-]{0,31}$")],
    payload: CredentialWrite,
    session: Session,
    response: Response,
) -> CredentialMetadata:
    response.headers["Cache-Control"] = "no-store"
    return await save_credential(
        session, credential_id, payload, CredentialVault.from_environment()
    )


@router.get("/connections", dependencies=[Depends(local_operator)])
async def connections(
    session: Session, response: Response
) -> dict[str, tuple[ConnectionMetadata, ...]]:
    response.headers["Cache-Control"] = "no-store"
    return {
        "items": await list_connections(session, os.environ, CredentialVault.from_environment())
    }


@router.put("/connections/{connection_id}", dependencies=[Depends(local_operator)])
async def write_connection(
    connection_id: Annotated[str, Path(pattern=r"^[a-z][a-z0-9-]{0,31}$")],
    payload: ConnectionWrite,
    session: Session,
    response: Response,
) -> ConnectionMetadata:
    response.headers["Cache-Control"] = "no-store"
    return await save_connection(
        session,
        registry_catalog(distribution_root(), os.environ),
        connection_id,
        payload,
        os.environ,
        CredentialVault.from_environment(),
    )


@router.post("/connections/{connection_id}/check", dependencies=[Depends(local_operator)])
async def check_connection(
    connection_id: str, session: Session, response: Response
) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    item = next(
        (
            c
            for c in await list_connections(session, os.environ, CredentialVault.from_environment())
            if c.connection_id == connection_id
        ),
        None,
    )
    if item is None:
        raise WorkbenchAPIError(404, "CONNECTION_NOT_FOUND", "Connection does not exist.")
    return {
        "connection": item,
        "check_kind": "LOCAL_CONFIGURATION_ONLY",
        "connection_health": "NOT_VERIFIED",
        "network_requests": 0,
        "provider_requests": 0,
    }


@router.get("/options", dependencies=[Depends(local_operator)])
async def options(session: Session, response: Response) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    builtin = registry_catalog(distribution_root(), os.environ)
    models = await configurations(session)
    catalog = effective_catalog(
        builtin,
        models,
        await list_connections(session, os.environ, CredentialVault.from_environment()),
    )
    direct = next(h for h in builtin.harnesses if h.harness_id == "direct-model")
    supported = {p for h in direct.profiles for p in h.supported_provider_profile_ids}
    return {
        "model_controls": [
            generation_options(builtin, p)
            for p in builtin.provider_model_profiles
            if p.profile_id in supported
        ],
        "harness_templates": [
            {
                "profile_id": p.profile_id,
                "harness_id": h.harness_id,
                "version": h.version,
                "profile_reference": p.profile_reference,
                "reasoning_effort": None if h.harness_id == "direct-model" else p.reasoning_effort,
                "tool_surface": h.tool_surface,
                "supported_provider_profile_ids": local_harnesses.allowed_profiles(
                    h, p, catalog, models
                ),
            }
            for h in builtin.harnesses
            for p in h.profiles
        ],
    }


@router.get("/harnesses", dependencies=[Depends(local_operator)])
async def harnesses(
    session: Session, response: Response
) -> dict[str, tuple[local_harnesses.LocalHarnessConfiguration, ...]]:
    response.headers["Cache-Control"] = "no-store"
    return {"items": await local_harnesses.configurations(session)}


@router.put("/harnesses/{configuration_id}", dependencies=[Depends(local_operator)])
async def save_harness(
    configuration_id: Annotated[str, Path(pattern=r"^[a-z][a-z0-9-]{0,39}$")],
    payload: local_harnesses.LocalHarnessWrite,
    session: Session,
    response: Response,
) -> local_harnesses.LocalHarnessConfiguration:
    response.headers["Cache-Control"] = "no-store"
    builtin = registry_catalog(distribution_root(), os.environ)
    models = await configurations(session)
    catalog = effective_catalog(
        builtin,
        models,
        await list_connections(session, os.environ, CredentialVault.from_environment()),
    )
    return await local_harnesses.save_configuration(
        session, builtin, catalog, configuration_id, payload, models
    )
