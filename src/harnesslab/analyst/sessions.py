from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import Field, model_validator
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from harnesslab.analyst.backend import AnalystBackend, FakeAnalystBackend
from harnesslab.analyst.evidence import AnalystEvidenceRepository
from harnesslab.analyst.graph import AttributionGraph, validate_proposal
from harnesslab.analyst.models import (
    AnalysisRequest,
    FinalizationRejectionCode,
    InvestigationState,
    ProposedRegressionPlan,
    StrictModel,
    ToolCall,
    ToolEvidence,
)
from harnesslab.analyst.real_backend import (
    AnalystProfile,
    DecisionUsage,
    RealAnalystBackend,
    decision_json_schema,
    request_input_bytes,
    resolve_analyst_profile,
    spend_reasons,
)
from harnesslab.analyst.tools import AnalystToolRegistry
from harnesslab.budget.models import AnalystSpendLimits
from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.common import Sha256Digest
from harnesslab.db.models.analyst import AnalystSessionRecord
from harnesslab.registry.service import registry_catalog


class AnalystSessionError(ValueError):
    pass


class CreateInvestigation(AnalysisRequest):
    backend: Literal["fake", "real"] = "fake"
    provider_profile_id: str | None = Field(default=None, min_length=1, max_length=100)
    decision_limit: int = Field(default=8, ge=1, le=8)
    tool_limit: int = Field(default=12, ge=1, le=12)
    spend_limits: AnalystSpendLimits | None = None

    @model_validator(mode="after")
    def backend_selection_is_explicit(self) -> CreateInvestigation:
        if (self.backend == "real") != (self.provider_profile_id is not None):
            raise ValueError("only real investigations require a registry profile")
        if (self.backend == "real") != (self.spend_limits is not None):
            raise ValueError("real investigations require explicit spend limits; Fake does not")
        if self.spend_limits and self.spend_limits.provider_requests > self.decision_limit:
            raise ValueError("request ceiling cannot exceed decision limit")
        return self


class ApprovalRequest(StrictModel):
    scope_digest: Sha256Digest
    proposal_digest: Sha256Digest
    reviewed_by: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9 ._@-]+$")


class PlanApproval(ApprovalRequest):
    session_id: str
    approved_at: datetime
    execution_authorized: Literal[False] = False


class AnalystSession(StrictModel):
    session_id: str
    backend: Literal["fake", "real"]
    profile: AnalystProfile | None = None
    state: InvestigationState
    usage: tuple[DecisionUsage, ...] = ()
    approval: PlanApproval | None = None
    spend_limits: AnalystSpendLimits | None = None

    @property
    def scope_digest(self) -> str:
        return canonical_digest(self.state.scope.model_dump(mode="json"))

    @property
    def proposal_digest(self) -> str | None:
        if self.state.proposed_plan is None:
            return None
        return canonical_digest(
            {
                "session_id": self.session_id,
                "scope_digest": self.scope_digest,
                "proposal": self.state.proposed_plan.model_dump(mode="json"),
            }
        )

    @property
    def status(self) -> str:
        if self.state.inflight:
            return "RUNNING"
        if self.state.error:
            return "FAILED"
        return self.state.report.execution.status.value if self.state.report else "PAUSED"

    def public_view(self) -> dict[str, Any]:
        runtime = self.profile.runtime if self.profile else None
        totals: dict[str, object] = {}
        for name in ("input_tokens", "output_tokens", "total_tokens"):
            values = [getattr(item.tokens, name) for item in self.usage]
            totals[name] = sum(values) if all(value is not None for value in values) else None
        costs = [item.cost_usd for item in self.usage]
        totals["cost_usd"] = (
            str(sum(value for value in costs if value is not None))
            if all(value is not None for value in costs)
            else None
        )
        latency = [item.latency_ms for item in self.usage]
        totals["latency_ms"] = (
            sum(value for value in latency if value is not None)
            if all(value is not None for value in latency)
            else None
        )
        invocations = [item.invocation_started for item in self.usage]
        return {
            "spend_limits": self.spend_limits.model_dump(mode="json")
            if self.spend_limits
            else None,
            "session_id": self.session_id,
            "backend": self.backend,
            "status": self.status,
            "request": self.state.request.model_dump(mode="json"),
            "scope": self.state.scope.model_dump(mode="json"),
            "scope_digest": self.scope_digest,
            "profile_id": self.profile.profile_id if self.profile else None,
            "profile_digest": self.profile.profile_digest if self.profile else None,
            "provider": runtime.provider if runtime else None,
            "model": runtime.requested_model if runtime else None,
            "route": runtime.provider_route_identity if runtime else None,
            "decision_iterations": self.state.decision_iterations,
            "tool_calls": self.state.tool_calls,
            "decision_limit": self.state.max_decision_iterations,
            "tool_limit": self.state.max_tool_calls,
            "max_output_tokens_per_request": self.spend_limits.output_tokens_per_request
            if self.spend_limits
            else runtime.reasoning.max_output_tokens
            if runtime
            else None,
            "request_timeout_seconds": self.spend_limits.timeout_seconds
            if self.spend_limits
            else runtime.request_timeout_seconds
            if runtime
            else None,
            "request_count": sum(item is True for item in invocations)
            if all(item is not None for item in invocations)
            else None,
            "request_budget_used": len(self.usage),
            "usage": [item.model_dump(mode="json") for item in self.usage],
            "totals": totals,
            "evidence": [entry.model_dump(mode="json") for entry in self.state.evidence],
            "completed_calls": [
                call.model_dump(mode="json") for call in self.state.completed_calls
            ],
            "error": self.state.error,
            "finalization_rejections": [item.value for item in self.state.finalization_rejections],
            "report": self.state.report.model_dump(mode="json") if self.state.report else None,
            "proposed_plan": self.state.proposed_plan.model_dump(mode="json")
            if self.state.proposed_plan
            else None,
            "proposal_digest": self.proposal_digest,
            "approval": self.approval.model_dump(mode="json") if self.approval else None,
        }


