from __future__ import annotations

import shutil
import tempfile
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

from harnesslab.contracts.common import EvaluationLane
from harnesslab.harness_lane.adapter import HarnessAdapterError
from harnesslab.harness_lane.models import (
    ChangedPathEvidence,
    HarnessFailureCategory,
    HarnessLaneOutcome,
)
from harnesslab.harness_lane.runner import changed_path_evidence, workspace_inventory
from harnesslab.model_lane.patch import copy_workspace_snapshot
from harnesslab.multi_harness.adapter import MultiHarnessAdapter, MultiHarnessBackend
from harnesslab.multi_harness.models import (
    HarnessProcessCapture,
    MultiHarnessCollection,
    MultiHarnessEvidence,
    MultiHarnessProfile,
    MultiHarnessRunResult,
)
from harnesslab.multi_harness.prompt import render_harness_prompt
from harnesslab.sandbox.artifacts import (
    ArtifactError,
    assert_tree_has_no_run_secrets,
    make_tree_readable,
    make_tree_writable,
)
from harnesslab.sandbox.models import SandboxArtifactManifest
from harnesslab.sandbox.runner import DockerSandbox
from harnesslab.tasks.package import TaskPackage, digest_tree


class MultiHarnessRunError(RuntimeError):
    """Trusted Phase F orchestration could not preserve its evidence contract."""


