from __future__ import annotations

import asyncio
import os
import re
import shutil
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from urllib.parse import unquote, urlsplit

from harnesslab.budget import BudgetCeilingStatus, PricingAvailability, estimate_budget
from harnesslab.contracts.common import NetworkPolicy, Protocol
from harnesslab.core.config import Settings
from harnesslab.db.health import check_database
from harnesslab.preflight.models import (
    CheckStatus,
    ConfigurationKind,
    ConfigurationRequirement,
    PreflightFinding,
    PreflightObservations,
    PreflightReport,
    PreflightSpecification,
    PreflightStatus,
    TaskObservation,
)
from harnesslab.sandbox.docker_cli import _DockerCLI
from harnesslab.sandbox.preflight import docker_preflight
from harnesslab.tasks.package import TaskPackage
from harnesslab.tasks.validation import validate_task_package

DockerCheck = Callable[[], Awaitable[object]]
DatabaseCheck = Callable[[Settings], Awaitable[None]]
_PROVIDER_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
_REFERENCE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _finding(
    check_id: str,
    status: CheckStatus,
    reason_code: str,
    detail: str,
    remediation: str,
) -> PreflightFinding:
    return PreflightFinding(
        check_id=check_id,
        status=status,
        reason_code=reason_code,
        detail=detail,
        remediation=remediation,
    )


def _configuration_is_valid(kind: ConfigurationKind, value: str) -> bool:
    if not value.strip():
        return False
    if kind in {ConfigurationKind.CREDENTIAL, ConfigurationKind.NON_EMPTY}:
        return True
    try:
        value.encode("ascii")
        parsed = urlsplit(value)
        hostname = parsed.hostname
        return bool(
            parsed.scheme == "https"
            and parsed.netloc
            and hostname
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
            and unquote(parsed.path) == parsed.path
        )
    except (UnicodeEncodeError, ValueError):
        return False


def _route_identity_is_valid(identity: str) -> bool:
    try:
        provider, protocol_value, endpoint = identity.split("|", 2)
        protocol = Protocol(protocol_value)
    except ValueError:
        return False
    if _PROVIDER_NAME.fullmatch(provider) is None:
        return False
    if endpoint.startswith("env:"):
        reference_and_path = endpoint.removeprefix("env:")
        reference, separator, path = reference_and_path.partition("/")
        if _REFERENCE.fullmatch(reference) is None or not separator:
            return False
        route = "/" + path
    else:
        try:
            parsed = urlsplit(endpoint)
        except ValueError:
            return False
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or unquote(parsed.path) != parsed.path
        ):
            return False
        route = parsed.path
    suffix = {
        Protocol.RESPONSES: "/responses",
        Protocol.CHAT_COMPLETIONS: "/chat/completions",
        Protocol.MESSAGES: "/messages",
    }.get(protocol)
    return bool(
        route.startswith("/") and "//" not in route and (suffix is None or route.endswith(suffix))
    )


def _all_configurations(
    specification: PreflightSpecification,
) -> tuple[ConfigurationRequirement, ...]:
    return specification.configurations + tuple(
        item for route in specification.provider_routes for item in route.configuration_references
    )