class _SessionTools:
    def __init__(self, service: AnalystSessions, state: InvestigationState) -> None:
        self.service = service
        self.state = state

    async def execute(self, call: ToolCall) -> tuple[ToolEvidence, ...]:
        # Evidence reads have their own read-only transaction, separate from the session journal.
        async with AsyncSession(self.service.engine) as session:
            repository = self.service.repository(session, self.state.request.experiment_id)
            if await repository.scope() != self.state.scope:
                raise AnalystSessionError("persisted investigation scope changed")
            return await AnalystToolRegistry(repository).execute(call)


class AnalystSessions:
    def __init__(
        self,
        engine: AsyncEngine,
        *,
        repository_root: Path,
        artifact_roots: tuple[Path, ...],
        environment: Mapping[str, str],
        real_enabled: bool = False,
    ) -> None:
        self.engine = engine
        self.root = repository_root
        self.artifact_roots = artifact_roots
        self.environment = environment
        self.real_enabled = real_enabled

    def repository(self, session: AsyncSession, experiment_id: str) -> AnalystEvidenceRepository:
        return AnalystEvidenceRepository(
            session,
            experiment_id=experiment_id,
            repository_root=self.root,
            artifact_roots=self.artifact_roots,
        )

    async def create(self, request: CreateInvestigation) -> AnalystSession:
        async with AsyncSession(self.engine) as reader:
            scope = await self.repository(reader, request.experiment_id).scope()
        profile = None
        if request.provider_profile_id is not None:
            profile = resolve_analyst_profile(
                registry_catalog(self.root, self.environment),
                request.provider_profile_id,
                self.root,
            )
        value = AnalystSession(
            session_id="analyst-" + uuid4().hex,
            backend=request.backend,
            profile=profile,
            spend_limits=request.spend_limits,
            state=InvestigationState(
                request=AnalysisRequest(
                    experiment_id=request.experiment_id, question=request.question
                ),
                scope=scope,
                max_decision_iterations=request.decision_limit,
                max_tool_calls=request.tool_limit,
            ),
        )
        async with AsyncSession(self.engine) as session, session.begin():
            session.add(
                AnalystSessionRecord(
                    id=value.session_id,
                    experiment_id=request.experiment_id,
                    state_json=value.model_dump(mode="json"),
                )
            )
        return value

    async def get(self, session_id: str) -> AnalystSession:
        async with AsyncSession(self.engine) as session:
            return await self._load(session, session_id)

    async def list(self, experiment_id: str) -> tuple[AnalystSession, ...]:
        async with AsyncSession(self.engine) as session:
            rows = await session.scalars(
                select(AnalystSessionRecord)
                .where(
                    AnalystSessionRecord.experiment_id == experiment_id,
                )
                .order_by(AnalystSessionRecord.created_at.desc())
                .limit(100)
            )
            return tuple(AnalystSession.model_validate(row.state_json) for row in rows)

    @staticmethod
    async def _load(session: AsyncSession, session_id: str) -> AnalystSession:
        row = await session.get(AnalystSessionRecord, session_id, populate_existing=True)
        if row is None:
            raise AnalystSessionError("Analyst session does not exist")
        return AnalystSession.model_validate(row.state_json)

    @staticmethod
    async def _save(session: AsyncSession, value: AnalystSession) -> None:
        row = await session.get(AnalystSessionRecord, value.session_id)
        if row is None:
            raise AnalystSessionError("Analyst session does not exist")
        row.state_json = value.model_dump(mode="json")
        row.updated_at = datetime.now(UTC)
        await session.commit()

    @asynccontextmanager
    async def _locked(self, session_id: str) -> AsyncIterator[AsyncSession]:
        # A connection-owned PostgreSQL lock survives journal commits and is released on
        # disconnect. No worker lease, scheduler or generic checkpoint service is needed.
        async with self.engine.connect() as connection:
            locked = await connection.scalar(
                text("SELECT pg_try_advisory_lock(hashtextextended(:id, 0))"), {"id": session_id}
            )
            await connection.commit()
            if not locked:
                raise AnalystSessionError("Analyst session is busy")
            try:
                async with AsyncSession(bind=connection, expire_on_commit=False) as session:
                    yield session
            finally:
                await connection.rollback()
                await connection.execute(
                    text("SELECT pg_advisory_unlock(hashtextextended(:id, 0))"), {"id": session_id}
                )
                await connection.commit()

    def _backend(self, value: AnalystSession) -> AnalystBackend:
        if value.backend == "fake":
            return FakeAnalystBackend()
        assert value.profile is not None
        current = resolve_analyst_profile(
            registry_catalog(self.root, self.environment), value.profile.profile_id, self.root
        )
        if current.digest != value.profile.digest:
            raise AnalystSessionError(
                "Analyst registry profile changed; create a new investigation"
            )
        return RealAnalystBackend(
            value.profile,
            environment=self.environment,
            completed_calls=value.state.completed_calls,
            decision_limit=value.state.max_decision_iterations,
            budget=value.spend_limits,
            previous_usage=value.usage,
        )

    async def preflight(self, session_id: str) -> dict[str, Any]:
        return await self._preflight(await self.get(session_id))

    async def _preflight(self, value: AnalystSession) -> dict[str, Any]:
        reasons: list[str] = []
        profile = value.profile
        input_bytes = None
        credential_status = "MISSING"
        base_url_status = "MISSING"
        if value.backend != "real" or profile is None:
            reasons.append("REAL_SESSION_REQUIRED")
        else:
            runtime = profile.runtime
            credential_status = (
                "SET"
                if self.environment.get(runtime.credential_reference or "", "").strip()
                else "MISSING"
            )
            base_url_status = (
                "SET"
                if runtime.base_url
                or self.environment.get(runtime.base_url_reference or "", "").strip()
                else "MISSING"
            )
            if credential_status == "MISSING":
                reasons.append("CREDENTIAL_REFERENCE_MISSING")
            if base_url_status == "MISSING":
                reasons.append("BASE_URL_REFERENCE_MISSING")
            else:
                try:
                    runtime.resolve_base_url(self.environment)
                except ValueError:
                    reasons.append("BASE_URL_REFERENCE_INVALID")
            try:
                self._backend(value)  # Registry drift/enablement only; never invokes a provider.
            except (ValueError, OSError):
                reasons.append("PROFILE_DRIFT_OR_UNAVAILABLE")
            if value.spend_limits is None:
                reasons.append("SPEND_LIMITS_MISSING")
            else:
                backend = RealAnalystBackend(
                    profile,
                    environment=self.environment,
                    budget=value.spend_limits,
                    completed_calls=value.state.completed_calls,
                    decision_limit=value.state.max_decision_iterations,
                )
                invocation = backend.prepare(
                    request=value.state.request,
                    scope=value.state.scope,
                    evidence=value.state.evidence,
                    iteration=value.state.decision_iterations + 1,
                    remaining_tool_calls=value.state.max_tool_calls - value.state.tool_calls,
                    finalization_rejections=value.state.finalization_rejections,
                )
                input_bytes = request_input_bytes(invocation)
                reasons.extend(spend_reasons(profile, value.spend_limits, value.usage, invocation))
        try:
            async with AsyncSession(self.engine) as reader:
                if (
                    await self.repository(reader, value.state.request.experiment_id).scope()
                    != value.state.scope
                ):
                    reasons.append("EVIDENCE_SCOPE_DRIFT")
        except (ValueError, OSError):
            reasons.append("EVIDENCE_SCOPE_UNAVAILABLE")
        if value.state.inflight:
            reasons.append("INTERRUPTED_OR_RUNNING_REQUEST")
        if value.state.pending is not None:
            reasons.append("PENDING_DECISION_MUST_RESUME_WITHOUT_PROVIDER")
        if value.state.report is not None:
            reasons.append("SESSION_TERMINAL")
        if value.state.decision_iterations >= value.state.max_decision_iterations:
            reasons.append("DECISION_CEILING_REACHED")
        if value.state.tool_calls >= value.state.max_tool_calls:
            reasons.append("TOOL_CEILING_REACHED")
        result = {
            "kind": "REAL_AGENT_SMOKE",
            "session_id": value.session_id,
            "session_digest": canonical_digest(value.model_dump(mode="json")),
            "status": "BLOCKED" if reasons else "READY",
            "reasons": list(dict.fromkeys(reasons)),
            "profile_id": profile.profile_id if profile else None,
            "profile_digest": profile.profile_digest if profile else None,
            "frozen_profile_digest": profile.digest if profile else None,
            "provider": profile.runtime.provider if profile else None,
            "model": profile.runtime.requested_model if profile else None,
            "route": profile.runtime.provider_route_identity if profile else None,
            "credential_reference_status": credential_status,
            "base_url_reference_status": base_url_status,
            "structured_output_contract": {
                "envelope": "BackendDecision",
                "schema_digest": canonical_digest(decision_json_schema()),
                "live_verified": False,
            },
            "goal": value.state.request.question,
            "evidence_scope": value.state.scope.model_dump(mode="json"),
            "scope_digest": value.scope_digest,
            "decision_ceiling": value.state.max_decision_iterations,
            "tool_ceiling": value.state.max_tool_calls,
            "spend_limits": value.spend_limits.model_dump(mode="json")
            if value.spend_limits
            else None,
            "next_input_bytes": input_bytes,
            "input_token_reservation_basis": "KNOWN_REGISTRY_CONTEXT_WINDOW"
            if profile and profile.context_window_tokens
            else "UNKNOWN",
            "input_token_upper_bound": profile.context_window_tokens if profile else None,
            "pricing_basis": profile.pricing.model_dump(mode="json")
            if profile and profile.pricing
            else None,
            "request_budget_used": len(value.usage),
            "observed_totals": value.public_view()["totals"],
            "server_real_enabled": self.real_enabled,
            "per_step_confirmation_required": True,
            "execution_authorized": False,
        }
        result["preflight_digest"] = canonical_digest(result)
        return result

    async def resume(self, session_id: str, *, confirm_real: bool = False) -> AnalystSession:
        async with self._locked(session_id) as session:
            value = await self._load(session, session_id)
            if value.state.report is not None:
                return value
            if value.backend == "real" and not (self.real_enabled and confirm_real):
                raise AnalystSessionError(
                    "real Analyst requires server enablement and explicit invocation confirmation"
                )
            if value.backend == "real" and value.spend_limits is None:
                # Old journals stay readable, but are neither upgraded nor assigned a budget.
                raise AnalystSessionError("SPEND_LIMITS_MISSING")
            async with AsyncSession(self.engine) as reader:
                if (
                    await self.repository(reader, value.state.request.experiment_id).scope()
                    != value.state.scope
                ):
                    raise AnalystSessionError("persisted investigation scope changed")
            backend = self._backend(value)
            state = value.state
            if state.inflight:
                state = state.model_copy(
                    update={
                        "inflight": None,
                        "completed_calls": tuple(
                            c.model_copy(update={"status": "INTERRUPTED"})
                            if c.status == "RUNNING"
                            else c
                            for c in state.completed_calls
                        ),
                    }
                )
                value = value.model_copy(
                    update={
                        "usage": tuple(
                            u.model_copy(update={"status": "INTERRUPTED"})
                            if u.status == "RESERVED"
                            else u
                            for u in value.usage
                        )
                    }
                )
            state_updates: dict[str, object] = {"error": None}
            if state.error == "INVALID_ATTRIBUTION" and not state.finalization_rejections:
                state_updates["finalization_rejections"] = (FinalizationRejectionCode.UNKNOWN,)
            state = state.model_copy(update=state_updates)

            async def persist(current: InvestigationState) -> None:
                nonlocal value
                usage = list(value.usage)
                if isinstance(backend, RealAnalystBackend):
                    if current.inflight == "decision" and not any(
                        u.iteration == current.decision_iterations for u in usage
                    ):
                        usage.append(DecisionUsage(iteration=current.decision_iterations))
                    if backend.last_usage is not None:
                        usage = [
                            backend.last_usage if u.iteration == backend.last_usage.iteration else u
                            for u in usage
                        ]
                approval = (
                    value.approval if current.proposed_plan == value.state.proposed_plan else None
                )
                value = value.model_copy(
                    update={"state": current, "usage": tuple(usage), "approval": approval}
                )
                await self._save(session, value)

            await persist(state)
            if isinstance(backend, RealAnalystBackend):

                async def reserve(usage: DecisionUsage) -> None:
                    nonlocal value
                    value = value.model_copy(
                        update={
                            "usage": tuple(
                                usage if old.iteration == usage.iteration else old
                                for old in value.usage
                            )
                        }
                    )
                    await self._save(session, value)

                backend.reserve = reserve
                if (
                    state.pending is None
                    and state.decision_iterations < state.max_decision_iterations
                    and state.tool_calls < state.max_tool_calls
                ):
                    preflight = await self._preflight(value)
                    if preflight["status"] != "READY":
                        value = value.model_copy(
                            update={
                                "state": value.state.model_copy(
                                    update={"error": "SPEND_PREFLIGHT_BLOCKED"}
                                )
                            }
                        )
                        await self._save(session, value)
                        raise AnalystSessionError(
                            "SPEND_PREFLIGHT_BLOCKED: " + ",".join(preflight["reasons"])
                        )
            graph = AttributionGraph(
                backend, _SessionTools(self, state), persist=persist, single_step=True
            )
            result = await graph.advance(state)
            await persist(result)
            return value

    async def propose(self, session_id: str, plan: ProposedRegressionPlan) -> AnalystSession:
        async with self._locked(session_id) as session:
            value = await self._load(session, session_id)
            validate_proposal(plan, value.state)
            changed = value.state.proposed_plan != plan
            value = value.model_copy(
                update={
                    "state": value.state.model_copy(update={"proposed_plan": plan}),
                    "approval": None if changed else value.approval,
                }
            )
            await self._save(session, value)
            return value

    async def approve(self, session_id: str, request: ApprovalRequest) -> AnalystSession:
        async with self._locked(session_id) as session:
            value = await self._load(session, session_id)
            if (
                value.proposal_digest is None
                or value.scope_digest != request.scope_digest
                or value.proposal_digest != request.proposal_digest
            ):
                raise AnalystSessionError(
                    "approval does not match the session scope and current proposal"
                )
            value = value.model_copy(
                update={
                    "approval": PlanApproval(
                        **request.model_dump(),
                        session_id=session_id,
                        approved_at=datetime.now(UTC),
                    )
                }
            )
            await self._save(session, value)
            return value  # No experiment, queue, provider or external execution call exists here.
