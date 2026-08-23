from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


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
