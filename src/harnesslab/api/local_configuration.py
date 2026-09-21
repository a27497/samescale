"""Local operator boundary for opt-in workspace configuration writes."""

from __future__ import annotations

import hmac
import os
from collections.abc import AsyncIterator
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from harnesslab.api.workbench_dependencies import workbench_session
from harnesslab.api.workbench_errors import WorkbenchAPIError
from harnesslab.productization.assets import distribution_root
from harnesslab.registry import local_harnesses
from harnesslab.registry.connections import list_connections
from harnesslab.registry.local_models import configurations, effective_catalog
from harnesslab.registry.models import RegistryCatalog
from harnesslab.registry.service import registry_catalog
from harnesslab.registry.vault import CredentialVault


def configuration_enabled(request: Request) -> bool:
    return bool(
        getattr(request.app.state, "local_configuration_allowed", False)
        and len(os.environ.get("HARNESSLAB_LOCAL_CONFIGURATION_TOKEN", "")) >= 32
    )


async def local_operator(request: Request) -> None:
    if not configuration_enabled(request):
        raise WorkbenchAPIError(
            403, "LOCAL_CONFIGURATION_DISABLED", "Local editing is not enabled."
        )
    # Reject DNS rebinding and cross-origin browser writes, including null origins.
    # Forwarded headers never establish the operator origin. The separate bearer
    # credential identifies the local operator, including behind loopback Compose.
    host = request.headers.get("host", "")
    try:
        parsed = urlsplit(f"http://{host}")
        _port = parsed.port
    except ValueError:
        raise WorkbenchAPIError(
            403, "LOCAL_ORIGIN_REQUIRED", "Use the local workspace origin."
        ) from None
    origin = request.headers.get("origin")
    if (
        parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or (origin is not None and origin != f"{request.url.scheme}://{host}")
        or (request.method != "GET" and origin is None)
        or request.headers.get("sec-fetch-site", "same-origin") != "same-origin"
    ):
        raise WorkbenchAPIError(403, "LOCAL_ORIGIN_REQUIRED", "Use the local workspace origin.")
    expected = "Bearer " + os.environ["HARNESSLAB_LOCAL_CONFIGURATION_TOKEN"]
    supplied = request.headers.get("authorization", "")
    if not hmac.compare_digest(supplied.encode(), expected.encode()):
        raise WorkbenchAPIError(403, "LOCAL_OPERATOR_REQUIRED", "Local operator token is required.")
    if (
        request.method != "GET"
        and request.headers.get("content-type", "").split(";")[0] != "application/json"
    ):
        raise WorkbenchAPIError(415, "JSON_REQUIRED", "Use a JSON configuration request.")


async def local_catalog_session(request: Request) -> AsyncIterator[AsyncSession | None]:
    if not configuration_enabled(request):
        yield None
        return
    async for session in workbench_session():
        yield session


async def workspace_catalog(
    session: Annotated[AsyncSession | None, Depends(local_catalog_session)],
) -> RegistryCatalog:
    builtin = registry_catalog(distribution_root(), os.environ)
    if session is None:
        return builtin
    models = await configurations(session)
    catalog = effective_catalog(
        builtin,
        models,
        await list_connections(session, os.environ, CredentialVault.from_environment()),
    )

    return local_harnesses.effective_catalog(
        builtin, catalog, await local_harnesses.configurations(session), models
    )


async def configured_credentials(
    session: Annotated[AsyncSession | None, Depends(local_catalog_session)],
) -> frozenset[str]:
    builtin = registry_catalog(distribution_root(), os.environ)
    references = {
        p.credential_reference
        for p in builtin.providers
        if os.environ.get(p.credential_reference, "").strip()
    }
    if session is not None:
        for connection in await list_connections(
            session, os.environ, CredentialVault.from_environment()
        ):
            if connection.credential_present:
                references.add(connection.credential_reference)
    return frozenset(references)
