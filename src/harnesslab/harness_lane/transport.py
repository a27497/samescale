"""Subject communication boundary. CLI plans and captures stay in these implementations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from harnesslab.harness_lane.adapter import CodexBackend, CodexHarnessAdapter, HarnessAdapterError
from harnesslab.harness_lane.docker_backend import CodexBackendExecutionError
from harnesslab.harness_lane.models import (
    CodexBackendFailureEvidence,
    CodexCollection,
    CodexHarnessProfile,
    CodexProcessCapture,
)
from harnesslab.harness_lane.prompt import CodexHarnessPrompt
from harnesslab.multi_harness.adapter import MultiHarnessAdapter, MultiHarnessBackend
from harnesslab.multi_harness.diagnostics import SafeProcessDiagnostics, safe_process_diagnostics
from harnesslab.multi_harness.models import MultiHarnessCollection, MultiHarnessProfile
from harnesslab.multi_harness.prompt import MultiHarnessPrompt


@dataclass(frozen=True)
class SubjectWorkspace:
    """Server-owned sandbox handle; never supplied by a browser or persisted in a request."""

    reference: str
    workspace: Path
    context: Path | None


@dataclass(frozen=True)
class SubjectRequest[ProfileT, PromptT]:
    execution_id: str
    task_id: str
    profile: ProfileT
    prompt: PromptT
    workspace_reference: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z0-9-]{1,100}", self.execution_id):
            raise HarnessAdapterError("invalid subject execution identity")
        if self.workspace_reference != self.execution_id:
            raise HarnessAdapterError("subject workspace must belong to this attempt")


@dataclass(frozen=True)
class SubjectObservation[CollectionT]:
    """Sanitized adapter output. RETURNED is communication completion, not correctness."""

    execution_id: str
    collection: CollectionT
    completion: Literal["RETURNED", "FAILED", "TIMED_OUT", "CANCELLED"]
    duration_ms: int
    # Optional legacy CLI provenance for unchanged frozen evidence schemas.
    exit_code: int | None = None
    timed_out: bool = False
    cancelled: bool = False
    diagnostics: SafeProcessDiagnostics | None = None
    backend_failure: CodexBackendFailureEvidence | None = None

    def __post_init__(self) -> None:
        if self.duration_ms < 0 or not re.fullmatch(r"[a-z0-9-]{1,100}", self.execution_id):
            raise HarnessAdapterError("invalid subject observation identity or duration")
        if not isinstance(self.collection, (CodexCollection, MultiHarnessCollection)):
            raise HarnessAdapterError("subject observation requires a normalized collection")
        failed = self.collection.failure_category is not None or self.backend_failure is not None
        if self.completion != _completion(
            timed_out=self.timed_out,
            cancelled=self.cancelled,
            failed=failed,
        ) or (self.completion != "RETURNED" and not failed):
            raise HarnessAdapterError(
                "subject completion disagrees with normalized failure evidence"
            )


class SubjectTransport[ProfileT, PromptT, CollectionT](Protocol):
    @property
    def artifact_secret_values(self) -> tuple[str, ...]: ...

    async def execute(
        self, request: SubjectRequest[ProfileT, PromptT], workspace: SubjectWorkspace
    ) -> SubjectObservation[CollectionT]: ...


def _workspace(request_reference: str, workspace: SubjectWorkspace) -> None:
    if request_reference != workspace.reference:
        raise HarnessAdapterError("subject workspace reference mismatch")


def _completion(
    *,
    timed_out: bool,
    cancelled: bool,
    failed: bool,
) -> Literal["RETURNED", "FAILED", "TIMED_OUT", "CANCELLED"]:
    if cancelled:
        return "CANCELLED"
    if timed_out:
        return "TIMED_OUT"
    return "FAILED" if failed else "RETURNED"


class CodexCLITransport:
    def __init__(self, adapter: CodexHarnessAdapter, backend: CodexBackend) -> None:
        self.adapter = adapter
        self.backend = backend

    @property
    def artifact_secret_values(self) -> tuple[str, ...]:
        return self.backend.artifact_secret_values

    async def execute(
        self,
        request: SubjectRequest[CodexHarnessProfile, CodexHarnessPrompt],
        workspace: SubjectWorkspace,
    ) -> SubjectObservation[CodexCollection]:
        _workspace(request.workspace_reference, workspace)
        failure = None
        try:
            self.adapter.preflight(request.profile)
            plan = self.adapter.prepare(
                request.profile,
                request.prompt,
                workspace=workspace.workspace,
                context=workspace.context,
                task_id=request.task_id,
            )
            capture = await self.adapter.execute(plan, self.backend)
        except CodexBackendExecutionError as exc:
            failure = exc.evidence
            capture = CodexProcessCapture(
                lines=(),
                exit_code=failure.exit_code,
                duration_ms=failure.duration_ms,
                timed_out=failure.timed_out,
                cancelled=failure.cancelled,
            )
        collection = self.adapter.collect(capture, secret_values=self.artifact_secret_values)
        if failure is None:
            self.adapter.normalize(collection)
        return SubjectObservation(
            execution_id=request.execution_id,
            collection=collection,
            completion=_completion(
                timed_out=capture.timed_out,
                cancelled=capture.cancelled,
                failed=failure is not None or collection.failure_category is not None,
            ),
            duration_ms=capture.duration_ms,
            exit_code=capture.exit_code,
            timed_out=capture.timed_out,
            cancelled=capture.cancelled,
            backend_failure=failure,
        )


class MultiHarnessCLITransport:
    def __init__(self, adapter: MultiHarnessAdapter, backend: MultiHarnessBackend) -> None:
        self.adapter = adapter
        self.backend = backend

    @property
    def artifact_secret_values(self) -> tuple[str, ...]:
        return self.backend.artifact_secret_values

    async def execute(
        self,
        request: SubjectRequest[MultiHarnessProfile, MultiHarnessPrompt],
        workspace: SubjectWorkspace,
    ) -> SubjectObservation[MultiHarnessCollection]:
        _workspace(request.workspace_reference, workspace)
        self.adapter.preflight(request.profile)
        plan = self.adapter.prepare(
            request.profile,
            request.prompt,
            workspace=workspace.workspace,
            context=workspace.context,
            task_id=request.task_id,
        )
        capture = await self.backend.run(plan)
        collection = self.adapter.collect(capture, secret_values=self.artifact_secret_values)
        return SubjectObservation(
            execution_id=request.execution_id,
            collection=collection,
            completion=_completion(
                timed_out=capture.timed_out,
                cancelled=capture.cancelled,
                failed=collection.failure_category is not None,
            ),
            duration_ms=capture.duration_ms,
            exit_code=capture.exit_code,
            timed_out=capture.timed_out,
            cancelled=capture.cancelled,
            diagnostics=safe_process_diagnostics(
                capture, secret_values=self.artifact_secret_values
            ),
        )
