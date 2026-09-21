from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

import typer

from harnesslab.episodes.service import import_codex_episode, inspect_episode

episode_app = typer.Typer(
    no_args_is_help=True, help="Import completed observations; never execute models."
)


@episode_app.command("import-codex")
def import_codex(
    source: Path,
    store: Annotated[Path, typer.Option("--store")] = Path("harnesslab-runtime/episodes"),
    source_kind: Literal["historical", "synthetic", "unverified"] = typer.Option(
        "unverified", "--source-kind", help="Operator declaration, not authenticity attestation."
    ),
) -> None:
    """Import one completed SameScale Codex H-Lane bundle; metadata only."""
    try:
        episode = import_codex_episode(source, store, source_kind=source_kind)
    except (ValueError, OSError):
        typer.echo("FAIL episode import: invalid, missing, changed or unsupported evidence")
        raise typer.Exit(code=1) from None
    typer.echo(episode.model_dump_json())
    typer.echo(f"episode_identity={episode.identity}")


@episode_app.command("inspect")
def inspect(path: Path) -> None:
    """Check the stored content identity and read metadata without executing a verifier."""
    try:
        episode = inspect_episode(path)
    except (ValueError, OSError):
        typer.echo("FAIL episode inspect: invalid or changed evidence")
        raise typer.Exit(code=1) from None
    typer.echo(episode.model_dump_json())
