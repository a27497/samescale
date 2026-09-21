from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

from harnesslab.contracts.common import EvaluationLane
from harnesslab.harness_lane.adapter import CodexBackend, CodexHarnessAdapter, HarnessAdapterError
from harnesslab.harness_lane.models import (
    ChangedPathEvidence,
    ChangedPathStatus,
    CodexBackendFailureEvidence,
    CodexCollection,
    CodexHarnessProfile,
    HarnessFailureCategory,
    HarnessLaneEvidence,
    HarnessLaneOutcome,
    HarnessLaneRunResult,
    WorkspaceFileEvidence,
)
from harnesslab.harness_lane.prompt import CodexHarnessPrompt, render_codex_harness_prompt
from harnesslab.harness_lane.transport import (
    CodexCLITransport,
    SubjectObservation,
    SubjectRequest,
    SubjectTransport,
    SubjectWorkspace,
)
from harnesslab.model_lane.patch import copy_workspace_snapshot
from harnesslab.sandbox.artifacts import (
    ArtifactError,
    assert_tree_has_no_run_secrets,
    make_tree_readable,
    make_tree_writable,
)
from harnesslab.sandbox.models import SandboxArtifactManifest
from harnesslab.sandbox.runner import DockerSandbox
from harnesslab.tasks.package import TaskPackage, TaskPackageError, digest_tree, is_link_like


