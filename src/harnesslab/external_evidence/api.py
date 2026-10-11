from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Response

from harnesslab.api.workbench_errors import WorkbenchAPIError
from harnesslab.external_evidence import service
from harnesslab.external_evidence.models import ImportRequest
from harnesslab.local_plans.api import Private
from harnesslab.local_plans.tasks import fail
from harnesslab.tasks.package import sha256_bytes

router = APIRouter(prefix="/external-evidence", tags=["private-saved-evidence"])


@router.get("/status", dependencies=Private)
def status() -> dict[str, object]:
    return {
        "enabled": bool(os.environ.get("HARNESSLAB_EXTERNAL_EVIDENCE_POLICY")),
        "real_execution_enabled": False,
        "automatic_collection": False,
    }


@router.get("/configuration-check", dependencies=Private)
def configuration_check() -> dict[str, Any]:
    return service.configuration_check()


@router.get("/sources", dependencies=Private)
def sources() -> dict[str, object]:
    policy = service.load_policy()
    # Explicit items only: no directory discovery, filesystem paths or arbitrary uploads.
    return {"items": [s.binding for s in policy.sources]}


@router.post("/records", dependencies=Private)
def ingest(request: ImportRequest) -> dict[str, Any]:
    try:
        return service.ingest(service.load_policy(), request.source_id)
    except service.EvidenceInputError as exc:
        raise fail(exc.code, "Review the approved source, format and retained pins.", 409) from None
    except (OSError, ValueError):
        raise fail(
            "EVIDENCE_IMPORT_REJECTED", "Approved evidence failed safety or integrity checks.", 409
        ) from None


@router.get("/records", dependencies=Private)
def records() -> dict[str, object]:
    policy = service.load_policy()
    try:
        return {"items": service.list_records(policy)}
    except (OSError, ValueError, WorkbenchAPIError):
        raise fail("EVIDENCE_STORAGE_UNSAFE", "Private storage is unavailable.", 403) from None


@router.get("/records/{identity}", dependencies=Private)
def detail(identity: str) -> dict[str, Any]:
    try:
        return service.view(service.load_policy(), identity)
    except PermissionError:
        raise fail("EVIDENCE_STORAGE_UNSAFE", "Private storage is not readable.", 403) from None
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise fail(
            "EVIDENCE_INTEGRITY_ERROR", "Stored evidence is unavailable or changed.", 409
        ) from None


@router.get("/records/{identity}/export", dependencies=Private)
def export(identity: str) -> Response:
    try:
        payload = service.export_record(service.load_policy(), identity)
        return Response(
            payload,
            media_type="application/json",
            headers={
                "Cache-Control": "no-store",
                "X-Evidence-SHA256": sha256_bytes(payload),
                "Content-Disposition": 'attachment; filename="saved-evidence.json"',
            },
        )
    except PermissionError:
        raise fail("EVIDENCE_STORAGE_UNSAFE", "Private storage is not readable.", 403) from None
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise fail(
            "EVIDENCE_INTEGRITY_ERROR", "Unsafe or changed evidence cannot be exported.", 409
        ) from None
