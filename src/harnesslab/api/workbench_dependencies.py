from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from pydantic import ValidationError
from pydantic_settings import SettingsError
from sqlalchemy.ext.asyncio import AsyncSession

from harnesslab.api.workbench_errors import WorkbenchAPIError
from harnesslab.core.config import Settings, get_settings
from harnesslab.db.session import create_engine, create_session_factory


def workspace_settings() -> Settings:
    try:
        return get_settings()
    except (ValidationError, SettingsError):
        raise WorkbenchAPIError(
            503,
            "WORKSPACE_NOT_CONFIGURED",
            "Workspace configuration is missing or invalid. Run `samescale up`, or check "
            "the server DATABASE_URL and artifact-root configuration; then retry.",
        ) from None


async def workbench_session() -> AsyncIterator[AsyncSession]:
    engine = create_engine(workspace_settings())
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            yield session
    finally:
        await engine.dispose()


def workbench_artifact_roots() -> tuple[Path, ...]:
    """Server-owned roots permitted for every Workbench artifact read."""

    return tuple(path.resolve() for path in workspace_settings().workbench_artifact_roots)
