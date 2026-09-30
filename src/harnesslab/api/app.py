import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.exc import DBAPIError

from harnesslab import __version__
from harnesslab.analyst.api import router as analyst_router
from harnesslab.api.routes.health import router as health_router
from harnesslab.api.routes.local_configuration import router as local_configuration_router
from harnesslab.api.routes.preflight import router as preflight_router
from harnesslab.api.routes.registry import experiment_router, registry_router
from harnesslab.api.routes.workbench import router as workbench_router
from harnesslab.api.static import WorkbenchStaticFiles, resolve_workbench_dist
from harnesslab.api.workbench_errors import (
    WorkbenchAPIError,
    database_unavailable_handler,
    request_validation_error_handler,
    workbench_error_handler,
)
from harnesslab.custom_eval.api import router as custom_eval_router
from harnesslab.demo.integrity import DemoIntegrityError, load_bundle


def create_app(*, workbench_dist: Path | None = None) -> FastAPI:
    application = FastAPI(
        title="SameScale Control API",
        version=__version__,
        description=(
            "SameScale evidence workbench and keyless Registry Lite API (HarnessLab-compatible)"
        ),
    )
    application.state.local_configuration_allowed = not bool(
        os.environ.get("HARNESSLAB_PUBLIC_DEMO_MANIFEST")
    )

    @application.middleware("http")
    async def demo_boundary(request: Request, call_next):  # type: ignore[no-untyped-def]
        manifest = os.environ.get("HARNESSLAB_PUBLIC_DEMO_MANIFEST")
        if manifest:
            if request.url.path == "/":
                return RedirectResponse("/demo", status_code=307)
            # Fixed Fake computation only: no persistence, artifacts, Provider or network.
            allowed_post = request.url.path in {
                "/api/workbench/regression/compare",
                "/api/workbench/analyst/examples/offline",
            } or (
                request.url.path.startswith("/api/workbench/experiments/")
                and request.url.path.endswith("/diagnosis/badcases")
            )
            if request.method not in {"GET", "HEAD"} and not (
                request.method == "POST" and allowed_post
            ):
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": {
                            "code": "PUBLIC_DEMO_READ_ONLY",
                            "message": (
                                "Public demo evidence is read-only. "
                                "Execution and configuration changes are disabled."
                            ),
                        }
                    },
                )
            if (
                request.url.path.startswith("/api/workbench/")
                and request.url.path != "/api/workbench/experiments"
            ):
                try:
                    load_bundle(Path(manifest), os.environ.get("HARNESSLAB_PUBLIC_DEMO_DIGEST", ""))
                except DemoIntegrityError:
                    return JSONResponse(
                        status_code=409,
                        content={
                            "error": {
                                "code": "ARTIFACT_INTEGRITY_ERROR",
                                "message": (
                                    "Public demo evidence integrity failed. "
                                    "No replacement evidence was used."
                                ),
                            }
                        },
                    )
        return await call_next(request)

    application.include_router(local_configuration_router, prefix="/api")
    application.include_router(health_router, prefix="/api")
    application.include_router(analyst_router, prefix="/api")
    application.include_router(workbench_router, prefix="/api")
    application.include_router(registry_router, prefix="/api")
    application.include_router(experiment_router, prefix="/api")
    application.include_router(preflight_router, prefix="/api")
    application.include_router(custom_eval_router, prefix="/api")
    application.add_exception_handler(WorkbenchAPIError, workbench_error_handler)
    application.add_exception_handler(DBAPIError, database_unavailable_handler)
    application.add_exception_handler(RequestValidationError, request_validation_error_handler)
    bundled_workbench = resolve_workbench_dist(workbench_dist)
    if bundled_workbench is not None:
        # Keep this mount last so API routes remain authoritative.
        application.mount(
            "/",
            WorkbenchStaticFiles(directory=bundled_workbench, html=True),
            name="workbench",
        )
    return application


app = create_app()
