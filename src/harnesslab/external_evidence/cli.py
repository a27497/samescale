from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer

from harnesslab.api.workbench_errors import WorkbenchAPIError
from harnesslab.episodes.hooks import encode
from harnesslab.external_evidence import service
from harnesslab.external_evidence.verification import verify_workspace

external_evidence_app = typer.Typer(
    no_args_is_help=True, help="Approved saved evidence; no Agent execution."
)


@external_evidence_app.command("verify-workspace")
def verify(
    identity: str, confirm: Annotated[bool, typer.Option("--confirm-independent-verifier")] = False
) -> None:
    if not confirm:
        raise typer.BadParameter("Explicit independent Verifier authorization required.")
    try:
        policy = service.load_policy()
        receipt = asyncio.run(verify_workspace(policy, identity))
        typer.echo(encode(receipt).decode(), nl=False)
    except (OSError, ValueError, WorkbenchAPIError):
        raise typer.BadParameter(
            "Verifier admission rejected or one attempt already consumed."
        ) from None


@external_evidence_app.command("replay")
def replay(path: Path, sha256: str) -> None:
    try:
        service.safe_root(path)
        if path.stat().st_size > service.MAX_EXPORT:
            raise ValueError("oversized export")
        result = service.replay_export(path.read_bytes(), sha256)
        typer.echo(encode(result).decode(), nl=False)
    except (OSError, ValueError):
        raise typer.BadParameter("Offline evidence integrity verification failed.") from None
