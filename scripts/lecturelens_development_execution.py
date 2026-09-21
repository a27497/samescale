"""Single-attempt L1 entry with mandatory authorization.

Run with ``python -m scripts.lecturelens_development_execution --help``.
Historical execute_once artifacts are records, not reusable launchers. No authorization
is inferred or generated here; the operator supplies a fresh, bounded receipt.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from harnesslab.contracts.provider import validate_provider_base_url
from harnesslab.custom_eval.models import canonical_digest
from harnesslab.egress import boundary_for_provider_url
from harnesslab.harness_lane.adapter import CodexExecutionPlan, CodexHarnessAdapter
from harnesslab.harness_lane.docker_backend import DockerCodexBackend
from harnesslab.harness_lane.models import CodexHarnessProfile, HarnessLaneRunResult
from harnesslab.harness_lane.prompt import CodexHarnessPrompt, render_codex_harness_prompt
from harnesslab.harness_lane.runner import CodexHarnessRunner
from harnesslab.registry.vault import CredentialVault
from harnesslab.sandbox.docker_cli import _DockerCLI
from harnesslab.sandbox.models import ImageIdentity
from harnesslab.sandbox.preflight import _docker_runtime_preflight
from harnesslab.sandbox.runner import SANDBOX_IMAGE, DockerSandbox
from harnesslab.tasks.package import TaskPackage
from harnesslab.tasks.quality import TaskIdentity

TOKEN_LIMITATION_REQUIRED = "REQUIRED"
TOKEN_LIMITATION_ACCEPTED = "ACCEPTED_NO_SESSION_TOKEN_HARD_CAP"


# Pinned execution primitives only; task intake/freeze preparation is not a runtime dependency.
IMAGE_ID = "sha256:88c5544438f5942f7b3d17263816ac01f1479fb8d0ae7e9dd640fbe8ef51f11b"


RESOURCES = {"memory": "2g", "cpus": "2", "pids": "256", "tmpfs": "768m"}

RETRY_OVERRIDES = (
    "-c",
    "model_providers.harnesslab_responses_relay.request_max_retries=0",
    "-c",
    "model_providers.harnesslab_responses_relay.stream_max_retries=0",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


class DevelopmentAdapter(CodexHarnessAdapter):
    def __init__(self, profile_identity: str) -> None:
        self.profile_identity = profile_identity

    def preflight(self, profile: CodexHarnessProfile) -> None:
        require(profile.fingerprint == self.profile_identity, "Development profile changed")
        require(
            profile.codex_image.image_id == IMAGE_ID and profile.codex_cli_version == "0.153.4",
            "Unqualified development image/version",
        )
        # The base adapter requires its stock tag. This narrowly pinned derivative
        # retains all other checks; the actual plan/evidence keeps the derivative ID.
        raw = profile.model_dump(mode="json")
        raw["codex_image"]["reference"] = "harnesslab-codex:0.153.4"
        super().preflight(CodexHarnessProfile.model_validate(raw))

    def prepare(
        self,
        profile: CodexHarnessProfile,
        prompt: CodexHarnessPrompt,
        *,
        workspace: Path,
        context: Path | None,
        task_id: str,
    ) -> CodexExecutionPlan:
        require(profile.fingerprint == self.profile_identity, "Development profile changed")
        self.preflight(profile)
        plan = super().prepare(
            profile, prompt, workspace=workspace, context=context, task_id=task_id
        )
        return replace(plan, argv=(*plan.argv[:-1], *RETRY_OVERRIDES, "-"))


class DevelopmentBackend(DockerCodexBackend):
    """Existing Codex backend with the declared task dependency resource envelope."""

    def create_argv(self, plan: CodexExecutionPlan, container_name: str) -> tuple[str, ...]:
        require(plan.image_reference == IMAGE_ID, "Development image changed")
        args = list(super().create_argv(plan, container_name))
        args[args.index("--memory") + 1] = RESOURCES["memory"]
        args[args.index("--tmpfs") + 1] = "/tmp:rw,nosuid,nodev,size=768m"
        return tuple(args)


class DevelopmentSandbox(DockerSandbox):
    async def _prepare_image(self) -> tuple[ImageIdentity, dict[str, str]]:
        _, environment = await _docker_runtime_preflight()
        result = await _DockerCLI(environment=environment).run(
            "image", "inspect", IMAGE_ID, "--format", "{{.Id}}"
        )
        require(result.stdout.decode().strip() == IMAGE_ID, "Offline image unavailable")
        return ImageIdentity(reference=IMAGE_ID, image_id=IMAGE_ID), environment

    def _create_arguments(self, **kwargs: Any) -> tuple[str, ...]:
        require(not kwargs["secret_names"], "Verifier must not receive credentials")
        args = list(super()._create_arguments(**kwargs))
        for flag, value in (
            ("--memory", RESOURCES["memory"]),
            ("--cpus", RESOURCES["cpus"]),
            ("--pids-limit", RESOURCES["pids"]),
            ("--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=768m"),
        ):
            args[args.index(flag) + 1] = value
        index = args.index(SANDBOX_IMAGE)
        args[index : index + 1] = ["--entrypoint", "python3", IMAGE_ID]
        return tuple(args)


def validate_execution_budget_contract(
    request: dict[str, Any], authorization: dict[str, Any]
) -> None:
    """Fail closed when the declared output budget is not a real session cap.

    The current Codex/Harness path observes output usage after completion; it does not
    establish a cumulative session hard cap. A real run must therefore bind the same
    declared budget and record fresh, explicit acceptance of that limitation.
    """
    declared = request.get("declared_output_tokens")
    if not isinstance(declared, int) or isinstance(declared, bool) or declared <= 0:
        raise ValueError("Execution request requires a positive declared output budget")
    if request.get("session_output_token_cap_enforced") is not False:
        raise ValueError("Execution request misstates session output-cap enforcement")
    if request.get("token_limitation_acceptance") != TOKEN_LIMITATION_REQUIRED:
        raise ValueError("Execution request token limitation contract changed")
    if authorization.get("execution_authorized") is not True:
        raise ValueError("Fresh execution authorization is required")
    if authorization.get("session_output_token_cap_enforced") is not False:
        raise ValueError("Authorization misstates session output-cap enforcement")
    if authorization.get("token_limitation_acceptance") != TOKEN_LIMITATION_ACCEPTED:
        raise ValueError("No-session-hard-cap limitation was not explicitly accepted")
    if (
        type(authorization.get("declared_output_tokens")) is not int
        or authorization["declared_output_tokens"] != declared
    ):
        raise ValueError("Authorization output budget does not match the execution request")


def _check_identity(document: dict[str, Any], field: str) -> None:
    require(
        document.get(field) == canonical_digest({k: v for k, v in document.items() if k != field}),
        f"{field} content mismatch",
    )


def _consume_authorization(vault: CredentialVault, authorization: dict[str, Any]) -> None:
    # Fixed to the operator's credential store, independent of output directory.
    # Exclusive, durable claims survive failure/restart; never remove or reset them.
    require(vault.root is not None, "A persistent operator vault is required")
    assert vault.root is not None
    root = vault.root / "l1-consumed-authorizations"
    root.mkdir(mode=0o700, exist_ok=True)
    require(root.resolve() == root, "Authorization state must not be redirected")
    for field in ("authorization_id", "execution_id"):
        path = root / f"{field}-{authorization[field]}"
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            raise ValueError("Authorization or execution already consumed") from None
        with os.fdopen(fd, "w") as stream:
            stream.write(canonical_digest(authorization) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


async def run_development_attempt(
    *,
    request: dict[str, Any],
    plan: dict[str, Any],
    authorization: dict[str, Any] | None,
    execution_id: str,
    slot: str,
    task_path: Path,
    prompt_addendum: str | None,
    vault: CredentialVault,
    output: Path,
) -> HarnessLaneRunResult:
    """Authorize exactly one L1 attempt before credentials, egress, or run creation.

    Receipts are trusted local operator inputs, not remotely authenticated approvals.
    Their issued_at/expires_at window is at most one hour. Each receipt and execution
    is consumed once in the persistent vault, even if downstream preparation fails.
    No retry, resume, Judge, or automatic transition to another slot is available.
    """
    authorization = authorization or {}
    validate_execution_budget_contract(request, authorization)
    now = datetime.now(UTC)
    try:
        issued = datetime.fromisoformat(authorization["issued_at"])
        expires = datetime.fromisoformat(authorization["expires_at"])
        fresh = issued <= now < expires and expires - issued <= timedelta(hours=1)
    except (KeyError, TypeError, ValueError):
        fresh = False
    require(fresh, "Fresh, unexpired execution authorization is required")
    for field in ("authorization_id", "execution_id"):
        require(
            isinstance(authorization.get(field), str)
            and re.fullmatch(r"[a-f0-9]{32}", authorization[field]) is not None,
            "Authorization requires unique authorization/execution IDs",
        )
    require(authorization.get("consumed") is False, "Authorization already consumed or unknown")
    require(
        authorization["execution_id"] == request.get("execution_id") == execution_id
        and authorization.get("slot") == request.get("slot") == slot,
        "Authorization belongs to another execution or slot",
    )
    _check_identity(request, "request_identity")
    _check_identity(plan, "plan_identity")
    profile = CodexHarnessProfile.model_validate(plan["profile"])
    for field, actual in (
        ("request_identity", request["request_identity"]),
        ("plan_identity", plan["plan_identity"]),
        ("profile_identity", profile.fingerprint),
    ):
        require(
            request.get(field) == authorization.get(field) == actual,
            f"Authorization {field} binding mismatch",
        )
    require(plan["profile_identity"] == profile.fingerprint, "Plan profile mismatch")
    require(
        request.get("image_id") == profile.codex_image.image_id
        and request.get("requested_model") == profile.requested_model
        and request.get("reasoning_effort") == profile.reasoning_effort
        and request.get("codex_cli_version") == profile.codex_cli_version
        and request.get("candidate_freeze_identity") == plan["candidate_freeze_identity"]
        and plan.get("session_output_token_cap_enforced") is False,
        "Request/plan runtime binding mismatch",
    )
    require(
        request.get("run_order") == [slot]
        and slot in plan["run_order"]
        and request.get("top_level_attempts") == authorization.get("top_level_attempts") == 1
        and request.get("automatic_retry") is False
        and request.get("automatic_resume") is False
        and request.get("request_max_retries") == request.get("stream_max_retries") == 0
        and authorization.get("judge_authorized") is False
        and request.get("judge_calls") == 0,
        "Only one no-retry, no-resume, no-Judge attempt is authorized",
    )
    label, variant, attempt = slot.split("/")
    require(attempt == "1", "Replacement attempts require a new execution")
    package = TaskPackage.load(task_path)
    expected_task = plan["tasks"][label]
    require(
        all(
            expected_task.get(k) == v
            for k, v in TaskIdentity.from_package(package).model_dump(mode="json").items()
        )
        and expected_task["oracle_digest"] == package.oracle_digest,
        "Task package does not match plan",
    )
    budget = package.definition.budget.model_dump(mode="json")
    require(
        budget == plan["resource_budget"]
        and budget["max_output_tokens"] == request["declared_output_tokens"]
        and budget["timeout_seconds"]
        == profile.execution_timeout_seconds
        == request.get("subject_timeout_seconds_per_attempt")
        and package.manifest.verifier.timeout_seconds
        == request.get("verifier_timeout_seconds_per_attempt"),
        "Task/plan/profile/request budget mismatch",
    )
    prompt = render_codex_harness_prompt(
        task_instruction=package.definition.instruction,
        task_digest=package.definition.content_digest,
        workspace_input_digest=package.definition.workspace.digest,
        context_digest=(
            package.definition.context_bundle.digest if package.definition.context_bundle else None
        ),
        network_policy=profile.tool_network_policy,
        prompt_addendum=prompt_addendum,
    )
    require(
        expected_task["variants"][variant]
        == {
            "prompt_identity": prompt.prompt_hash,
            "prompt_text": prompt.text,
            "profile_identity": profile.fingerprint,
            "setup_identity": canonical_digest(
                {
                    "profile": profile.fingerprint,
                    "prompt": prompt.prompt_hash,
                    "resource_budget": budget,
                }
            ),
        },
        "Task Setup/prompt binding mismatch",
    )
    adapter = DevelopmentAdapter(profile.fingerprint)
    adapter.preflight(profile)  # Local validation only; no Docker/provider probing.
    connection = json.loads(vault.read(request["connection_reference"]))
    require(
        canonical_digest(connection)
        == request.get("connection_identity")
        == authorization.get("connection_identity")
        and connection["model"] == profile.requested_model
        and connection["model_reasoning_effort"] == profile.reasoning_effort
        and connection["wire_api"] == profile.provider_wire_api,
        "Connection binding mismatch",
    )
    proxy = ImageIdentity.model_validate(request["egress_proxy_image"])
    require(not output.exists(), "Execution output already exists")
    require(datetime.now(UTC) < expires, "Authorization expired during validation")
    _consume_authorization(vault, authorization)

    # First credential resolution and all executable work are behind the gate.
    endpoint = validate_provider_base_url(vault.read(connection["endpoint_vault_reference"]))
    key = vault.read(connection["credential_vault_reference"])
    require(bool(key), "Missing credential")
    boundary = boundary_for_provider_url(
        endpoint,
        network_name="hl-l1-" + execution_id,
        proxy_name="hl-l1-" + execution_id + "-proxy",
        proxy_image=proxy,
    )
    backend = DevelopmentBackend(
        explicitly_enabled=True,
        credentials={
            "HARNESSLAB_CODEX_RELAY_BASE_URL": endpoint,
            "HARNESSLAB_CODEX_RELAY_API_KEY": key,
        },
        egress_boundary=boundary,
    )
    output.mkdir(mode=0o700, parents=True, exist_ok=False)

    def execution_guard(
        actual_package: TaskPackage,
        actual_profile: CodexHarnessProfile,
        actual_prompt: CodexHarnessPrompt,
        actual_execution_id: str,
    ) -> None:
        # Recheck what the actual runner loaded/rendered, immediately before transport.
        require(datetime.now(UTC) < expires, "Authorization expired before transport")
        require(
            actual_execution_id == execution_id
            and actual_profile == profile
            and TaskIdentity.from_package(actual_package) == TaskIdentity.from_package(package)
            and actual_package.oracle_digest == package.oracle_digest
            and actual_package.definition.budget == package.definition.budget
            and actual_prompt == prompt,
            "Runner inputs changed after authorization",
        )

    runner = CodexHarnessRunner(
        artifact_root=output / "runs",
        runtime_root=output / "runtime",
        sandbox=DevelopmentSandbox(
            artifact_root=output / "verifier", runtime_root=output / "sandbox"
        ),
        adapter=adapter,
        plan_harness_config_identity=plan["plan_identity"],
    )
    return await runner.run(
        task_path,
        profile,
        backend=backend,
        run_id=execution_id,
        prompt_addendum=prompt_addendum,
        execution_guard=execution_guard,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="One freshly authorized L1 development attempt")
    for name in ("request", "plan", "authorization", "task", "vault", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--execution-id", required=True)
    parser.add_argument("--slot", required=True)
    parser.add_argument("--prompt-addendum", type=Path)
    args = parser.parse_args()
    asyncio.run(
        run_development_attempt(
            request=json.loads(args.request.read_bytes()),
            plan=json.loads(args.plan.read_bytes()),
            authorization=json.loads(args.authorization.read_bytes()),
            execution_id=args.execution_id,
            slot=args.slot,
            task_path=args.task,
            prompt_addendum=args.prompt_addendum.read_text() if args.prompt_addendum else None,
            vault=CredentialVault(args.vault),
            output=args.output,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Credential-bearing downstream exception text is not safe CLI output.
        print(json.dumps({"status": "STOPPED", "error_class": type(error).__name__}))
        raise SystemExit(1) from None
