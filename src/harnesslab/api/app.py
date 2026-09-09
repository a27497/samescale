from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from harnesslab import __version__
from harnesslab.analyst.api import router as analyst_router
from harnesslab.api.routes.health import router as health_router
from harnesslab.api.routes.preflight import router as preflight_router
from harnesslab.api.routes.registry import experiment_router, registry_router
from harnesslab.api.routes.workbench import router as workbench_router
from harnesslab.api.static import WorkbenchStaticFiles, resolve_workbench_dist
from harnesslab.api.workbench_errors import (
    WorkbenchAPIError,
    request_validation_error_handler,
    workbench_error_handler,
)
from harnesslab.custom_eval.api import router as custom_eval_router


def create_app(*, workbench_dist: Path | None = None) -> FastAPI:
    application = FastAPI(
        title="HarnessLab AI Control API",
        version=__version__,
        description="HarnessLab evidence Workbench and keyless Registry Lite control API",
    )
    application.include_router(health_router, prefix="/api")
    application.include_router(analyst_router, prefix="/api")
    application.include_router(workbench_router, prefix="/api")
    application.include_router(registry_router, prefix="/api")
    application.include_router(experiment_router, prefix="/api")
    application.include_router(preflight_router, prefix="/api")
    application.include_router(custom_eval_router, prefix="/api")
    application.add_exception_handler(WorkbenchAPIError, workbench_error_handler)
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
