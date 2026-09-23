from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

import typer

from harnesslab.episodes.hooks import freeze_hook_case, import_hook_episode
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


@episode_app.command("import-hooks")
def import_hooks(
    source: Path,
    store: Annotated[Path, typer.Option("--store")],
    source_kind: Literal["historical", "synthetic", "unverified"] = "unverified",
) -> None:
    """Import paired, completed native hook receipts; never read transcripts."""
    try:
        episode = import_hook_episode(source, store, source_kind=source_kind)
    except (ValueError, OSError, TypeError):
        typer.echo("FAIL_CLOSED hook import")
        raise typer.Exit(code=1) from None
    typer.echo(episode.model_dump_json())
    typer.echo(f"episode_identity={episode.identity}")


@episode_app.command("freeze-hooks")
def freeze_hooks(
    source: Path,
    store: Annotated[Path, typer.Option("--store")],
    output: Annotated[Path, typer.Option("--output")],
    source_kind: Literal["historical", "synthetic", "unverified"] = "unverified",
    verification: Annotated[Path | None, typer.Option("--verification")] = None,
    verification_sha256: Annotated[str | None, typer.Option("--verification-sha256")] = None,
) -> None:
    """Freeze observed tool failures as a CUSTOM offline regression case."""
    try:
        if verification is not None and verification_sha256 is not None:
            from harnesslab.episodes.verified_hooks import freeze_verified_hook_case

            digest = freeze_verified_hook_case(
                source, store, verification, verification_sha256, output, source_kind=source_kind
            )
        elif verification is not None or verification_sha256 is not None:
            raise ValueError("verification requires an external digest")
        else:
            digest = freeze_hook_case(source, store, output, source_kind=source_kind)
    except (ValueError, OSError, TypeError):
        typer.echo("FAIL_CLOSED hook freeze")
        raise typer.Exit(code=1) from None
    typer.echo(f"case_digest={digest}")
