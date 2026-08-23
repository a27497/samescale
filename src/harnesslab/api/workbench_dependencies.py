from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from harnesslab.core.config import get_settings
from harnesslab.db.session import create_engine, create_session_factory


async def workbench_session() -> AsyncIterator[AsyncSession]:
    engine = create_engine(get_settings())
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            yield session
    finally:
        await engine.dispose()


def workbench_artifact_roots() -> tuple[Path, ...]:
    """Server-owned roots permitted for every Workbench artifact read."""

    return tuple(path.resolve() for path in get_settings().workbench_artifact_roots)
