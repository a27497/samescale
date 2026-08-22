from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from harnesslab.core.config import get_settings
from harnesslab.db.health import check_database

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])
DatabaseCheck = Callable[[], Awaitable[None]]


def database_check_dependency() -> DatabaseCheck:
    settings = get_settings()

    async def perform_check() -> None:
        await check_database(settings)

    return perform_check


@router.get("/health")
async def health(
    database_check: Annotated[DatabaseCheck, Depends(database_check_dependency)],
) -> JSONResponse:
    try:
        await database_check()
    except Exception as exc:  # API boundary intentionally converts all backend failures.
        logger.warning("Database health check failed: %s", type(exc).__name__)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unhealthy", "database": "unavailable"},
        )
    return JSONResponse(content={"status": "ok", "database": "ok"})
