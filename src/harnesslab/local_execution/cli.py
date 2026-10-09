from __future__ import annotations

import asyncio
import json
import os
import signal

import typer

from harnesslab.core.config import Settings
from harnesslab.db.session import create_engine, create_session_factory
from harnesslab.local_execution.worker import LocalWorker

worker_app = typer.Typer(help="Independent local single-attempt Worker; keyless Fake only.")


async def run_worker(*, continuous: bool) -> None:
    engine = create_engine(Settings.without_dotenv(database_url=os.environ["DATABASE_URL"]))
    current = asyncio.current_task()
    assert current is not None
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGTERM, current.cancel)
    try:
        worker = LocalWorker(create_session_factory(engine))
        while True:
            run_id = await worker.once()
            typer.echo(
                json.dumps({"run_id": run_id, "real_execution_enabled": False, "model_calls": 0})
            )
            if not continuous or current.cancelling():
                return
            if run_id is None:
                await asyncio.sleep(1)
    finally:
        loop.remove_signal_handler(signal.SIGTERM)
        await engine.dispose()


def invoke(*, continuous: bool) -> None:
    if os.environ.get("HARNESSLAB_PUBLIC_DEMO_MANIFEST"):
        raise typer.BadParameter("Public Demo cannot host an execution Worker")
    try:
        asyncio.run(run_worker(continuous=continuous))
    except (KeyboardInterrupt, asyncio.CancelledError):
        raise typer.Exit(code=0) from None
    except Exception:
        # Error messages never include environment values, DB credentials or native output.
        typer.echo(
            "WORKER_STOPPED: configuration, ownership, isolation or persistence check failed."
        )
        raise typer.Exit(code=2) from None


@worker_app.command("once")
def once() -> None:
    """Recover without redispatch and consume at most one authorization."""
    invoke(continuous=False)


@worker_app.command("serve")
def serve() -> None:
    """Poll the local durable queue. SIGTERM stops active work safely; never requeue attempts."""
    invoke(continuous=True)
