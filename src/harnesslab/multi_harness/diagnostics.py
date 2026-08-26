from __future__ import annotations

import hashlib
from dataclasses import dataclass

from harnesslab.multi_harness.models import (
    HarnessProcessCapture,
    ProcessDiagnosticCategory,
    StartupFailureCategory,
)
from harnesslab.sandbox.artifacts import redact_exact


@dataclass(frozen=True)
class SafeProcessDiagnostics:
    stderr_category: ProcessDiagnosticCategory
    stderr_digest: str | None
    stdout_line_count: int
    startup_failure_category: StartupFailureCategory | None


def _classify_startup_failure(sanitized_stderr: str) -> StartupFailureCategory:
    normalized = " ".join(sanitized_stderr.casefold().split())
    if any(
        pattern in normalized
        for pattern in (
            "invalid mcp configuration",
            "mcpservers: invalid input",
            "provider configuration",
            "invalid base url",
        )
    ):
        return StartupFailureCategory.PROVIDER_BOOTSTRAP_ERROR
    if any(
        pattern in normalized
        for pattern in (
            "authentication failed",
            "authentication error",
            "invalid api key",
            "api key is required",
        )
    ):
        return StartupFailureCategory.AUTHENTICATION_ERROR
    if any(
        pattern in normalized
        for pattern in (
            "invalid permission mode",
            "permission configuration",
            "bypasspermissions is disabled",
        )
    ):
        return StartupFailureCategory.PERMISSION_CONFIGURATION_ERROR
    if any(
        pattern in normalized
        for pattern in (
            "unknown option",
            "unknown argument",
            "missing required argument",
            "usage: claude",
        )
    ):
        return StartupFailureCategory.CLI_USAGE_ERROR
    return StartupFailureCategory.UNKNOWN


def safe_process_diagnostics(
    capture: HarnessProcessCapture, *, secret_values: tuple[str, ...]
) -> SafeProcessDiagnostics:
    category = capture.stderr_category
    if category is None:
        category = (
            ProcessDiagnosticCategory.PRESENT
            if capture.stderr_text
            else ProcessDiagnosticCategory.EMPTY
        )
    if category in {
        ProcessDiagnosticCategory.UNAVAILABLE,
        ProcessDiagnosticCategory.READ_FAILED,
    }:
        return SafeProcessDiagnostics(category, None, len(capture.stdout_lines), None)

    sanitized = redact_exact(capture.stderr_text, secret_values)
    digest = "sha256:" + hashlib.sha256(sanitized.encode("utf-8")).hexdigest()
    startup_category = (
        _classify_startup_failure(sanitized)
        if category in {ProcessDiagnosticCategory.PRESENT, ProcessDiagnosticCategory.TRUNCATED}
        and capture.exit_code not in {0, None}
        and not capture.stdout_lines
        else None
    )
    return SafeProcessDiagnostics(category, digest, len(capture.stdout_lines), startup_category)