class CodexHarnessRunError(RuntimeError):
    """Trusted Phase E orchestration could not preserve a safe evidence bundle."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(65_536):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def workspace_inventory(root: Path) -> tuple[WorkspaceFileEvidence, ...]:
    digest_tree(root)
    files: list[WorkspaceFileEvidence] = []
    for current, directory_names, file_names in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in (*directory_names, *file_names):
            candidate = current_path / name
            if is_link_like(candidate):
                raise TaskPackageError(
                    f"workspace links are not allowed: {candidate.relative_to(root).as_posix()}"
                )
        for name in file_names:
            path = current_path / name
            files.append(
                WorkspaceFileEvidence(
                    path=path.relative_to(root).as_posix(), digest=_sha256_file(path)
                )
            )
    return tuple(sorted(files, key=lambda item: item.path))


def changed_path_evidence(
    before: tuple[WorkspaceFileEvidence, ...], after: tuple[WorkspaceFileEvidence, ...]
) -> tuple[ChangedPathEvidence, ...]:
    before_map = {item.path: item.digest for item in before}
    after_map = {item.path: item.digest for item in after}
    changed: list[ChangedPathEvidence] = []
    for path in sorted(before_map.keys() | after_map.keys()):
        before_digest = before_map.get(path)
        after_digest = after_map.get(path)
        if before_digest == after_digest:
            continue
        if before_digest is None:
            status = ChangedPathStatus.ADDED
        elif after_digest is None:
            status = ChangedPathStatus.DELETED
        else:
            status = ChangedPathStatus.MODIFIED
        changed.append(
            ChangedPathEvidence(
                path=path,
                status=status,
                before_digest=before_digest,
                after_digest=after_digest,
            )
        )
    return tuple(changed)


class CodexHarnessRunner:
    def __init__(
        self,
        *,
        artifact_root: Path | None = None,
        runtime_root: Path | None = None,
        sandbox: DockerSandbox | None = None,
        adapter: CodexHarnessAdapter | None = None,
        plan_profile_identity: str | None = None,
        plan_harness_config_identity: str | None = None,
    ) -> None:
        base = Path(tempfile.gettempdir()) / "harnesslab-phase-e"
        self.artifact_root = (artifact_root or base / "artifacts").resolve()
        self.runtime_root = (runtime_root or base / "runtime").resolve()
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self.sandbox = sandbox or DockerSandbox()
        self.adapter = adapter or CodexHarnessAdapter()
        self.plan_profile_identity = plan_profile_identity
        self.plan_harness_config_identity = plan_harness_config_identity

    async def run(
        self,
        task_path: Path,
        profile: CodexHarnessProfile,
        *,
        backend: CodexBackend | None = None,
        transport: SubjectTransport[CodexHarnessProfile, CodexHarnessPrompt, CodexCollection]
        | None = None,
        run_id: str | None = None,
        prompt_addendum: str | None = None,
        execution_guard: Callable[[TaskPackage, CodexHarnessProfile, CodexHarnessPrompt, str], None]
        | None = None,
    ) -> HarnessLaneRunResult:
        if transport is not None and backend is not None:
            raise CodexHarnessRunError("select one subject transport")
        if transport is None:
            if backend is None:
                raise CodexHarnessRunError("a subject transport or CLI backend is required")
            transport = CodexCLITransport(self.adapter, backend)
        secret_values = transport.artifact_secret_values
        package = TaskPackage.load(task_path)
        if EvaluationLane.HARNESS not in package.definition.lane_support:
            raise CodexHarnessRunError("task package does not declare H-Lane support")
        effective_run_id = run_id or uuid4().hex
        if (
            not effective_run_id
            or len(effective_run_id) > 100
            or any(
                character not in "abcdefghijklmnopqrstuvwxyz0123456789-"
                for character in effective_run_id
            )
        ):
            raise CodexHarnessRunError(
                "run_id must use lowercase ASCII letters, digits, or hyphens"
            )
        run_root = Path(
            tempfile.mkdtemp(prefix=f"{effective_run_id}-", dir=self.runtime_root)
        ).resolve()
        materialized = None
        try:
            materialized = package.materialize(run_root)
            make_tree_writable(materialized.workspace)
            input_digest = digest_tree(materialized.workspace)
            input_inventory = workspace_inventory(materialized.workspace)
            context_digest = (
                make_tree_readable(materialized.context)
                if materialized.context is not None
                else None
            )
            prompt = render_codex_harness_prompt(
                task_instruction=package.definition.instruction,
                task_digest=package.definition.content_digest,
                workspace_input_digest=input_digest,
                context_digest=context_digest,
                network_policy=profile.tool_network_policy,
                prompt_addendum=prompt_addendum,
            )
            if execution_guard is not None:
                execution_guard(package, profile, prompt, effective_run_id)
            try:
                observation = await transport.execute(
                    SubjectRequest(
                        effective_run_id, package.definition.id, profile, prompt, effective_run_id
                    ),
                    SubjectWorkspace(
                        effective_run_id, materialized.workspace, materialized.context
                    ),
                )
                if observation.execution_id != effective_run_id:
                    raise HarnessAdapterError("subject returned another execution identity")
            except HarnessAdapterError as exc:
                raise CodexHarnessRunError(str(exc)) from exc
            collection = observation.collection
            if observation.backend_failure is not None:
                backend_failure = observation.backend_failure
                output_digest = digest_tree(materialized.workspace)
                output_inventory = workspace_inventory(materialized.workspace)
                changed_paths = changed_path_evidence(input_inventory, output_inventory)
                evidence = self._evidence(
                    effective_run_id,
                    package,
                    profile,
                    prompt_hash=prompt.prompt_hash,
                    prompt_template_version=prompt.template_version,
                    input_digest=input_digest,
                    output_digest=output_digest,
                    changed_paths=changed_paths,
                    context_digest=context_digest,
                    observation=observation,
                    collection=collection,
                    outcome=HarnessLaneOutcome.INFRA_ERROR,
                    summary=f"Codex backend execution failed during {backend_failure.phase.value}",
                    backend_failure=backend_failure,
                )
                return self._persist(evidence, collection, None, secret_values)
            output_digest = digest_tree(materialized.workspace)
            output_inventory = workspace_inventory(materialized.workspace)
            changed_paths = changed_path_evidence(input_inventory, output_inventory)
            artifact_failure = False
            try:
                assert_tree_has_no_run_secrets(materialized.workspace, secret_values)
            except ArtifactError:
                artifact_failure = True
            failure = (
                HarnessFailureCategory.ARTIFACT_ERROR
                if artifact_failure
                else collection.failure_category
            )
            if failure is not None:
                evidence = self._evidence(
                    effective_run_id,
                    package,
                    profile,
                    prompt_hash=prompt.prompt_hash,
                    prompt_template_version=prompt.template_version,
                    input_digest=input_digest,
                    output_digest=output_digest,
                    changed_paths=changed_paths,
                    context_digest=context_digest,
                    observation=observation,
                    collection=collection,
                    outcome=HarnessLaneOutcome.HARNESS_ERROR,
                    summary=f"Codex Harness attempt failed: {failure.value}",
                    harness_failure=failure,
                )
                return self._persist(
                    evidence,
                    collection,
                    None if artifact_failure else materialized.workspace,
                    secret_values,
                )
            try:
                verifier = await self.sandbox.run_hidden_verifier_workspace(
                    package,
                    materialized.workspace,
                    timeout_seconds=package.manifest.verifier.timeout_seconds,
                    secret_values=secret_values,
                )
                if verifier.run.manifest.workspace_input_digest != output_digest:
                    raise CodexHarnessRunError("verifier workspace identity mismatch")
                verifier_digest = digest_tree(verifier.run.artifact_directory)
            except Exception as exc:
                evidence = self._evidence(
                    effective_run_id,
                    package,
                    profile,
                    prompt_hash=prompt.prompt_hash,
                    prompt_template_version=prompt.template_version,
                    input_digest=input_digest,
                    output_digest=output_digest,
                    changed_paths=changed_paths,
                    context_digest=context_digest,
                    observation=observation,
                    collection=collection,
                    outcome=HarnessLaneOutcome.INFRA_ERROR,
                    summary=f"isolated Hidden Verifier failed: {type(exc).__name__}",
                )
                return self._persist(evidence, collection, materialized.workspace, secret_values)
            outcome = (
                HarnessLaneOutcome.VERIFIED_PASS
                if verifier.passed
                else HarnessLaneOutcome.VERIFIED_FAIL
            )
            evidence = self._evidence(
                effective_run_id,
                package,
                profile,
                prompt_hash=prompt.prompt_hash,
                prompt_template_version=prompt.template_version,
                input_digest=input_digest,
                output_digest=output_digest,
                changed_paths=changed_paths,
                context_digest=context_digest,
                observation=observation,
                collection=collection,
                outcome=outcome,
                summary=(
                    "isolated Hidden Verifier passed"
                    if verifier.passed
                    else "isolated Hidden Verifier rejected the final workspace"
                ),
                verifier_sandbox_manifest=verifier.run.manifest,
                verifier_artifact_digest=verifier_digest,
                verifier_passed=verifier.passed,
                verifier_score=verifier.score,
            )
            return self._persist(
                evidence,
                collection,
                materialized.workspace,
                secret_values,
                verifier_artifacts=verifier.run.artifact_directory,
            )
        finally:
            if materialized is not None:
                with suppress(OSError):
                    materialized.cleanup()
            shutil.rmtree(run_root, ignore_errors=True)

    def _evidence(
        self,
        run_id: str,
        package: TaskPackage,
        profile: CodexHarnessProfile,
        *,
        prompt_hash: str,
        prompt_template_version: str,
        input_digest: str,
        output_digest: str,
        changed_paths: tuple[ChangedPathEvidence, ...],
        context_digest: str | None,
        observation: SubjectObservation[CodexCollection],
        collection: CodexCollection,
        outcome: HarnessLaneOutcome,
        summary: str,
        harness_failure: HarnessFailureCategory | None = None,
        backend_failure: CodexBackendFailureEvidence | None = None,
        verifier_sandbox_manifest: SandboxArtifactManifest | None = None,
        verifier_artifact_digest: str | None = None,
        verifier_passed: bool | None = None,
        verifier_score: float | None = None,
    ) -> HarnessLaneEvidence:
        return HarnessLaneEvidence(
            run_id=run_id,
            task_id=package.definition.id,
            task_version=package.definition.version,
            task_digest=package.definition.content_digest,
            verifier_definition_digest=package.verifier_digest,
            resource_budget=package.definition.budget,
            workspace_input_digest=input_digest,
            workspace_output_digest=output_digest,
            changed_paths=changed_paths,
            context_digest=context_digest,
            plan_profile_identity=self.plan_profile_identity,
            plan_harness_config_identity=self.plan_harness_config_identity,
            prompt_template_version=prompt_template_version,
            prompt_hash=prompt_hash,
            profile=profile,
            profile_hash=profile.fingerprint,
            requested_model=profile.requested_model,
            observed_model=collection.observed_model,
            observed_model_status=collection.observed_model_status,
            provider_route=profile.provider_route,
            native_transcript_digest=collection.native_digest,
            normalized_trace_digest=collection.trace_digest,
            trace_event_count=len(collection.trace.events),
            trace_event_types=tuple(event.type for event in collection.trace.events),
            thread_id=collection.thread_id,
            terminal_native_event=collection.terminal_event,
            process_exit_code=observation.exit_code,
            duration_ms=observation.duration_ms,
            timed_out=observation.timed_out,
            cancelled=observation.cancelled,
            usage=collection.usage,
            harness_failure=harness_failure,
            backend_failure=backend_failure,
            verifier_sandbox_manifest=verifier_sandbox_manifest,
            verifier_artifact_namespace=(
                "verifier" if verifier_sandbox_manifest is not None else None
            ),
            verifier_artifact_digest=verifier_artifact_digest,
            verifier_passed=verifier_passed,
            verifier_score=verifier_score,
            outcome=outcome,
            summary=summary,
        )

    def _persist(
        self,
        evidence: HarnessLaneEvidence,
        collection: CodexCollection,
        workspace: Path | None,
        secret_values: tuple[str, ...],
        *,
        verifier_artifacts: Path | None = None,
    ) -> HarnessLaneRunResult:
        destination = self.artifact_root / evidence.run_id
        if destination.exists():
            raise CodexHarnessRunError("Harness artifact run_id already exists")
        staging = self.artifact_root / f".{evidence.run_id}-{uuid4().hex}.tmp"
        staging.mkdir()
        try:
            native = staging / "native"
            trace = staging / "trace"
            native.mkdir()
            trace.mkdir()
            (native / "codex.sanitized.jsonl").write_text(
                collection.sanitized_jsonl, encoding="utf-8"
            )
            (trace / "normalized.json").write_text(
                collection.trace.canonical_json(), encoding="utf-8"
            )
            if workspace is not None:
                assert_tree_has_no_run_secrets(workspace, secret_values)
                copied = copy_workspace_snapshot(workspace, staging / "workspace")
                if copied != evidence.workspace_output_digest:
                    raise CodexHarnessRunError("workspace artifact identity mismatch")
            if verifier_artifacts is not None:
                assert_tree_has_no_run_secrets(verifier_artifacts, secret_values)
                shutil.copytree(verifier_artifacts, staging / "verifier")
                if digest_tree(staging / "verifier") != evidence.verifier_artifact_digest:
                    raise CodexHarnessRunError("verifier artifact identity mismatch")
            (staging / "manifest.json").write_text(evidence.canonical_json(), encoding="utf-8")
            assert_tree_has_no_run_secrets(staging, secret_values)
            staging.replace(destination)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return HarnessLaneRunResult(artifact_directory=destination, evidence=evidence)
