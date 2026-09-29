"""Populate an isolated QA database with existing keyless synthetic Matrix examples.

This intentionally reuses the exercised Phase I fixture builders. It runs Fake
providers and Fake Codex, records the normal executor/verifier artifacts, and
never substitutes fixture JSON for a persisted result. The database and artifact
directory must be dedicated to QA; this script refuses other environments.
"""

from __future__ import annotations

import asyncio
from urllib.parse import urlsplit

from sqlalchemy import func, select
from tests.test_workbench_api import (
    MULTI_TASK_EXPERIMENT_ID,
    REGRESSION_EXPERIMENT_IDS,
    ROOT,
    _matrix_plan,
    _multi_task_matrix_plan,
)

from harnesslab.core.config import get_settings
from harnesslab.db.models.experiment import ExperimentRecord, ExperimentRunRecord
from harnesslab.db.session import create_engine, create_session_factory
from harnesslab.experiment.executor import ExperimentRunExecutor
from harnesslab.experiment.queue import enqueue_plan

EXAMPLE_IDS = (*REGRESSION_EXPERIMENT_IDS, MULTI_TASK_EXPERIMENT_ID)


async def seed() -> None:
    settings = get_settings()
    parsed = urlsplit(settings.database_url_value)
    artifact_root = ROOT / ".phase-i-test-artifacts"
    expected_roots = (artifact_root.resolve(),)
    if (
        settings.environment != "qa"
        or parsed.hostname != "127.0.0.1"
        or parsed.port != 55471
        or parsed.path != "/samescale_qa"
        or tuple(path.resolve() for path in settings.workbench_artifact_roots) != expected_roots
    ):
        raise SystemExit("Refusing to seed anything but the isolated local QA database")

    artifact_root.mkdir(exist_ok=True)
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        for experiment_id in EXAMPLE_IDS:
            expected_count = 18 if experiment_id == MULTI_TASK_EXPERIMENT_ID else 9
            async with factory() as session:
                existing = await session.get(ExperimentRecord, experiment_id)
            if existing is not None:
                async with factory() as session:
                    counts = (
                        await session.execute(
                            select(ExperimentRunRecord.status, func.count())
                            .where(ExperimentRunRecord.experiment_id == experiment_id)
                            .group_by(ExperimentRunRecord.status)
                        )
                    ).all()
                if sum(count for _, count in counts) != expected_count or any(
                    status not in {"completed", "failed_subject"} for status, _ in counts
                ):
                    raise RuntimeError(f"Existing QA example is incomplete: {experiment_id}")
                print(f"Existing complete synthetic example retained: {experiment_id}")
                continue

            plan, bindings = (
                _multi_task_matrix_plan()
                if experiment_id == MULTI_TASK_EXPERIMENT_ID
                else _matrix_plan(experiment_id)
            )
            async with factory() as session, session.begin():
                await enqueue_plan(session, plan)
            executor = ExperimentRunExecutor(
                repository_root=ROOT,
                session_factory=factory,
                bindings=bindings,
                owner=f"qa-seed-{experiment_id}",
            )
            completed = await executor.run_until_idle(experiment_id)
            if len(completed) != expected_count:
                raise RuntimeError(
                    f"{experiment_id}: expected {expected_count} terminal runs, "
                    f"got {len(completed)}"
                )
            print(f"Generated synthetic example: {experiment_id} ({len(completed)} runs)")

        async with factory() as session:
            for experiment_id in EXAMPLE_IDS:
                counts = (
                    await session.execute(
                        select(ExperimentRunRecord.status, func.count())
                        .where(ExperimentRunRecord.experiment_id == experiment_id)
                        .group_by(ExperimentRunRecord.status)
                    )
                ).all()
                print(f"{experiment_id}: {dict(counts)}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