class MultiHarnessRunner:
    """One shared fresh-workspace / hidden-verifier runner for both Phase F adapters."""

    def __init__(
        self,
        *,
        artifact_root: Path | None = None,
        runtime_root: Path | None = None,
        sandbox: DockerSandbox | None = None,
    ) -> None:
        base = Path(tempfile.gettempdir()) / "harnesslab-phase-f"
        self.artifact_root = (artifact_root or base / "artifacts").resolve()
        self.runtime_root = (runtime_root or base / "runtime").resolve()
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self.sandbox = sandbox or DockerSandbox()

    async def run(
        self,
        task_path: Path,
        profile: MultiHarnessProfile,
        *,
        adapter: MultiHarnessAdapter,
        backend: MultiHarnessBackend,
        run_id: str | None = None,
    ) -> MultiHarnessRunResult:
        package = TaskPackage.load(task_path)
        if EvaluationLane.HARNESS not in package.definition.lane_support:
            raise MultiHarnessRunError("task package does not declare H-Lane support")
        effective_run_id = run_id or uuid4().hex
        if (
            not effective_run_id
            or len(effective_run_id) > 100
            or any(
                character not in "abcdefghijklmnopqrstuvwxyz0123456789-"
                for character in effective_run_id
            )
        ):
            raise MultiHarnessRunError(
                "run_id must use lowercase ASCII letters, digits, or hyphens"
            )
        run_root = Path(tempfile.mkdtemp(prefix=f"{effective_run_id}-", dir=self.runtime_root))
        materialized = None
        secrets = backend.artifact_secret_values
        try:
            materialized = package.materialize(run_root)
            make_tree_writable(materialized.workspace)
            input_digest = digest_tree(materialized.workspace)
            before = workspace_inventory(materialized.workspace)
            context_digest = (
                make_tree_readable(materialized.context) if materialized.context else None
            )
            prompt = render_harness_prompt(
                profile.harness,
                task_instruction=package.definition.instruction,
                task_digest=package.definition.content_digest,
                workspace_input_digest=input_digest,
                context_digest=context_digest,
                network_policy=profile.network_policy,
            )
            if prompt.template_version != profile.prompt_template_version:
                raise MultiHarnessRunError("prompt template does not match profile")
            try:
                adapter.preflight(profile)
                plan = adapter.prepare(
                    profile,
                    prompt,
                    workspace=materialized.workspace,
                    context=materialized.context,
                    task_id=package.definition.id,
                )
                capture = await backend.run(plan)
                collection = adapter.collect(capture, secret_values=secrets)
            except HarnessAdapterError as exc:
                raise MultiHarnessRunError(str(exc)) from exc
            output_digest = digest_tree(materialized.workspace)
            changed = changed_path_evidence(before, workspace_inventory(materialized.workspace))
            artifact_failure = False
            try:
                assert_tree_has_no_run_secrets(materialized.workspace, secrets)
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
                    prompt.prompt_hash,
                    input_digest,
                    output_digest,
                    changed,
                    context_digest,
                    capture,
                    collection,
                    HarnessLaneOutcome.HARNESS_ERROR,
                    f"{profile.harness.value} attempt failed: {failure.value}",
                    harness_failure=failure,
                )
                return self._persist(
                    evidence,
                    collection,
                    None if artifact_failure else materialized.workspace,
                    secrets,
                )
            try:
                verifier = await self.sandbox.run_hidden_verifier_workspace(
                    package,
                    materialized.workspace,
                    timeout_seconds=package.manifest.verifier.timeout_seconds,
                    secret_values=secrets,
                )
                if verifier.run.manifest.workspace_input_digest != output_digest:
                    raise MultiHarnessRunError("verifier workspace identity mismatch")
                verifier_digest = digest_tree(verifier.run.artifact_directory)
            except Exception as exc:
                evidence = self._evidence(
                    effective_run_id,
                    package,
                    profile,
                    prompt.prompt_hash,
                    input_digest,
                    output_digest,
                    changed,
                    context_digest,
                    capture,
                    collection,
                    HarnessLaneOutcome.INFRA_ERROR,
                    f"isolated Hidden Verifier failed: {type(exc).__name__}",
                )
                return self._persist(evidence, collection, materialized.workspace, secrets)
            outcome = (
                HarnessLaneOutcome.VERIFIED_PASS
                if verifier.passed
                else HarnessLaneOutcome.VERIFIED_FAIL
            )
            evidence = self._evidence(
                effective_run_id,
                package,
                profile,
                prompt.prompt_hash,
                input_digest,
                output_digest,
                changed,
                context_digest,
                capture,
                collection,
                outcome,
                "isolated Hidden Verifier passed"
                if verifier.passed
                else "isolated Hidden Verifier rejected the final workspace",
                verifier_sandbox_manifest=verifier.run.manifest,
                verifier_artifact_digest=verifier_digest,
                verifier_passed=verifier.passed,
                verifier_score=verifier.score,
            )
            return self._persist(
                evidence,
                collection,
                materialized.workspace,
                secrets,
                verifier_artifacts=verifier.run.artifact_directory,
            )
        finally:
            if materialized is not None:
                with suppress(OSError):
                    materialized.cleanup()
            shutil.rmtree(run_root, ignore_errors=True)

    @staticmethod
    def _evidence(
        run_id: str,
        package: TaskPackage,
        profile: MultiHarnessProfile,
        prompt_hash: str,
        input_digest: str,
        output_digest: str,
        changed_paths: tuple[ChangedPathEvidence, ...],
        context_digest: str | None,
        capture: HarnessProcessCapture,
        collection: MultiHarnessCollection,
        outcome: HarnessLaneOutcome,
        summary: str,
        *,
        harness_failure: HarnessFailureCategory | None = None,
        verifier_sandbox_manifest: SandboxArtifactManifest | None = None,
        verifier_artifact_digest: str | None = None,
        verifier_passed: bool | None = None,
        verifier_score: float | None = None,
    ) -> MultiHarnessEvidence:
        return MultiHarnessEvidence(
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
            prompt_template_version=profile.prompt_template_version,
            prompt_hash=prompt_hash,
            harness=profile.harness,
            profile=profile,
            profile_hash=profile.fingerprint,
            requested_model=profile.requested_model,
            observed_model=collection.observed_model,
            observed_model_status=collection.observed_model_status,
            provider_route=profile.provider_route,
            native_transcript_digest=collection.native_digest,
            normalized_trace_digest=collection.trace_digest,
            trace_coverage=profile.trace_coverage,
            trace_event_count=len(collection.trace.events),
            trace_event_types=tuple(event.type for event in collection.trace.events),
            terminal_native_event=collection.terminal_event,
            process_exit_code=capture.exit_code,
            duration_ms=capture.duration_ms,
            timed_out=capture.timed_out,
            cancelled=capture.cancelled,
            retry_count=collection.retry_count,
            usage=collection.usage,
            harness_failure=harness_failure,
            verifier_sandbox_manifest=verifier_sandbox_manifest,
            verifier_artifact_namespace="verifier" if verifier_sandbox_manifest else None,
            verifier_artifact_digest=verifier_artifact_digest,
            verifier_passed=verifier_passed,
            verifier_score=verifier_score,
            outcome=outcome,
            summary=summary,
        )

    def _persist(
        self,
        evidence: MultiHarnessEvidence,
        collection: MultiHarnessCollection,
        workspace: Path | None,
        secrets: tuple[str, ...],
        *,
        verifier_artifacts: Path | None = None,
    ) -> MultiHarnessRunResult:
        destination = self.artifact_root / evidence.run_id
        if destination.exists():
            raise MultiHarnessRunError("Harness artifact run_id already exists")
        staging = self.artifact_root / f".{evidence.run_id}-{uuid4().hex}.tmp"
        staging.mkdir()
        try:
            (staging / "native").mkdir()
            (staging / "trace").mkdir()
            native_name = f"{evidence.harness.value}.sanitized.jsonl"
            (staging / "native" / native_name).write_text(
                collection.sanitized_jsonl, encoding="utf-8"
            )
            (staging / "trace" / "normalized.json").write_text(
                collection.trace.canonical_json(), encoding="utf-8"
            )
            if workspace is not None:
                assert_tree_has_no_run_secrets(workspace, secrets)
                if (
                    copy_workspace_snapshot(workspace, staging / "workspace")
                    != evidence.workspace_output_digest
                ):
                    raise MultiHarnessRunError("workspace artifact identity mismatch")
            if verifier_artifacts is not None:
                assert_tree_has_no_run_secrets(verifier_artifacts, secrets)
                shutil.copytree(verifier_artifacts, staging / "verifier")
                if digest_tree(staging / "verifier") != evidence.verifier_artifact_digest:
                    raise MultiHarnessRunError("verifier artifact identity mismatch")
            (staging / "manifest.json").write_text(evidence.canonical_json(), encoding="utf-8")
            assert_tree_has_no_run_secrets(staging, secrets)
            staging.replace(destination)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return MultiHarnessRunResult(artifact_directory=destination, evidence=evidence)
