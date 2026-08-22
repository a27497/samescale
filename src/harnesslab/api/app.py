from fastapi import FastAPI

from harnesslab import __version__
from harnesslab.api.routes.health import router as health_router


def create_app() -> FastAPI:
    application = FastAPI(
        title="HarnessLab AI Control API",
        version=__version__,
        description="Phase A control-plane foundation",
    )
    application.include_router(health_router, prefix="/api")
    return application


app = create_app()
