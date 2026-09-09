from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from harnesslab.analyst.evidence import AnalystEvidenceError
from harnesslab.analyst.models import AnalysisRequest
from harnesslab.analyst.report import AttributionValidationError
from harnesslab.analyst.service import AnalystService, PersistedAnalysis
from harnesslab.core.config import Settings
from harnesslab.db.session import create_engine, create_session_factory
from harnesslab.evidence.reader import EvidenceReadError

analyst_app = typer.Typer(no_args_is_help=True, help="Read-only attribution analysis.")


async def _analyze(
    request: AnalysisRequest,
    *,
    repository_root: Path,
    report_root: Path,
) -> PersistedAnalysis:
    settings = Settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            service = AnalystService(
                session,
                repository_root=repository_root,
                artifact_roots=settings.workbench_artifact_roots,
                report_root=report_root,
            )
            return await service.analyze(request)
    finally:
        await engine.dispose()


@analyst_app.command("analyze")
def analyze(
    experiment_id: str = typer.Argument(help="Persisted experiment identity."),
    question: str = typer.Option(..., "--question", "-q", help="Analysis objective."),
    repository_root: str = typer.Option(".", help="HarnessLab repository root."),
    report_root: str = typer.Option(
        "harnesslab-artifacts/analyst", help="Controlled Analyst report root."
    ),
    backend: str = typer.Option(
        "fake", help="Legacy one-shot backend; real uses Workbench Analyst sessions."
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit canonical report JSON."),
) -> None:
    """Analyze existing immutable evidence without executing or changing it."""

    if backend != "fake":
        typer.echo(
            "FAIL real Analyst is not authorized through the legacy one-shot command; "
            "use Analyst sessions"
        )
        raise typer.Exit(code=2)
    try:
        request = AnalysisRequest(experiment_id=experiment_id, question=question)
        result = asyncio.run(
            _analyze(
                request,
                repository_root=Path(repository_root),
                report_root=Path(report_root),
            )
        )
    except (AnalystEvidenceError, AttributionValidationError, EvidenceReadError, ValueError) as exc:
        typer.echo(f"FAIL Analyst evidence: {exc}")
        raise typer.Exit(code=1) from exc
    if json_output:
        typer.echo(result.report.canonical_json())
        return
    typer.echo(f"status={result.report.execution.status.value}")
    typer.echo(f"analysis_id={result.report.analysis_id}")
    typer.echo(f"report_digest={result.report.digest}")
    typer.echo(f"evidence_count={len(result.report.evidence_catalog)}")
    typer.echo(f"verified_facts={len(result.report.verified_facts)}")
    typer.echo(f"hypotheses={len(result.report.hypotheses)}")
