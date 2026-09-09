from __future__ import annotations

import os
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
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
        expected_revision = ScriptDirectory.from_config(config).get_current_head()
        assert expected_revision is not None
        command.upgrade(config, "head")

        with psycopg.connect(temporary_psycopg_url) as connection:
            row = connection.execute(
                "SELECT to_regclass('public.schema_metadata'), "
                "to_regclass('public.execution_lease'), "
                "to_regclass('public.experiment'), "
                "to_regclass('public.experiment_cell'), "
                "to_regclass('public.experiment_run'), "
                "to_regclass('public.experiment_pair'), "
                "to_regclass('public.judge_calibration'), "
                "to_regclass('public.judge_evaluation'), "
                "to_regclass('public.registry_experiment_snapshot'), "
                "to_regclass('public.analyst_session'), "
                "(SELECT version_num FROM alembic_version)"
            ).fetchone()
        assert row == (
            "schema_metadata",
            "execution_lease",
            "experiment",
            "experiment_cell",
            "experiment_run",
            "experiment_pair",
            "judge_calibration",
            "judge_evaluation",
            "registry_experiment_snapshot",
            "analyst_session",
            expected_revision,
        )
        # Round-trip only this session migration; older experiment evidence survives.
        with psycopg.connect(temporary_psycopg_url) as connection:
            connection.execute(
                "INSERT INTO experiment (id,schema_version,name,plan_digest,plan_json,status) "
                "VALUES (%s,1,'preserved',%s,'{}','completed')",
                ("analyst-migration-control", "sha256:" + "1" * 64),
            )
            connection.execute(
                "INSERT INTO analyst_session (id,experiment_id,state_json) "
                "VALUES ('migration-session','analyst-migration-control','{}')"
            )
        command.downgrade(config, "20260904_0006")
        with psycopg.connect(temporary_psycopg_url) as connection:
            assert connection.execute(
                "SELECT to_regclass('public.analyst_session')"
            ).fetchone() == (None,)
            assert connection.execute(
                "SELECT status,plan_digest FROM experiment WHERE id='analyst-migration-control'"
            ).fetchone() == ("completed", "sha256:" + "1" * 64)
        command.upgrade(config, "head")
        with psycopg.connect(temporary_psycopg_url) as connection:
            assert connection.execute("SELECT count(*) FROM analyst_session").fetchone() == (0,)
            assert connection.execute(
                "SELECT count(*) FROM experiment WHERE id='analyst-migration-control'"
            ).fetchone() == (1,)
    finally:
        get_settings.cache_clear()
        os.environ["DATABASE_URL"] = database_url
        with psycopg.connect(admin_url, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(database_name)
                )
            )