def assess_preflight(
    specification: PreflightSpecification,
    observations: PreflightObservations,
) -> PreflightReport:
    """Evaluate collected local facts without networking or provider execution."""

    findings: list[PreflightFinding] = []
    if specification.docker_required:
        findings.append(
            _finding(
                "docker",
                CheckStatus.PASS if observations.docker_available else CheckStatus.BLOCKED,
                "DOCKER_RUNTIME_READY"
                if observations.docker_available
                else "DOCKER_RUNTIME_MISSING",
                "The local Linux-container runtime is ready."
                if observations.docker_available
                else "The required local Linux-container runtime is unavailable.",
                "No action is required."
                if observations.docker_available
                else "Install or start the supported local Docker runtime and rerun preflight.",
            )
        )
    if specification.database_required:
        findings.append(
            _finding(
                "database",
                CheckStatus.PASS if observations.database_ready else CheckStatus.BLOCKED,
                "DATABASE_READY" if observations.database_ready else "DATABASE_NOT_READY",
                "The database accepted a keyless readiness query."
                if observations.database_ready
                else "The configured database is missing, invalid, or unreachable.",
                "No action is required."
                if observations.database_ready
                else (
                    "Configure DATABASE_URL for a reachable HarnessLab database and rerun "
                    "preflight."
                ),
            )
        )
    disk_ready = (
        observations.disk_free_bytes is not None
        and observations.disk_free_bytes >= specification.minimum_free_bytes
    )
    disk_detail = (
        "Disk capacity could not be inspected."
        if observations.disk_free_bytes is None
        else (
            f"Available disk space is {observations.disk_free_bytes} bytes; required "
            f"minimum is {specification.minimum_free_bytes} bytes."
        )
    )
    findings.append(
        _finding(
            "disk",
            CheckStatus.PASS if disk_ready else CheckStatus.BLOCKED,
            "DISK_SPACE_READY"
            if disk_ready
            else "DISK_SPACE_UNAVAILABLE"
            if observations.disk_free_bytes is None
            else "INSUFFICIENT_DISK_SPACE",
            disk_detail,
            "No action is required."
            if disk_ready
            else "Free disk space or select a workspace with the frozen minimum capacity.",
        )
    )
    for image in specification.required_images:
        available = observations.image_available.get(image, False)
        findings.append(
            _finding(
                f"image:{image}",
                CheckStatus.PASS if available else CheckStatus.BLOCKED,
                "REQUIRED_IMAGE_AVAILABLE" if available else "REQUIRED_IMAGE_MISSING",
                f"Required image {image} is locally available."
                if available
                else f"Required image {image} is not locally available.",
                "No action is required."
                if available
                else f"Build or load the frozen image {image} without changing its identity.",
            )
        )
    for requirement in _all_configurations(specification):
        present = observations.configuration_present.get(requirement.reference, False)
        valid = observations.configuration_valid.get(requirement.reference, False)
        if not present:
            status = CheckStatus.BLOCKED if requirement.required else CheckStatus.WARNING
            reason = (
                "REQUIRED_CONFIGURATION_MISSING"
                if requirement.required
                else "OPTIONAL_CONFIGURATION_MISSING"
            )
            detail = f"Configuration reference {requirement.reference} is MISSING."
            remediation = (
                f"Set {requirement.reference} in the execution environment; do not place its "
                "value in manifests."
            )
        elif not valid:
            status = CheckStatus.BLOCKED
            reason = "CONFIGURATION_INVALID"
            detail = (
                f"Configuration reference {requirement.reference} is SET but invalid for "
                f"{requirement.kind.value}."
            )
            remediation = (
                f"Correct {requirement.reference} without exposing its value, then rerun preflight."
            )
        else:
            status = CheckStatus.PASS
            reason = "CONFIGURATION_VALID"
            detail = f"Configuration reference {requirement.reference} is SET and valid."
            remediation = "No action is required."
        findings.append(
            _finding(f"configuration:{requirement.reference}", status, reason, detail, remediation)
        )
    for index, route in enumerate(specification.provider_routes):
        canonical = _route_identity_is_valid(route.route_identity)
        matches = route.expected_identity is None or route.route_identity == route.expected_identity
        ready = canonical and matches
        findings.append(
            _finding(
                f"provider-route:{index}",
                CheckStatus.PASS if ready else CheckStatus.BLOCKED,
                "PROVIDER_ROUTE_IDENTITY_VALID"
                if ready
                else "PROVIDER_ROUTE_IDENTITY_MISMATCH"
                if canonical
                else "PROVIDER_ROUTE_IDENTITY_INVALID",
                "The provider route has a canonical, frozen configuration identity."
                if ready
                else "The provider route identity does not match the required frozen identity."
                if canonical
                else "The provider route identity is not canonical.",
                "No action is required."
                if ready
                else (
                    "Restore the preregistered provider/protocol/endpoint identity; do not "
                    "substitute a route."
                ),
            )
        )
        if route.requires_network and specification.network_policy is NetworkPolicy.DENY:
            findings.append(
                _finding(
                    f"network:{index}",
                    CheckStatus.BLOCKED,
                    "NETWORK_POLICY_CONFLICT",
                    (
                        "The selected provider route requires network access but the frozen "
                        "policy denies it."
                    ),
                    (
                        "Select the preregistered allowlist policy or a keyless route that "
                        "requires no network."
                    ),
                )
            )
        else:
            findings.append(
                _finding(
                    f"network:{index}",
                    CheckStatus.PASS,
                    "NETWORK_POLICY_COMPATIBLE",
                    "The selected route is compatible with the frozen network policy.",
                    "No action is required.",
                )
            )
    for harness in specification.harnesses:
        runtime_ready = observations.harness_runtime_available.get(harness.harness_id, False)
        findings.append(
            _finding(
                f"harness-runtime:{harness.harness_id}",
                CheckStatus.PASS if runtime_ready else CheckStatus.BLOCKED,
                "HARNESS_RUNTIME_READY" if runtime_ready else "HARNESS_RUNTIME_MISSING",
                f"Harness runtime {harness.harness_id} is available."
                if runtime_ready
                else f"Harness runtime {harness.harness_id} is unavailable.",
                "No action is required."
                if runtime_ready
                else "Install or build the frozen harness runtime before spending provider budget.",
            )
        )
        lane_ready = harness.selected_lane in harness.supported_lanes
        findings.append(
            _finding(
                f"harness-lane:{harness.harness_id}",
                CheckStatus.PASS if lane_ready else CheckStatus.BLOCKED,
                "HARNESS_LANE_SUPPORTED" if lane_ready else "HARNESS_CAPABILITY_UNSUPPORTED",
                "The harness supports the selected evaluation lane."
                if lane_ready
                else "The harness does not support the selected evaluation lane.",
                "No action is required."
                if lane_ready
                else (
                    "Select a supported harness/lane pairing without changing historical evidence."
                ),
            )
        )
        model_ready = (
            not harness.compatible_models or harness.requested_model in harness.compatible_models
        )
        findings.append(
            _finding(
                f"harness-model:{harness.harness_id}",
                CheckStatus.PASS if model_ready else CheckStatus.BLOCKED,
                "MODEL_HARNESS_COMPATIBLE" if model_ready else "MODEL_HARNESS_INCOMPATIBLE",
                "The requested model is supported by the harness configuration."
                if model_ready
                else "The requested model is not supported by the frozen harness configuration.",
                "No action is required."
                if model_ready
                else (
                    "Use a preregistered compatible model/harness pair; do not substitute at "
                    "runtime."
                ),
            )
        )
        trace_ready = harness.trace_support.level >= harness.required_trace_support.level
        findings.append(
            _finding(
                f"trace:{harness.harness_id}",
                CheckStatus.PASS if trace_ready else CheckStatus.BLOCKED,
                "TRACE_SUPPORT_READY" if trace_ready else "REQUIRED_TRACE_UNSUPPORTED",
                "The harness provides the required trace coverage."
                if trace_ready
                else "The harness cannot provide the required trace coverage.",
                "No action is required."
                if trace_ready
                else (
                    "Choose a harness with the preregistered trace coverage or revise the plan "
                    "before freeze."
                ),
            )
        )
    for task in specification.tasks:
        observation = observations.tasks.get(task.package_path)
        valid = observation is not None and observation.valid
        findings.append(
            _finding(
                f"task:{task.package_path}",
                CheckStatus.PASS if valid else CheckStatus.BLOCKED,
                "TASK_VALID" if valid else "TASK_INVALID",
                f"Task package {task.package_path} passed deterministic validation."
                if valid
                else f"Task package {task.package_path} is missing or invalid.",
                "No action is required."
                if valid
                else "Repair or qualify a new task version; never rewrite a historical package.",
            )
        )
        lane_ready = observation is not None and task.selected_lane in observation.supported_lanes
        findings.append(
            _finding(
                f"task-lane:{task.package_path}",
                CheckStatus.PASS if lane_ready else CheckStatus.BLOCKED,
                "TASK_LANE_SUPPORTED" if lane_ready else "TASK_LANE_UNSUPPORTED",
                "The task supports the selected evaluation lane."
                if lane_ready
                else "The task does not support the selected evaluation lane.",
                "No action is required."
                if lane_ready
                else "Select a supported lane or publish a newly versioned qualified task package.",
            )
        )
    for control in specification.comparability_controls:
        matches = control.expected_identity == control.actual_identity
        status = (
            CheckStatus.PASS
            if matches
            else CheckStatus.BLOCKED
            if control.blocking
            else CheckStatus.WARNING
        )
        findings.append(
            _finding(
                f"comparability:{control.name}",
                status,
                "COMPARABILITY_CONTROL_MATCH" if matches else "COMPARABILITY_RISK",
                f"Comparability control {control.name} is frozen and matched."
                if matches
                else f"Comparability control {control.name} differs from its frozen identity.",
                "No action is required."
                if matches
                else (
                    "Resolve the declared control drift or retain the warning in the claim "
                    "boundary."
                ),
            )
        )
    envelope = specification.resource_envelope
    if envelope is not None:
        ready = envelope.frozen and envelope.actual_identity == envelope.expected_identity
        reason = (
            "RESOURCE_ENVELOPE_FROZEN"
            if ready
            else "RESOURCE_ENVELOPE_NOT_FROZEN"
            if not envelope.frozen
            else "RESOURCE_ENVELOPE_IDENTITY_MISMATCH"
        )
        findings.append(
            _finding(
                "resource-envelope",
                CheckStatus.PASS if ready else CheckStatus.BLOCKED,
                reason,
                "The resource envelope is frozen and its identity matches."
                if ready
                else "The required resource envelope is absent, mutable, or identity-mismatched.",
                "No action is required."
                if ready
                else "Freeze the complete runtime resource envelope before provider execution.",
            )
        )
    budget_estimate = (
        estimate_budget(specification.budget) if specification.budget is not None else None
    )
    if budget_estimate is None:
        findings.append(
            _finding(
                "budget",
                CheckStatus.BLOCKED,
                "BUDGET_ESTIMATE_REQUIRED",
                "No deterministic pre-spend budget request was supplied.",
                "Declare call, token, request, harness-turn, pricing, and cost ceilings.",
            )
        )
    else:
        pricing_known = budget_estimate.estimated_cost_availability is PricingAvailability.KNOWN
        findings.append(
            _finding(
                "pricing",
                CheckStatus.PASS if pricing_known else CheckStatus.WARNING,
                "PRICING_KNOWN" if pricing_known else "PRICING_UNKNOWN",
                "Worst-case cost is backed by supplied immutable pricing."
                if pricing_known
                else "At least one active route has unknown pricing; its cost is not zero.",
                "No action is required."
                if pricing_known
                else "Register immutable price evidence or retain cost as unknown.",
            )
        )
        ceiling_status = budget_estimate.budget_ceiling_status
        ceiling_ready = ceiling_status is BudgetCeilingStatus.WITHIN_CEILING
        reason_code = {
            BudgetCeilingStatus.WITHIN_CEILING: "BUDGET_WITHIN_CEILING",
            BudgetCeilingStatus.EXCEEDS_CEILING: "BUDGET_CEILING_EXCEEDED",
            BudgetCeilingStatus.INDETERMINATE: "BUDGET_CEILING_INDETERMINATE",
            BudgetCeilingStatus.NOT_CONFIGURED: "BUDGET_CEILING_NOT_CONFIGURED",
        }[ceiling_status]
        findings.append(
            _finding(
                "budget-ceiling",
                CheckStatus.PASS if ceiling_ready else CheckStatus.BLOCKED,
                reason_code,
                "Projected worst-case cost is within the frozen budget ceiling."
                if ceiling_ready
                else "Projected worst-case cost cannot be authorized by the budget ceiling.",
                "No action is required."
                if ceiling_ready
                else "Provide a sufficient ceiling and immutable pricing before execution.",
            )
        )
    if not findings:
        findings.append(
            _finding(
                "specification",
                CheckStatus.WARNING,
                "NO_APPLICABLE_CHECKS",
                "The specification declared no spend-bearing prerequisites.",
                "Declare all applicable runtime, task, route, trace, and budget requirements.",
            )
        )
    overall_status = (
        PreflightStatus.BLOCKED
        if any(item.status is CheckStatus.BLOCKED for item in findings)
        else PreflightStatus.READY_WITH_WARNINGS
        if any(item.status is CheckStatus.WARNING for item in findings)
        else PreflightStatus.READY
    )
    return PreflightReport(
        status=overall_status,
        specification_digest=specification.digest,
        findings=tuple(findings),
        budget_estimate=budget_estimate,
    )


