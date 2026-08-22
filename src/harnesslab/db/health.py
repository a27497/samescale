from sqlalchemy import text

from harnesslab.core.config import Settings
from harnesslab.db.session import create_engine


async def check_database(settings: Settings) -> None:
    """Execute a real round trip; any configuration/driver/database error propagates."""

    engine = create_engine(settings)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    finally:
        await engine.dispose()
