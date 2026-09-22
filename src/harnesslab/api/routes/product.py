"""Public mode metadata; readiness remains a separate runtime check."""

from typing import Literal

from fastapi import APIRouter


def product_router(mode: Literal["demo", "workspace"]) -> APIRouter:
    router = APIRouter()

    @router.get("/product")
    def product() -> dict[str, str]:
        return {
            "mode": mode,
            "persistence": "none" if mode == "demo" else "postgresql",
            "health_path": "/api/demo/health" if mode == "demo" else "/api/health",
        }

    return router
