from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Response

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


@router.get("/sources", dependencies=Private)
def sources() -> dict[str, object]:
    policy = service.load_policy()
    # Explicit items only: no directory discovery, filesystem paths or arbitrary uploads.
    return {"items": [s.binding for s in policy.sources]}


@router.post("/records", dependencies=Private)
def ingest(request: ImportRequest) -> dict[str, Any]:
    try:
        return service.ingest(service.load_policy(), request.source_id)
    except (OSError, ValueError):
        raise fail(
            "EVIDENCE_IMPORT_REJECTED", "Approved evidence failed safety or integrity checks.", 409
        ) from None


@router.get("/records", dependencies=Private)
def records() -> dict[str, object]:
    policy = service.load_policy()
    result = []
    try:
        if policy.store.exists():
            for path in sorted(policy.store.iterdir()):
                if path.name.startswith("."):
                    continue  # An interrupted staging directory is never a completed record.
                item = service.view(policy, path.name)
                record = item["record"]
                result.append(
                    {
                        "identity": path.name,
                        "source_id": record["source"]["source_id"],
                        "source_kind": record["source"]["source_kind"],
                        "acceptance": item["diagnosis"]["workspace_acceptance"],
                    }
                )
                if len(result) > 1000:
                    raise ValueError("store limit")
        return {"items": result}
    except (OSError, ValueError):
        raise fail(
            "EVIDENCE_INTEGRITY_ERROR", "Stored evidence is unavailable or changed.", 409
        ) from None


@router.get("/records/{identity}", dependencies=Private)
def detail(identity: str) -> dict[str, Any]:
    try:
        return service.view(service.load_policy(), identity)
    except (OSError, ValueError):
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
    except (OSError, ValueError):
        raise fail(
            "EVIDENCE_INTEGRITY_ERROR", "Unsafe or changed evidence cannot be exported.", 409
        ) from None
