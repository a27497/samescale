from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from harnesslab.api.workbench_errors import WorkbenchAPIError
from harnesslab.code_snapshots.restore import restore
from harnesslab.episodes.hooks import encode
from harnesslab.external_evidence import service

code_snapshots_app = typer.Typer(
    no_args_is_help=True, help="Restore reviewed code snapshots; no execution."
)


@code_snapshots_app.command("restore")
def restore_command(
    identity: str,
    destination: Annotated[Path, typer.Option("--destination")],
    source_id: Annotated[str, typer.Option("--source-id")],
    task_reference: Annotated[str, typer.Option("--task-reference")],
    task_digest: Annotated[str, typer.Option("--task-digest")],
    confirm: Annotated[bool, typer.Option("--confirm-source-restore")] = False,
) -> None:
    """Restore to a new directory and print a source fragment for MANUAL policy review."""
    if not confirm:
        raise typer.BadParameter("Explicit source restoration confirmation required.")
    try:
        result = restore(
            service.load_policy(),
            identity,
            destination,
            source_id=source_id,
            task_reference=task_reference,
            task_digest=task_digest,
        )
    except (OSError, ValueError, KeyError, TypeError, WorkbenchAPIError):
        raise typer.BadParameter("Snapshot restoration rejected; no source was approved.") from None
    typer.echo(encode(result).decode(), nl=False)
