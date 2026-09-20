from __future__ import annotations

import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


async def database_unavailable_handler(_request: Request, exc: Exception) -> JSONResponse:
    logging.getLogger(__name__).warning("Workspace database failure: %s", type(exc).__name__)
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": "WORKSPACE_DATABASE_UNAVAILABLE",
                "message": "Workspace data is unavailable. Run `samescale doctor` and check "
                "PostgreSQL and migrations, then retry; offline examples remain available.",
            }
        },
    )


class WorkbenchAPIError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.public_message = message


async def workbench_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, WorkbenchAPIError)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.public_message}},
    )


async def request_validation_error_handler(_request: Request, _exc: Exception) -> JSONResponse:
    """Reject strict payloads without reflecting attacker-controlled input values."""

    assert isinstance(_exc, RequestValidationError)
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "INVALID_REQUEST",
                "message": "request failed strict schema validation",
            }
        },
    )
