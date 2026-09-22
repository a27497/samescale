"""Foreground, database-free demo using the existing synthetic Analyst journey."""

from __future__ import annotations

import asyncio
import http.client
import json
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import typer
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from harnesslab.analyst.comparison_showcase import ComparisonExample, comparison_example
from harnesslab.analyst.showcase import InvestigationExample, historical_example, offline_demo
from harnesslab.api.routes.product import product_router
from harnesslab.api.routes.registry import registry_router
from harnesslab.api.static import WorkbenchStaticFiles
from harnesslab.productization.assets import (
    AssetError,
    demo_bundle,
    distribution_root,
    validate_bundle,
)

DEMO_HEALTH = "/api/demo/health"


def create_demo_app(dist: Path) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        # Validate the actual synthetic graph before claiming the demo is ready.
        result = await asyncio.wait_for(offline_demo(), timeout=20)
        if result.kind != "offline_fake" or result.metadata["provider_requests"] != 0:
            raise RuntimeError("Synthetic demo validation failed")
        yield

    application = FastAPI(title="SameScale local demo", lifespan=lifespan)
    application.include_router(product_router("demo"), prefix="/api")
    # This app does not register sessions, resume, approval, snapshot, runner or Judge routes.
    application.include_router(registry_router, prefix="/api")

    @application.get(DEMO_HEALTH, response_model=None)
    async def health() -> JSONResponse | dict[str, str]:
        try:
            validate_bundle(dist)
        except AssetError:
            return JSONResponse({"mode": "demo", "status": "invalid_assets"}, status_code=503)
        return {"mode": "demo", "status": "ready", "persistence": "none"}

    @application.post(
        "/api/workbench/analyst/examples/offline", response_model=InvestigationExample
    )
    async def offline() -> InvestigationExample:
        return await offline_demo()

    @application.get(
        "/api/workbench/analyst/examples/historical", response_model=InvestigationExample
    )
    async def historical() -> InvestigationExample | JSONResponse:
        try:
            return historical_example(distribution_root())
        except (OSError, ValueError):
            return JSONResponse(
                {
                    "code": "HISTORICAL_EVIDENCE_UNAVAILABLE",
                    "message": "Frozen evidence is unavailable or invalid.",
                },
                status_code=503,
            )

    @application.get("/api/workbench/analyst/examples/comparison", response_model=ComparisonExample)
    async def comparison() -> ComparisonExample | JSONResponse:
        try:
            return comparison_example(distribution_root())
        except (OSError, ValueError):
            return JSONResponse(
                {
                    "code": "COMPARISON_EVIDENCE_UNAVAILABLE",
                    "message": "Frozen comparison evidence is unavailable or invalid.",
                },
                status_code=503,
            )

    @application.api_route(
        "/api/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"]
    )
    async def full_workspace_required(request: Request, path: str) -> JSONResponse:
        return JSONResponse(
            {
                "code": "FULL_WORKSPACE_REQUIRED",
                "message": (
                    "This is the nonpersistent demo. Run samescale up for the full local workspace."
                ),
            },
            status_code=503,
        )

    application.mount("/", WorkbenchStaticFiles(directory=dist, html=True), name="workbench")
    return application


class DemoServer(uvicorn.Server):
    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        await super().startup(sockets=sockets)
        if self.started:
            typer.echo(f"Ready: http://127.0.0.1:{self.config.port}/analyst")
            typer.echo("离线合成案例 / Synthetic demo · no model calls · no persistence")
            typer.echo("按 Ctrl-C 停止 / Ctrl-C to stop. Full workspace: samescale up")


def demo_command(
    port: Annotated[
        int, typer.Option("--port", min=1, max=65535, help="Loopback demo port.")
    ] = 8000,
) -> None:
    """Open the keyless local UI without Docker or PostgreSQL; Ctrl-C stops it."""
    # Reserve the port before any build, without terminating a process that already owns it.
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", port))
        listener.listen(128)
    except OSError:
        listener.close()
        typer.echo(
            f"NOT_RUNNING demo: port {port} is unavailable. "
            f"Try `samescale demo --port {port + 1 if port < 65535 else 8000}`."
        )
        raise typer.Exit(code=2) from None
    try:
        dist = demo_bundle(build=True)
        application = create_demo_app(dist)
        config = uvicorn.Config(
            application,
            host="127.0.0.1",
            port=port,
            access_log=False,
            log_level="warning",
            loop="harnesslab.core.runtime:selector_loop_factory",
            timeout_graceful_shutdown=5,
        )
        server = DemoServer(config)
        typer.echo("Starting SameScale demo; validating the UI and synthetic investigation…")
        server.run(sockets=[listener])
        if not server.started:
            raise typer.Exit(code=1)
    except AssetError as exc:
        typer.echo(f"NOT_RUNNING demo: {exc}")
        raise typer.Exit(code=exc.exit_code) from None
    finally:
        listener.close()


def check_demo(port: int, *, inspect_assets: bool = False) -> None:
    if inspect_assets:
        try:
            demo_bundle()
        except AssetError as exc:
            typer.echo(f"FAIL demo assets: {exc}")
            raise typer.Exit(code=2) from None
        typer.echo("PASS installed/source UI assets; Docker and PostgreSQL are not required")
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        connection.request("GET", DEMO_HEALTH)
        response = connection.getresponse()
        body = response.read(4097)
        if (
            response.status != 200
            or len(body) > 4096
            or json.loads(body) != {"mode": "demo", "status": "ready", "persistence": "none"}
        ):
            typer.echo("FAIL demo readiness: this endpoint is not a healthy standalone demo")
            raise typer.Exit(code=1)
        connection.request("GET", "/analyst")
        response = connection.getresponse()
        body = response.read(65537)
        if response.status != 200 or len(body) > 65536 or b'id="app"' not in body:
            typer.echo("FAIL demo UI: reinstall or rebuild the product")
            raise typer.Exit(code=1)
    except ConnectionRefusedError:
        typer.echo(f"NOT_RUNNING demo: run `samescale demo --port {port}`")
        raise typer.Exit(code=2) from None
    except (OSError, ValueError, http.client.HTTPException):
        typer.echo("FAIL demo readiness: endpoint unavailable or invalid; check the demo terminal")
        raise typer.Exit(code=1) from None
    finally:
        connection.close()
    typer.echo(
        f"PASS demo ready: http://127.0.0.1:{port}/analyst (nonpersistent synthetic evidence)"
    )
