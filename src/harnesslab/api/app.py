from fastapi import FastAPI

from harnesslab import __version__
from harnesslab.api.routes.health import router as health_router
from harnesslab.api.routes.workbench import router as workbench_router
from harnesslab.api.workbench_errors import WorkbenchAPIError, workbench_error_handler


def create_app() -> FastAPI:
    application = FastAPI(
        title="HarnessLab AI Control API",
        version=__version__,
        description="Read-only HarnessLab evidence and Workbench API",
    )
    application.include_router(health_router, prefix="/api")
    application.include_router(workbench_router, prefix="/api")
    application.add_exception_handler(WorkbenchAPIError, workbench_error_handler)
    return application


app = create_app()
