"""Operator CLI only: existing isolated Verifier, never an Agent/Provider or API process."""

from __future__ import annotations

import fcntl
import json
import os
import shutil
import tempfile
from typing import Any

from harnesslab.episodes.hooks import _write_once, encode
from harnesslab.external_evidence.models import EvidencePolicy
from harnesslab.external_evidence.service import (
    content_digest,
    overlap,
    read_record,
    record_root,
    safe_root,
    unknown_verification,
    verification_receipt,
    workspace_files,
)
from harnesslab.local_execution.sandbox import PinnedVerifierSandbox
from harnesslab.local_plans.tasks import inspect_task, load_policy
from harnesslab.registry.models import canonical_digest
from harnesslab.sandbox.runner import SandboxExecutionError
from harnesslab.tasks.models import VerifierReport
from harnesslab.tasks.package import sha256_bytes


async def verify_workspace(policy: EvidencePolicy, identity: str) -> dict[str, Any]:
    record = read_record(policy, identity)
    # Reuse TaskStore's exact Custom qualification / baseline-fail / oracle-pass gate.
    source = next((s for s in policy.sources if s.binding == record.source), None)
    if source is None or source.task_reference is None or source.task_digest is None:
        raise ValueError("separate trusted task mapping required")
    task_policy = load_policy()
    for path in (
        task_policy.managed_store,
        *task_policy.source_roots.values(),
        *(a.qualification_file for a in task_policy.admissions),
        *(a.validation_file for a in task_policy.admissions),
    ):
        safe_root(path)
        if any(
            r is not None and overlap(path, r)
            for r in (policy.store, policy.runtime_root, policy.artifact_root)
        ):
            raise ValueError("task/verifier storage overlaps imported data")
    inspection, package = inspect_task(task_policy, source.task_reference)
    if (
        not inspection.eligible_for_planning
        or package.definition.content_digest != source.task_digest
        or policy.verifier_image_id is None
        or policy.runtime_root is None
        or policy.artifact_root is None
    ):
        raise ValueError("trusted admission and pinned isolated verifier required")
    prior_task = record.recorded_verification.get("task_digest")
    if prior_task is not None and prior_task != source.task_digest:
        raise ValueError("independent task mapping contradicts the saved binding")
    policy.runtime_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root = record_root(policy, identity)
    # CLI one writer, no automatic retry. An incomplete attempt stays NOT_VERIFIED.
    with (root / ".verification-lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        prior = verification_receipt(policy, identity)
        if prior is not None:
            return prior
        _write_once(
            root / "verification-attempt.json",
            encode(
                {
                    "record_identity": record.identity,
                    "physical_attempts": 1,
                    "automatic_retry": False,
                    "agent_reexecuted": False,
                }
            ),
        )
        # _write_once permits identical bytes; existence itself must burn the attempt.
        started = root / ".verifier-started"
        with started.open("xb") as stream:
            stream.write(b"ONE_ATTEMPT_NO_RETRY\n")
            stream.flush()
            os.fsync(stream.fileno())
        directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        receipt: dict[str, Any] = {
            **unknown_verification("VERIFIER_INFRASTRUCTURE_FAILURE"),
            "record_identity": record.identity,
            "workspace_digest": record.workspace_digest,
            "task_digest": package.definition.content_digest,
            "verifier_digest": package.verifier_digest,
            "qualification_identity": inspection.qualification_identity,
            "image_id": policy.verifier_image_id,
            "authority": "L0_INDEPENDENT_VERIFIER",
            "agent_reexecuted": False,
            "physical_attempts": 1,
            "automatic_retry": False,
            "scope": "FINAL_WORKSPACE_CONTRACT_NOT_AGENT_INSTRUCTION_COMPLIANCE",
        }
        try:
            with tempfile.TemporaryDirectory(
                dir=policy.runtime_root, prefix="external-copy-"
            ) as temporary:
                from pathlib import Path

                workspace = Path(temporary) / "workspace"
                shutil.copytree(root / "workspace", workspace)
                files = workspace_files(workspace)
                if content_digest(files) != record.workspace_digest:
                    raise ValueError("workspace drift before verification")
                # Contract files are checked before sandboxing; imported code stays data.
                protected = package.materialize(Path(temporary) / "contract-baseline")
                if any(
                    files.get(name) is None or sha256_bytes(files[name]) != digest
                    for name, digest in protected.protected_digests
                ):
                    raise ValueError("protected task contract changed")
                sandbox = PinnedVerifierSandbox(
                    image_id=policy.verifier_image_id,
                    run_id="external-" + identity[:32],
                    runtime_root=policy.runtime_root,
                    artifact_root=policy.artifact_root,
                )
                result = await sandbox.run_hidden_verifier_workspace(
                    package,
                    workspace,
                    timeout_seconds=min(package.manifest.verifier.timeout_seconds, 30),
                )
                report = VerifierReport.model_validate(json.loads(result.run.stdout))
                manifest = result.run.manifest
                if (
                    not report.checks
                    or len({c.name for c in report.checks}) != len(report.checks)
                    or report.passed != all(c.passed for c in report.checks)
                    or report.score != sum(c.passed for c in report.checks) / len(report.checks)
                    or manifest.workspace_input_digest != record.workspace_digest
                    or manifest.workspace_output_digest != record.workspace_digest
                    or manifest.stdout_truncated
                    or manifest.stderr_truncated
                    or not manifest.cleanup_verified
                    or result.lifecycle is None
                    or result.lifecycle.failure_subtype is not None
                ):
                    raise ValueError("incomplete or contradictory verifier evidence")
                receipt.update(
                    acceptance="VERIFIED_PASS" if report.passed else "VERIFIED_FAIL",
                    checks=len(report.checks),
                    passed_checks=sum(c.passed for c in report.checks),
                    check_results=[
                        {"ordinal": i, "passed": c.passed} for i, c in enumerate(report.checks, 1)
                    ],
                    reason="INDEPENDENT_WORKSPACE_CONTRACT",
                    report_digest=sha256_bytes(result.run.stdout.encode()),
                    manifest_digest=canonical_digest(manifest.model_dump(mode="json")),
                    lifecycle_digest=canonical_digest(result.lifecycle.model_dump(mode="json")),
                )
        except (OSError, ValueError, SandboxExecutionError):
            # No raw exception/report text or verifier assets cross into the public record.
            pass
        receipt["receipt_digest"] = canonical_digest(receipt)
        _write_once(root / "verification.json", encode(receipt))
        return receipt
