from __future__ import annotations

import os
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy.engine import make_url

from harnesslab.core.config import Settings, get_settings
from harnesslab.db.health import check_database


@pytest.mark.integration
async def test_database_connectivity(database_url: str) -> None:
    settings = Settings.without_dotenv(database_url=database_url)
    await check_database(settings)


@pytest.mark.integration
def test_migration_from_empty_database(database_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    source_url = make_url(database_url)
    database_name = f"harnesslab_gate_{uuid4().hex[:12]}"
    psycopg_url = source_url.set(drivername="postgresql")
    admin_url = psycopg_url.set(database="postgres").render_as_string(hide_password=False)
    temporary_url = source_url.set(database=database_name).render_as_string(hide_password=False)
    temporary_psycopg_url = psycopg_url.set(database=database_name).render_as_string(
        hide_password=False
    )

    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))

    try:
        monkeypatch.setenv("DATABASE_URL", temporary_url)
        get_settings.cache_clear()
        config = Config("alembic.ini")
        command.upgrade(config, "head")

        with psycopg.connect(temporary_psycopg_url) as connection:
            row = connection.execute(
                "SELECT to_regclass('public.schema_metadata'), "
                "to_regclass('public.execution_lease'), "
                "(SELECT version_num FROM alembic_version)"
            ).fetchone()
        assert row == ("schema_metadata", "execution_lease", "20260822_0002")
    finally:
        get_settings.cache_clear()
        os.environ["DATABASE_URL"] = database_url
        with psycopg.connect(admin_url, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(database_name)
                )
            )
