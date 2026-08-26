from __future__ import annotations

import os
import shutil
import tempfile
import warnings
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

from harnesslab.contracts.common import EvaluationLane, Protocol
from harnesslab.contracts.model import ModelProfile
from harnesslab.model_lane.models import (
    DirectModelEvidence,
    DirectModelOutcome,
    DirectModelRunResult,
    GenerationSettings,
    ProviderAdapter,
    ProviderError,
    ProviderFailureCategory,
    ProviderInvocationError,
    ProviderRequest,
    ProviderResult,
)
from harnesslab.model_lane.patch import (
    DirectPatchError,
    DirectPatchInfrastructureError,
    apply_direct_patch,
    copy_workspace_snapshot,
    parse_direct_patch,
)
from harnesslab.model_lane.prompt import (
    DirectPrompt,
    PromptContractError,
    assert_prompt_matches_task_identity,
    render_direct_prompt,
)
from harnesslab.model_lane.providers import adapter_for_profile
from harnesslab.sandbox.artifacts import assert_tree_has_no_run_secrets
from harnesslab.sandbox.models import SandboxArtifactManifest
from harnesslab.sandbox.runner import DockerSandbox
from harnesslab.tasks.package import TaskPackage, digest_tree, sha256_bytes


class DirectModelRunError(RuntimeError):
    """Trusted runner infrastructure could not preserve Phase D evidence."""


def _report_cleanup_failure(message: str) -> None:
    with suppress(Exception):
        warnings.warn(message, RuntimeWarning, stacklevel=3)


def _assert_text_has_no_run_secrets(text: str, secret_values: tuple[str, ...]) -> None:
    if any(value and value in text for value in secret_values):
        raise DirectModelRunError("exact run secret detected before external or artifact write")


