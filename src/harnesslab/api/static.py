from __future__ import annotations

import os
from collections.abc import MutableMapping
from pathlib import Path, PurePosixPath
from typing import Any

from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles

from harnesslab.productization.assets import distribution_root

WORKBENCH_DIST_ENV = "HARNESSLAB_WORKBENCH_DIST"


class WorkbenchStaticFiles(StaticFiles):
    """Serve the bundled Workbench and fall back to its SPA entry point."""

    async def get_response(self, path: str, scope: MutableMapping[str, Any]) -> Response:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404)
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            is_navigation = not PurePosixPath(path).suffix
            if exc.status_code == 404 and is_navigation and scope.get("method") in {"GET", "HEAD"}:
                response = await super().get_response("index.html", scope)
            else:
                raise
        # Revalidate the SPA shell on every navigation, including conditional
        # responses. An old shell can reference chunks removed by an update.
        if not PurePosixPath(path).suffix or path.endswith(".html"):
            response.headers["Cache-Control"] = "no-cache"
        return response


def resolve_workbench_dist(explicit: Path | None = None) -> Path | None:
    """Resolve an explicit/container bundle, or a local production build when present."""

    configured = os.environ.get(WORKBENCH_DIST_ENV)
    candidate = explicit
    required = explicit is not None
    if candidate is None and configured:
        candidate = Path(configured)
        required = True
    if candidate is None:
        repository_build = distribution_root() / "frontend" / "dist"
        candidate = repository_build if repository_build.is_dir() else None
    if candidate is None:
        return None

    candidate = candidate.resolve()
    if not candidate.is_dir() or not (candidate / "index.html").is_file():
        if required:
            raise RuntimeError(
                f"{WORKBENCH_DIST_ENV} must identify a Workbench build containing index.html"
            )
        return None
    return candidate
