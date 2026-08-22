from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from typing import Protocol

from pydantic import ValidationError

from harnesslab.tasks.models import (
    OutcomeCategory,
    VerifierExecutionResult,
    VerifierReport,
)
from harnesslab.tasks.package import (
    MaterializedTask,
    TaskPackage,
    TaskPackageError,
    resolve_package_path,
    sha256_bytes,
)

OUTPUT_LIMIT_BYTES = 65_536


class CapturedStream(Protocol):
    def read(self, size: int = -1) -> bytes: ...

    def seek(self, offset: int, whence: int = 0) -> int: ...

    def tell(self) -> int: ...


def _captured_output(stream: CapturedStream) -> tuple[str, str, bool]:
    stream.seek(0)
    digest = hashlib.sha256()
    captured = bytearray()
    while chunk := stream.read(65_536):
        digest.update(chunk)
        remaining = OUTPUT_LIMIT_BYTES - len(captured)
        if remaining > 0:
            captured.extend(chunk[:remaining])
    stream.seek(0, os.SEEK_END)
    truncated = stream.tell() > OUTPUT_LIMIT_BYTES
    return captured.decode("utf-8", errors="replace"), f"sha256:{digest.hexdigest()}", truncated


def _sanitized_environment() -> dict[str, str]:
    allowed = ("PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "HOME", "TMP", "TEMP", "LANG")
    environment = {name: os.environ[name] for name in allowed if name in os.environ}
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def _closed_failure(
    *,
    category: OutcomeCategory,
    summary: str,
    duration_ms: int = 0,
    exit_code: int | None = None,
    stdout_digest: str | None = None,
    stderr_digest: str | None = None,
    stdout_truncated: bool = False,
    stderr_truncated: bool = False,
) -> VerifierExecutionResult:
    empty_digest = sha256_bytes(b"")
    return VerifierExecutionResult(
        passed=False,
        score=0.0,
        checks=(),
        summary=summary,
        category=category,
        exit_code=exit_code,
        duration_ms=duration_ms,
        stdout_digest=stdout_digest or empty_digest,
        stderr_digest=stderr_digest or empty_digest,
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
    )


def protected_file_violations(materialized: MaterializedTask) -> tuple[str, ...]:
    violations: list[str] = []
    for relative, expected_digest in materialized.protected_digests:
        try:
            path = resolve_package_path(materialized.workspace, relative)
        except TaskPackageError:
            violations.append(relative)
            continue
        if not path.is_file() or sha256_bytes(path.read_bytes()) != expected_digest:
            violations.append(relative)
    return tuple(violations)


def execute_verifier(
    package: TaskPackage, materialized: MaterializedTask
) -> VerifierExecutionResult:
    violations = protected_file_violations(materialized)
    if violations:
        return _closed_failure(
            category=OutcomeCategory.PROTECTED_FILE_VIOLATION,
            summary=f"protected files changed: {', '.join(violations)}",
        )

    started = time.monotonic()
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        try:
            completed = subprocess.run(
                [sys.executable, str(package.verifier_entrypoint), str(materialized.workspace)],
                cwd=materialized.workspace,
                env=_sanitized_environment(),
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                timeout=package.manifest.verifier.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            duration_ms = int((time.monotonic() - started) * 1000)
            stdout, stdout_digest, stdout_truncated = _captured_output(stdout_file)
            stderr, stderr_digest, stderr_truncated = _captured_output(stderr_file)
            del stdout, stderr
            return _closed_failure(
                category=OutcomeCategory.TIMEOUT,
                summary="verifier timed out",
                duration_ms=duration_ms,
                stdout_digest=stdout_digest,
                stderr_digest=stderr_digest,
                stdout_truncated=stdout_truncated,
                stderr_truncated=stderr_truncated,
            )

        duration_ms = int((time.monotonic() - started) * 1000)
        stdout, stdout_digest, stdout_truncated = _captured_output(stdout_file)
        stderr, stderr_digest, stderr_truncated = _captured_output(stderr_file)

    if completed.returncode != 0:
        return _closed_failure(
            category=OutcomeCategory.VERIFIER_ERROR,
            summary="verifier process exited non-zero",
            duration_ms=duration_ms,
            exit_code=completed.returncode,
            stdout_digest=stdout_digest,
            stderr_digest=stderr_digest,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
        )
    if stdout_truncated:
        return _closed_failure(
            category=OutcomeCategory.MALFORMED_OUTPUT,
            summary="verifier output exceeded the capture limit",
            duration_ms=duration_ms,
            exit_code=completed.returncode,
            stdout_digest=stdout_digest,
            stderr_digest=stderr_digest,
            stdout_truncated=True,
            stderr_truncated=stderr_truncated,
        )
    try:
        report = VerifierReport.model_validate(json.loads(stdout))
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        return _closed_failure(
            category=OutcomeCategory.MALFORMED_OUTPUT,
            summary=f"malformed verifier output: {type(exc).__name__}",
            duration_ms=duration_ms,
            exit_code=completed.returncode,
            stdout_digest=stdout_digest,
            stderr_digest=stderr_digest,
            stderr_truncated=stderr_truncated,
        )
    return VerifierExecutionResult(
        passed=report.passed,
        score=report.score,
        checks=report.checks,
        summary=report.summary,
        category=OutcomeCategory.SUBJECT_RESULT,
        exit_code=completed.returncode,
        duration_ms=duration_ms,
        stdout_digest=stdout_digest,
        stderr_digest=stderr_digest,
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
    )
