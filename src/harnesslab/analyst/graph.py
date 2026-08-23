from __future__ import annotations

from typing import Protocol, TypedDict, cast

from langgraph.graph import END, START, StateGraph

from harnesslab.analyst.backend import AnalystBackend
from harnesslab.analyst.models import (
    MAX_DECISION_ITERATIONS,
    MAX_TOOL_CALLS,
    AnalysisRequest,
    AnalysisScope,
    AttributionDraft,
    AttributionReport,
    BackendDecision,
    EvidenceEntry,
    ExecutionStatus,
    FinalDecision,
    ToolCall,
    ToolDecision,
    ToolEvidence,
)
from harnesslab.analyst.report import validate_and_build_report


class ToolExecutor(Protocol):
    async def execute(self, call: ToolCall) -> tuple[ToolEvidence, ...]: ...


class AnalystGraphState(TypedDict):
    request: AnalysisRequest
    scope: AnalysisScope
    evidence: tuple[EvidenceEntry, ...]
    decision_iterations: int
    tool_calls: int
    pending: BackendDecision | None
    limit_reason: str | None
    report: AttributionReport | None


def _merge_evidence(
    catalog: tuple[EvidenceEntry, ...], additions: tuple[ToolEvidence, ...]
) -> tuple[EvidenceEntry, ...]:
    merged = {entry.ref.id: entry for entry in catalog}
    for addition in additions:
        current = merged.get(addition.ref.id)
        if current is None:
            merged[addition.ref.id] = EvidenceEntry(
                ref=addition.ref,
                tools=(addition.tool,),
                digest_bindings=tuple(sorted(set(addition.digest_bindings))),
                data_by_tool={addition.tool.value: addition.data},
            )
            continue
        data = dict(current.data_by_tool)
        data[addition.tool.value] = addition.data
        merged[addition.ref.id] = EvidenceEntry(
            ref=current.ref,
            tools=tuple(sorted(set((*current.tools, addition.tool)), key=lambda item: item.value)),
            digest_bindings=tuple(
                sorted(set((*current.digest_bindings, *addition.digest_bindings)))
            ),
            data_by_tool=data,
        )
    return tuple(merged[key] for key in sorted(merged))


class AttributionGraph:
    """Explicit one-shot LangGraph; no generic Agent, memory, or checkpoint service."""

    def __init__(self, backend: AnalystBackend, tools: ToolExecutor) -> None:
        self._backend = backend
        self._tools = tools
        builder = StateGraph(AnalystGraphState)
        builder.add_node("decide", self._decide)
        builder.add_node("tools", self._execute_tools)
        builder.add_node("finalize", self._finalize)
        builder.add_edge(START, "decide")
        builder.add_conditional_edges(
            "decide",
            self._route,
            {"tools": "tools", "finalize": "finalize"},
        )
        builder.add_edge("tools", "decide")
        builder.add_edge("finalize", END)
        self._graph = builder.compile()

    async def _decide(self, state: AnalystGraphState) -> dict[str, object]:
        iterations = state["decision_iterations"]
        if state["limit_reason"] is not None:
            return {"pending": None}
        if iterations >= MAX_DECISION_ITERATIONS:
            return {"pending": None, "limit_reason": "decision iteration limit reached"}
        decision = await self._backend.decide(
            request=state["request"],
            scope=state["scope"],
            evidence=state["evidence"],
            iteration=iterations + 1,
            remaining_tool_calls=MAX_TOOL_CALLS - state["tool_calls"],
        )
        return {"pending": decision, "decision_iterations": iterations + 1}

    @staticmethod
    def _route(state: AnalystGraphState) -> str:
        if state["limit_reason"] is not None or isinstance(state["pending"], FinalDecision):
            return "finalize"
        return "tools"

    async def _execute_tools(self, state: AnalystGraphState) -> dict[str, object]:
        decision = state["pending"]
        if not isinstance(decision, ToolDecision):
            raise RuntimeError("tool node received a non-tool decision")
        remaining = MAX_TOOL_CALLS - state["tool_calls"]
        if len(decision.calls) > remaining:
            return {"pending": None, "limit_reason": "tool call limit reached"}
        catalog = state["evidence"]
        for call in decision.calls:
            catalog = _merge_evidence(catalog, await self._tools.execute(call))
        return {
            "evidence": catalog,
            "tool_calls": state["tool_calls"] + len(decision.calls),
            "pending": None,
        }

    async def _finalize(self, state: AnalystGraphState) -> dict[str, object]:
        pending = state["pending"]
        if state["limit_reason"] is not None:
            draft = AttributionDraft(
                summary="Analysis stopped safely at its bounded execution limit.",
                claims=(),
                limitations=(state["limit_reason"] or "bounded execution limit reached",),
            )
            status = ExecutionStatus.LIMIT_REACHED
        elif isinstance(pending, FinalDecision):
            draft = pending.draft
            status = ExecutionStatus.COMPLETED
        else:
            raise RuntimeError("final node received no final decision")
        report = validate_and_build_report(
            request=state["request"],
            scope=state["scope"],
            draft=draft,
            catalog=state["evidence"],
            status=status,
            decision_iterations=state["decision_iterations"],
            tool_calls=state["tool_calls"],
        )
        return {"report": report}

    async def run(self, request: AnalysisRequest, scope: AnalysisScope) -> AttributionReport:
        initial: AnalystGraphState = {
            "request": request,
            "scope": scope,
            "evidence": (),
            "decision_iterations": 0,
            "tool_calls": 0,
            "pending": None,
            "limit_reason": None,
            "report": None,
        }
        result = cast(AnalystGraphState, await self._graph.ainvoke(initial))
        report = result["report"]
        if report is None:
            raise RuntimeError("Attribution graph completed without a report")
        return report
