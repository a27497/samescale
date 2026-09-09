from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Protocol

from langgraph.graph import END, START, StateGraph

from harnesslab.analyst.backend import AnalystBackend
from harnesslab.analyst.models import (
    AbstainDecision,
    AnalysisRequest,
    AnalysisScope,
    AttributionDraft,
    AttributionReport,
    CompletedToolCall,
    EvidenceEntry,
    ExecutionStatus,
    FinalDecision,
    FinalizationRejectionCode,
    InvestigationState,
    ProposedRegressionPlan,
    ToolCall,
    ToolDecision,
    ToolEvidence,
    safe_public_text,
)
from harnesslab.analyst.report import AttributionValidationError, validate_and_build_report
from harnesslab.comparability.models import canonical_digest


class ToolExecutor(Protocol):
    async def execute(self, call: ToolCall) -> tuple[ToolEvidence, ...]: ...


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
    """Bounded Analyst graph; optional session persistence surrounds each side effect."""

    def __init__(
        self,
        backend: AnalystBackend,
        tools: ToolExecutor,
        *,
        persist: Callable[[InvestigationState], Awaitable[None]] | None = None,
        single_step: bool = False,
        tool_timeout_seconds: float = 10,
    ) -> None:
        self._backend = backend
        self._tools = tools
        self._persist = persist
        self._single_step = single_step
        self._tool_timeout = tool_timeout_seconds
        builder = StateGraph(InvestigationState)
        builder.add_node("decide", self._decide)
        builder.add_node("tools", self._execute_tools)
        builder.add_node("finalize", self._finalize)
        builder.add_conditional_edges(
            START,
            self._start,
            {
                "decide": "decide",
                "tools": "tools",
                "finalize": "finalize",
            },
        )
        builder.add_conditional_edges(
            "decide",
            self._route,
            {
                "tools": "tools",
                "finalize": "finalize",
            },
        )
        builder.add_conditional_edges(
            "tools",
            self._after_tools,
            {
                "decide": "decide",
                "finalize": "finalize",
                "pause": END,
            },
        )
        builder.add_conditional_edges(
            "finalize",
            self._after_finalize,
            {"decide": "decide", "end": END},
        )
        self._graph = builder.compile()

    async def _save(self, state: InvestigationState) -> None:
        if self._persist is not None:
            await self._persist(state)

    @staticmethod
    def _start(state: InvestigationState) -> str:
        if state.limit_reason or isinstance(state.pending, FinalDecision | AbstainDecision):
            return "finalize"
        return "tools" if isinstance(state.pending, ToolDecision) else "decide"

    async def _decide(self, state: InvestigationState) -> dict[str, object]:
        if state.decision_iterations >= state.max_decision_iterations:
            return {"pending": None, "limit_reason": "decision iteration limit reached"}
        if self._persist is not None and state.tool_calls >= state.max_tool_calls:
            return {"pending": None, "limit_reason": "tool call limit reached"}
        state = state.model_copy(
            update={
                "decision_iterations": state.decision_iterations + 1,
                "inflight": "decision",
                "error": None,
            }
        )
        await self._save(state)  # Reserve before invocation; interruption never refunds a decision.
        try:
            decision = await self._backend.decide(
                request=state.request,
                scope=state.scope,
                evidence=state.evidence,
                iteration=state.decision_iterations,
                remaining_tool_calls=state.max_tool_calls - state.tool_calls,
                finalization_rejections=state.finalization_rejections,
            )
            state = state.model_copy(update={"pending": decision, "inflight": None})
        except Exception:
            if self._persist is None:
                raise
            state = state.model_copy(
                update={
                    "pending": None,
                    "inflight": None,
                    "error": "BACKEND_DECISION_FAILED",
                }
            )
        await self._save(state)
        return dict(state)

    @staticmethod
    def _route(state: InvestigationState) -> str:
        if (
            state.error
            or state.limit_reason
            or isinstance(state.pending, FinalDecision | AbstainDecision)
        ):
            return "finalize"
        return "tools"

    def _after_tools(self, state: InvestigationState) -> str:
        if state.limit_reason:
            return "finalize"
        return "pause" if self._single_step else "decide"

    def _after_finalize(self, state: InvestigationState) -> str:
        if state.report is not None or state.error is not None or self._single_step:
            return "end"
        if (
            state.finalization_rejections
            and state.pending is None
            and state.decision_iterations < state.max_decision_iterations
        ):
            return "decide"
        return "end"

    async def _execute_tools(self, state: InvestigationState) -> dict[str, object]:
        decision = state.pending
        if not isinstance(decision, ToolDecision):
            raise RuntimeError("tool node received a non-tool decision")
        for call in decision.calls:
            key = canonical_digest(call.model_dump(mode="json"))
            if self._persist is not None and any(c.key == key for c in state.completed_calls):
                continue  # Reuse observations; never replay ambiguous interrupted reads.
            if state.tool_calls >= state.max_tool_calls:
                return dict(
                    state.model_copy(
                        update={
                            "pending": None,
                            "limit_reason": "tool call limit reached",
                        }
                    )
                )
            record = CompletedToolCall(key=key, call=call, status="RUNNING")
            state = state.model_copy(
                update={
                    "tool_calls": state.tool_calls + 1,
                    "inflight": "tool",
                    "completed_calls": (*state.completed_calls, record),
                }
            )
            await self._save(state)
            try:
                additions = await asyncio.wait_for(self._tools.execute(call), self._tool_timeout)
                state = state.model_copy(
                    update={"evidence": _merge_evidence(state.evidence, additions)}
                )
                record = record.model_copy(
                    update={
                        "status": "COMPLETED",
                        "evidence_refs": tuple(item.ref.id for item in additions),
                    }
                )
            except Exception as exc:
                if self._persist is None:
                    raise
                record = record.model_copy(
                    update={
                        "status": "TIMEOUT" if isinstance(exc, TimeoutError) else "FAILED",
                    }
                )
            state = state.model_copy(
                update={
                    "inflight": None,
                    "completed_calls": (*state.completed_calls[:-1], record),
                }
            )
            await self._save(state)
        state = state.model_copy(update={"pending": None})
        await self._save(state)
        return dict(state)

    async def _finalize(self, state: InvestigationState) -> dict[str, object]:
        if state.error:
            return dict(state)
        pending = state.pending
        if state.limit_reason:
            draft = AttributionDraft(
                summary="Analysis stopped safely at its bounded execution limit.",
                claims=(),
                limitations=(state.limit_reason,),
            )
            status = ExecutionStatus.LIMIT_REACHED
        elif isinstance(pending, AbstainDecision):
            draft = AttributionDraft(
                summary="The Analyst abstained; no conclusion is established.",
                claims=(),
                limitations=(safe_public_text(pending.reason, limit=2_000),),
            )
            status = ExecutionStatus.ABSTAINED
        elif isinstance(pending, FinalDecision):
            draft = pending.draft
            status = ExecutionStatus.COMPLETED
        else:
            raise RuntimeError("final node received no final decision")
        try:
            report = validate_and_build_report(
                request=state.request,
                scope=state.scope,
                draft=draft,
                catalog=state.evidence,
                status=status,
                decision_iterations=state.decision_iterations,
                tool_calls=state.tool_calls,
                max_decision_iterations=state.max_decision_iterations,
                max_tool_calls=state.max_tool_calls,
            )
            proposal = pending.proposed_plan if isinstance(pending, FinalDecision) else None
            if proposal is not None:
                validate_proposal(proposal, state)
            state = state.model_copy(
                update={"report": report, "proposed_plan": proposal, "pending": None}
            )
        except AttributionValidationError as exc:
            state = self._reject_finalization(state, exc.reason)
        except ProposalValidationError:
            state = self._reject_finalization(
                state, FinalizationRejectionCode.INVALID_PROPOSAL_SCOPE
            )
        await self._save(state)
        return dict(state)

    def _reject_finalization(
        self, state: InvestigationState, reason: FinalizationRejectionCode
    ) -> InvestigationState:
        rejected = (*state.finalization_rejections, reason)
        if state.decision_iterations >= state.max_decision_iterations:
            return state.model_copy(
                update={
                    "error": "INVALID_ATTRIBUTION",
                    "pending": None,
                    "finalization_rejections": rejected,
                }
            )
        return state.model_copy(
            update={
                "error": None,
                "pending": None,
                "finalization_rejections": rejected,
            }
        )

    async def advance(self, state: InvestigationState) -> InvestigationState:
        return InvestigationState.model_validate(await self._graph.ainvoke(state))

    async def run(self, request: AnalysisRequest, scope: AnalysisScope) -> AttributionReport:
        result = await self.advance(InvestigationState(request=request, scope=scope))
        if result.report is None:
            raise RuntimeError("Attribution graph completed without a report")
        return result.report


class ProposalValidationError(ValueError):
    pass


def validate_proposal(proposal: ProposedRegressionPlan, state: InvestigationState) -> None:
    if (
        set(proposal.task_ids) - set(state.scope.task_ids)
        or set(proposal.cell_ids) - set(state.scope.cell_ids)
        or set(proposal.evidence_refs) - {entry.ref.id for entry in state.evidence}
    ):
        raise ProposalValidationError(
            "regression proposal is outside the session scope or evidence catalog"
        )