class DirectModelRunner:
    def __init__(
        self,
        *,
        artifact_root: Path | None = None,
        runtime_root: Path | None = None,
        sandbox: DockerSandbox | None = None,
        environment: Mapping[str, str] | None = None,
        allow_custom_endpoint: bool = False,
    ) -> None:
        base = Path(tempfile.gettempdir()) / "harnesslab-phase-d"
        self.artifact_root = (artifact_root or base / "artifacts").resolve()
        self.runtime_root = (runtime_root or base / "runtime").resolve()
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self.sandbox = sandbox or DockerSandbox()
        self.environment = environment if environment is not None else os.environ
        self.allow_custom_endpoint = allow_custom_endpoint

    async def run(
        self,
        task_path: Path,
        profile: ModelProfile,
        *,
        adapter: ProviderAdapter | None = None,
        run_id: str | None = None,
    ) -> DirectModelRunResult:
        package = TaskPackage.load(task_path)
        if EvaluationLane.MODEL not in package.definition.lane_support:
            raise DirectModelRunError("task package does not declare M-Lane support")
        effective_run_id = run_id or uuid4().hex
        if (
            not effective_run_id
            or len(effective_run_id) > 100
            or any(
                character not in "abcdefghijklmnopqrstuvwxyz0123456789-"
                for character in effective_run_id
            )
        ):
            raise DirectModelRunError("run_id must use lowercase ASCII letters, digits, or hyphens")
        run_root = Path(
            tempfile.mkdtemp(prefix=f"{effective_run_id}-", dir=self.runtime_root)
        ).resolve()
        run_environment = dict(self.environment)
        materialized = None
        try:
            materialized = package.materialize(run_root)
            try:
                prompt = render_direct_prompt(
                    task_instruction=package.definition.instruction,
                    workspace=materialized.workspace,
                    context=materialized.context,
                )
            except PromptContractError as exc:
                raise DirectModelRunError(f"direct prompt cannot be rendered: {exc}") from exc
            request = ProviderRequest(
                profile=profile,
                instructions=prompt.instructions,
                input=prompt.input,
            )
            credential_values = self._credential_values(profile, run_environment)
            _assert_text_has_no_run_secrets(prompt.instructions, credential_values)
            _assert_text_has_no_run_secrets(prompt.input, credential_values)
            try:
                official_route = (
                    profile.protocol is Protocol.RESPONSES
                    and profile.base_url == "https://api.openai.com/v1"
                    and profile.route == "/responses"
                ) or (
                    profile.protocol is Protocol.MESSAGES
                    and profile.base_url == "https://api.anthropic.com"
                    and profile.route == "/v1/messages"
                )
                if adapter is None and not official_route and not self.allow_custom_endpoint:
                    raise ProviderInvocationError(
                        ProviderFailureCategory.CONFIGURATION,
                        "custom provider endpoint requires explicit operator authorization",
                    )
                selected_adapter = adapter or adapter_for_profile(
                    request, environment=run_environment
                )
                provider_result = await selected_adapter.invoke(request)
            except ProviderInvocationError as exc:
                evidence = self._base_evidence(
                    effective_run_id,
                    package,
                    profile,
                    prompt,
                    outcome=DirectModelOutcome.PROVIDER_ERROR,
                    summary=f"provider invocation failed: {exc.category.value}",
                    provider_failure=exc.category,
                    provider_error=ProviderError(
                        category=exc.category,
                        timeout_phase=exc.timeout_phase,
                        status_code=exc.status_code,
                        request_id=exc.request_id,
                        response_status=exc.response_status,
                        latency_ms=exc.latency_ms,
                    ),
                )
                return self._persist(evidence, None, credential_values)

            public_digest = sha256_bytes(provider_result.public_output_text.encode("utf-8"))
            _assert_text_has_no_run_secrets(provider_result.public_output_text, credential_values)
            if provider_result.refused:
                evidence = self._base_evidence(
                    effective_run_id,
                    package,
                    profile,
                    prompt,
                    outcome=DirectModelOutcome.SUBJECT_REFUSAL,
                    summary="model declined the task",
                    provider_result=provider_result,
                    public_response_digest=public_digest,
                    public_response_text=provider_result.public_output_text,
                )
                return self._persist(evidence, None, credential_values)
            try:
                assert_prompt_matches_task_identity(prompt, materialized.workspace)
                patch = parse_direct_patch(provider_result.public_output_text)
                patch_digest = sha256_bytes(patch.canonical_json().encode("utf-8"))
                output_digest = apply_direct_patch(
                    materialized.workspace,
                    patch,
                    protected_digests=materialized.protected_digests,
                    expected_input_digest=prompt.workspace_digest,
                )
            except (PromptContractError, DirectPatchInfrastructureError) as exc:
                evidence = self._base_evidence(
                    effective_run_id,
                    package,
                    profile,
                    prompt,
                    outcome=DirectModelOutcome.INFRA_ERROR,
                    summary=f"workspace patch infrastructure failed: {type(exc).__name__}",
                    provider_result=provider_result,
                    public_response_digest=public_digest,
                    public_response_text=provider_result.public_output_text,
                )
                return self._persist(evidence, None, credential_values)
            except DirectPatchError:
                output_budget_exhausted = provider_result.stop_reason in {"max_tokens", "length"}
                evidence = self._base_evidence(
                    effective_run_id,
                    package,
                    profile,
                    prompt,
                    outcome=DirectModelOutcome.SUBJECT_OUTPUT_ERROR,
                    summary=(
                        "public model output exhausted the output-token budget "
                        "and violated direct-patch-v1"
                        if output_budget_exhausted
                        else "public model output violated direct-patch-v1"
                    ),
                    provider_result=provider_result,
                    public_response_digest=public_digest,
                    public_response_text=provider_result.public_output_text,
                )
                return self._persist(evidence, None, credential_values)

            try:
                assert_tree_has_no_run_secrets(materialized.workspace, credential_values)
                verifier = await self.sandbox.run_hidden_verifier_workspace(
                    package,
                    materialized.workspace,
                    timeout_seconds=package.manifest.verifier.timeout_seconds,
                    secret_values=credential_values,
                )
                if verifier.run.manifest.workspace_input_digest != output_digest:
                    raise RuntimeError("verifier workspace identity mismatch")
                verifier_artifact_digest = digest_tree(verifier.run.artifact_directory)
            except Exception as exc:
                evidence = self._base_evidence(
                    effective_run_id,
                    package,
                    profile,
                    prompt,
                    outcome=DirectModelOutcome.INFRA_ERROR,
                    summary=f"isolated verification failed: {type(exc).__name__}",
                    workspace_output_digest=output_digest,
                    provider_result=provider_result,
                    public_response_digest=public_digest,
                    public_response_text=provider_result.public_output_text,
                    parsed_patch_digest=patch_digest,
                )
                return self._persist(evidence, None, credential_values)

            outcome = (
                DirectModelOutcome.VERIFIED_PASS
                if verifier.passed
                else DirectModelOutcome.VERIFIED_FAIL
            )
            evidence = self._base_evidence(
                effective_run_id,
                package,
                profile,
                prompt,
                outcome=outcome,
                summary=(
                    "isolated verifier passed" if verifier.passed else "isolated verifier failed"
                ),
                workspace_output_digest=output_digest,
                provider_result=provider_result,
                public_response_digest=public_digest,
                public_response_text=provider_result.public_output_text,
                parsed_patch_digest=patch_digest,
                verifier_sandbox_manifest=verifier.run.manifest,
                verifier_artifact_namespace="verifier",
                verifier_artifact_digest=verifier_artifact_digest,
                verifier_passed=verifier.passed,
                verifier_score=verifier.score,
            )
            return self._persist(
                evidence,
                materialized.workspace,
                credential_values,
                verifier_artifacts=verifier.run.artifact_directory,
            )
        finally:
            if materialized is not None:
                try:
                    materialized.cleanup()
                except OSError as exc:
                    _report_cleanup_failure(
                        f"materialized workspace cleanup failed: {type(exc).__name__}"
                    )
            try:
                if run_root.exists():
                    shutil.rmtree(run_root)
            except OSError as exc:
                _report_cleanup_failure(f"Phase D runtime cleanup failed: {type(exc).__name__}")

    def _credential_values(
        self, profile: ModelProfile, environment: Mapping[str, str]
    ) -> tuple[str, ...]:
        reference = profile.credential_reference
        if reference is None:
            return ()
        value = environment.get(reference)
        return (value,) if value else ()

    def _base_evidence(
        self,
        run_id: str,
        package: TaskPackage,
        profile: ModelProfile,
        prompt: DirectPrompt,
        *,
        outcome: DirectModelOutcome,
        summary: str,
        workspace_output_digest: str | None = None,
        provider_result: ProviderResult | None = None,
        provider_failure: ProviderFailureCategory | None = None,
        provider_error: ProviderError | None = None,
        public_response_digest: str | None = None,
        public_response_text: str | None = None,
        parsed_patch_digest: str | None = None,
        verifier_sandbox_manifest: SandboxArtifactManifest | None = None,
        verifier_artifact_namespace: str | None = None,
        verifier_artifact_digest: str | None = None,
        verifier_passed: bool | None = None,
        verifier_score: float | None = None,
    ) -> DirectModelEvidence:
        return DirectModelEvidence(
            run_id=run_id,
            task_id=package.definition.id,
            task_version=package.definition.version,
            task_digest=package.definition.content_digest,
            verifier_definition_digest=package.verifier_digest,
            resource_budget=package.definition.budget,
            workspace_input_digest=prompt.workspace_digest,
            workspace_output_digest=workspace_output_digest,
            context_digest=prompt.context_digest,
            prompt_template_version=prompt.template_version,
            prompt_hash=prompt.prompt_hash,
            requested_model=profile.requested_model,
            observed_model=(
                provider_result.observed_model if provider_result is not None else None
            ),
            provider=profile.provider,
            endpoint=f"{profile.base_url}{profile.route}",
            protocol=profile.protocol,
            generation_settings=GenerationSettings(
                effort=profile.reasoning.effort,
                temperature=profile.reasoning.temperature,
                max_output_tokens=profile.reasoning.max_output_tokens,
                request_timeout_seconds=profile.request_timeout_seconds,
            ),
            provider_result=provider_result,
            provider_failure=provider_failure,
            provider_error=provider_error,
            public_response_digest=public_response_digest,
            public_response_text=public_response_text,
            parsed_patch_digest=parsed_patch_digest,
            verifier_sandbox_manifest=verifier_sandbox_manifest,
            verifier_artifact_namespace=verifier_artifact_namespace,
            verifier_artifact_digest=verifier_artifact_digest,
            verifier_passed=verifier_passed,
            verifier_score=verifier_score,
            outcome=outcome,
            summary=summary,
        )

    def _persist(
        self,
        evidence: DirectModelEvidence,
        workspace: Path | None,
        secret_values: tuple[str, ...],
        *,
        verifier_artifacts: Path | None = None,
    ) -> DirectModelRunResult:
        destination = self.artifact_root / evidence.run_id
        if destination.exists():
            raise DirectModelRunError("direct-model artifact run_id already exists")
        staging = self.artifact_root / f".{evidence.run_id}-{uuid4().hex}.tmp"
        manifest_text = evidence.canonical_json()
        _assert_text_has_no_run_secrets(manifest_text, secret_values)
        if workspace is not None:
            assert_tree_has_no_run_secrets(workspace, secret_values)
        if verifier_artifacts is not None:
            assert_tree_has_no_run_secrets(verifier_artifacts, secret_values)
        staging.mkdir()
        try:
            (staging / "manifest.json").write_text(manifest_text, encoding="utf-8")
            if workspace is not None:
                copied_digest = copy_workspace_snapshot(workspace, staging / "workspace")
                if copied_digest != evidence.workspace_output_digest:
                    raise DirectModelRunError("evidence workspace digest mismatch")
            if verifier_artifacts is not None:
                copied_verifier_digest = copy_workspace_snapshot(
                    verifier_artifacts, staging / "verifier"
                )
                if copied_verifier_digest != evidence.verifier_artifact_digest:
                    raise DirectModelRunError("verifier artifact digest mismatch")
            assert_tree_has_no_run_secrets(staging, secret_values)
            staging.replace(destination)
        except Exception as exc:
            if staging.exists():
                shutil.rmtree(staging)
            if isinstance(exc, DirectModelRunError):
                raise
            raise DirectModelRunError(
                f"direct-model evidence collection failed: {type(exc).__name__}"
            ) from exc
        return DirectModelRunResult(artifact_directory=destination, evidence=evidence)