async def _image_is_available(executable: str, image: str) -> bool:
    try:
        result = await _DockerCLI(executable).run(
            "image", "inspect", image, "--format", "{{.Id}}", timeout=15, check=False
        )
    except Exception:
        return False
    return result.returncode == 0 and bool(result.stdout.strip())


async def run_preflight(
    specification: PreflightSpecification,
    repository_root: Path,
    environment: Mapping[str, str] | None = None,
    *,
    docker_check: DockerCheck = docker_preflight,
    database_check: DatabaseCheck = check_database,
) -> PreflightReport:
    """Collect local readiness facts. This function never executes a provider or Judge."""

    root = repository_root.resolve()
    source_environment = dict(os.environ if environment is None else environment)
    docker_available: bool | None = None
    if specification.docker_required or specification.required_images:
        try:
            await docker_check()
        except Exception:
            docker_available = False
        else:
            docker_available = True
    executable = shutil.which("docker")
    image_available = {
        image: bool(
            docker_available
            and executable is not None
            and await _image_is_available(executable, image)
        )
        for image in specification.required_images
    }
    database_ready: bool | None = None
    if specification.database_required:
        database_url = source_environment.get("DATABASE_URL", "").strip()
        if not database_url:
            database_ready = False
        else:
            try:
                settings = Settings.without_dotenv(database_url=database_url)
                await database_check(settings)
            except Exception:
                database_ready = False
            else:
                database_ready = True
    configurations = _all_configurations(specification)
    configuration_present = {
        item.reference: bool(source_environment.get(item.reference, "").strip())
        for item in configurations
    }
    configuration_valid = {
        item.reference: _configuration_is_valid(
            item.kind, source_environment.get(item.reference, "")
        )
        for item in configurations
    }
    harness_runtime_available = {
        item.harness_id: item.executable is None or shutil.which(item.executable) is not None
        for item in specification.harnesses
    }
    task_observations: dict[str, TaskObservation] = {}
    for requirement in specification.tasks:
        candidate = (root / requirement.package_path).resolve()
        tasks_root = (root / "tasks").resolve()
        if tasks_root not in candidate.parents:
            task_observations[requirement.package_path] = TaskObservation(valid=False)
            continue
        try:
            package = TaskPackage.load(candidate)
            validation = await asyncio.to_thread(validate_task_package, candidate)
        except Exception:
            task_observations[requirement.package_path] = TaskObservation(valid=False)
        else:
            task_observations[requirement.package_path] = TaskObservation(
                valid=validation.valid,
                supported_lanes=package.definition.lane_support,
            )
    try:
        disk_free_bytes = shutil.disk_usage(root).free
    except OSError:
        disk_free_bytes = None
    observations = PreflightObservations(
        docker_available=docker_available,
        database_ready=database_ready,
        disk_free_bytes=disk_free_bytes,
        image_available=image_available,
        configuration_present=configuration_present,
        configuration_valid=configuration_valid,
        harness_runtime_available=harness_runtime_available,
        tasks=task_observations,
    )
    return assess_preflight(specification, observations)
