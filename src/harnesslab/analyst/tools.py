from __future__ import annotations

from harnesslab.analyst.evidence import AnalystEvidenceRepository
from harnesslab.analyst.models import (
    CompareCellsCall,
    GetAblationCall,
    GetTaskContractCall,
    InspectFailureCall,
    InspectTraceCall,
    QueryRunsCall,
    ToolCall,
    ToolEvidence,
    ToolName,
)


class AnalystToolRegistry:
    """The complete and intentionally closed Phase J Agent tool surface."""

    def __init__(self, repository: AnalystEvidenceRepository) -> None:
        self._repository = repository

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(name.value for name in ToolName)

    async def execute(self, call: ToolCall) -> tuple[ToolEvidence, ...]:
        if isinstance(call, QueryRunsCall):
            return await self._repository.query_runs(call.arguments)
        if isinstance(call, CompareCellsCall):
            return await self._repository.compare_cells(call.arguments)
        if isinstance(call, InspectTraceCall):
            return await self._repository.inspect_trace(call.arguments)
        if isinstance(call, InspectFailureCall):
            return await self._repository.inspect_failure(call.arguments)
        if isinstance(call, GetTaskContractCall):
            return await self._repository.get_task_contract(call.arguments)
        if isinstance(call, GetAblationCall):
            return await self._repository.get_ablation(call.arguments)
        raise TypeError("unsupported Analyst tool call")
