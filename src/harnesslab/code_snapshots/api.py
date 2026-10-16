from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from starlette.requests import ClientDisconnect

from harnesslab.api.local_configuration import check_local_operator
from harnesslab.code_snapshots import service
from harnesslab.external_evidence import service as evidence
from harnesslab.local_plans.api import Private
from harnesslab.local_plans.tasks import fail

router = APIRouter(prefix="/code-snapshots", tags=["private-code-snapshots"])


async def zip_operator(request: Request, response: Response) -> None:
    # The only explicit exception to the unchanged default JSON requirement.
    await check_local_operator(request, content_type="application/zip")
    response.headers["Cache-Control"] = "no-store"


async def upload(request: Request) -> bytes:
    declared = request.headers.get("content-length")
    if declared is not None and (not declared.isascii() or not declared.isdecimal()):
        raise fail("ZIP_UPLOAD_TRUNCATED", "Invalid archive length.", 400)
    if declared is not None and len(declared.lstrip("0")) > len(str(service.MAX_UPLOAD)):
        raise fail("ZIP_UPLOAD_LIMIT", "Archive upload exceeds 8,000,000 bytes.", 413)
    expected = int(declared.lstrip("0") or "0") if declared is not None else None
    if expected is not None and expected > service.MAX_UPLOAD:
        raise fail("ZIP_UPLOAD_LIMIT", "Archive upload exceeds 8,000,000 bytes.", 413)
    data = bytearray()
    try:
        async with asyncio.timeout(30):
            async for chunk in request.stream():
                if len(data) + len(chunk) > service.MAX_UPLOAD:
                    raise fail("ZIP_UPLOAD_LIMIT", "Archive upload exceeds 8,000,000 bytes.", 413)
                data.extend(chunk)
    except (ClientDisconnect, TimeoutError):
        raise fail("ZIP_UPLOAD_TRUNCATED", "Archive upload was interrupted.", 400) from None
    if expected is not None and len(data) != expected:
        raise fail("ZIP_UPLOAD_TRUNCATED", "Archive length does not match the upload.", 400)
    return bytes(data)


@router.post("/archive", dependencies=[Depends(zip_operator)])
async def archive(
    request: Request,
    action: Literal["preview", "confirm"] = "preview",
    declared_tool: service.DeclaredTool = "unknown",
) -> dict[str, object]:
    if any(key not in {"action", "declared_tool"} for key in request.query_params) or (
        len(request.query_params.multi_items()) != len(request.query_params)
    ):
        raise fail("ZIP_REQUEST_INVALID", "Use only the declared upload parameters.", 422)
    # Authenticate and validate configuration before consuming any uploaded bytes.
    policy = evidence.load_policy()
    data = await upload(request)
    if action == "preview":
        return await asyncio.to_thread(service.preview, data, declared_tool)
    try:
        return await asyncio.to_thread(
            service.confirm,
            policy,
            data,
            declared_tool,
            consent=request.headers.get("x-snapshot-consent", ""),
            archive_sha256=request.headers.get("x-snapshot-archive-sha256", ""),
            manifest_sha256=request.headers.get("x-snapshot-manifest-sha256", ""),
            signature=request.headers.get("x-snapshot-review", ""),
        )
    except service.Rejected as exc:
        raise fail("ZIP_" + exc.reason, "Confirmation rejected: " + exc.reason, 409) from None
    except (OSError, ValueError, KeyError, TypeError):
        raise fail(
            "SNAPSHOT_INTEGRITY_ERROR", "Snapshot storage is unavailable or changed.", 409
        ) from None


@router.get("/{identity}", dependencies=Private)
def detail(identity: str) -> dict[str, object]:
    try:
        return service.read(evidence.load_policy(), identity)
    except (OSError, ValueError, KeyError, TypeError):
        raise fail("SNAPSHOT_INTEGRITY_ERROR", "Snapshot is unavailable or changed.", 409) from None
