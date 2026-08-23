from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from harnesslab.analyst.backend import AnalystBackend, FakeAnalystBackend
from harnesslab.analyst.evidence import AnalystEvidenceRepository
from harnesslab.analyst.graph import AttributionGraph
from harnesslab.analyst.models import AnalysisRequest, AttributionReport
from harnesslab.analyst.report import persist_report
from harnesslab.analyst.tools import AnalystToolRegistry


@dataclass(frozen=True)
class PersistedAnalysis:
    report: AttributionReport
    json_path: Path
    markdown_path: Path


class AnalystService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        repository_root: Path,
        artifact_roots: tuple[Path, ...],
        report_root: Path,
    ) -> None:
        self._session = session
        self._repository_root = repository_root
        self._artifact_roots = artifact_roots
        self._report_root = report_root

    async def analyze(
        self, request: AnalysisRequest, backend: AnalystBackend | None = None
    ) -> PersistedAnalysis:
        repository = AnalystEvidenceRepository(
            self._session,
            experiment_id=request.experiment_id,
            repository_root=self._repository_root,
            artifact_roots=self._artifact_roots,
        )
        scope = await repository.scope()
        tools = AnalystToolRegistry(repository)
        graph = AttributionGraph(backend or FakeAnalystBackend(), tools)
        report = await graph.run(request, scope)
        json_path, markdown_path = persist_report(report, self._report_root)
        return PersistedAnalysis(report=report, json_path=json_path, markdown_path=markdown_path)
