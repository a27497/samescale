from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from harnesslab.release.models import (
    BadCasePlan,
    CoreCorpusManifest,
    CoreTaskInventoryEntry,
    EvidenceState,
    RealEvidencePlan,
    RealSmokePlan,
    ReleaseEvidenceManifest,
    ReleaseHistorySummary,
    ReleaseReadiness,
    ResumeClaimMap,
    SemanticReleaseReceipt,
    TechnicalReadinessManifest,
    ValidationResult,
)
from harnesslab.tasks.package import TaskPackage, TaskPackageError
from harnesslab.tasks.validation import validate_task_package


class CoreReleaseError(ValueError):
    """Phase K release input is missing, inconsistent, or unsafe."""


def _load_json[T](path: Path, validator: Callable[[Any], T], label: str) -> T:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return validator(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        raise CoreReleaseError(f"invalid {label}: {type(exc).__name__}") from exc


def discover_task_packages(
    repository_root: Path, *, task_version: str = "1.0.0"
) -> tuple[Path, ...]:
    """Discover Tier-A Core packages without folding qualified Tier-B tasks into its corpus."""

    tasks_root = repository_root / "tasks"
    discovered: list[Path] = []
    for manifest in sorted(tasks_root.glob(f"*/{task_version}/task.yaml")):
        task_path = manifest.parent
        try:
            if TaskPackage.load(task_path).manifest.repo_engineering is not None:
                continue
        except TaskPackageError:
            # Keep malformed candidates visible so Core validation fails closed downstream.
            pass
        discovered.append(task_path)
    return tuple(discovered)


def build_corpus_manifest(
    repository_root: Path, *, task_version: str = "1.0.0"
) -> CoreCorpusManifest:
    entries: list[CoreTaskInventoryEntry] = []
    for task_path in discover_task_packages(repository_root, task_version=task_version):
        try:
            package = TaskPackage.load(task_path)
            validation = validate_task_package(task_path)
        except TaskPackageError as exc:
            raise CoreReleaseError(f"invalid Core task package: {task_path.name}") from exc
        if not validation.valid:
            raise CoreReleaseError(
                f"Core task validation failed for {validation.task_id}: {validation.errors}"
            )
        definition = package.definition
        metadata = definition.metadata
        try:
            language = metadata["language"]
            category = metadata["category"]
            scenario_family = metadata["scenario_family"]
            benchmark_role = metadata["benchmark_role"]
            difficulty = metadata["difficulty"]
        except KeyError as exc:
            raise CoreReleaseError(f"Core task metadata is incomplete for {definition.id}") from exc
        entries.append(
            CoreTaskInventoryEntry(
                package_path=task_path.relative_to(repository_root).as_posix(),
                task_id=definition.id,
                version=definition.version,
                language=language,
                domain=definition.domain,
                category=category,
                scenario_family=scenario_family,
                benchmark_role=benchmark_role,
                difficulty_band=difficulty,
                task_digest=definition.content_digest,
                verifier_identity=package.verifier_digest,
                workspace_input_identity=definition.workspace.digest,
                lane_support=tuple(sorted(lane.value for lane in definition.lane_support)),
                expected_toolchain=tuple(
                    f"{tool.name}=={tool.version}" for tool in definition.expected_tools
                ),
                baseline=ValidationResult(
                    passed=validation.baseline.result.passed,
                    score=validation.baseline.result.score,
                ),
                oracle=ValidationResult(
                    passed=validation.oracle.result.passed,
                    score=validation.oracle.result.score,
                ),
            )
        )
    return CoreCorpusManifest(tasks=tuple(sorted(entries, key=lambda task: task.task_id)))


def load_core_corpus(path: Path) -> CoreCorpusManifest:
    return _load_json(path, CoreCorpusManifest.model_validate, "Core corpus manifest")


def load_real_evidence_plan(path: Path) -> RealEvidencePlan:
    return _load_json(path, RealEvidencePlan.model_validate, "real-evidence plan")


def load_real_smoke_plan(path: Path) -> RealSmokePlan:
    return _load_json(path, RealSmokePlan.model_validate, "real-smoke plan")


def load_release_evidence(path: Path) -> ReleaseEvidenceManifest:
    return _load_json(path, ReleaseEvidenceManifest.model_validate, "release evidence")


def load_technical_readiness(path: Path) -> TechnicalReadinessManifest:
    return _load_json(
        path, TechnicalReadinessManifest.model_validate, "technical readiness evidence"
    )


def load_resume_claim_map(path: Path) -> ResumeClaimMap:
    return _load_json(path, ResumeClaimMap.model_validate, "resume claim map")


def load_badcase_plan(path: Path) -> BadCasePlan:
    return _load_json(path, BadCasePlan.model_validate, "BadCase plan")


def load_contiguous_v2_histories(
    history_directory: Path, repository_root: Path
) -> tuple[tuple[dict[str, Any], ...], tuple[str, ...]]:
    pattern = re.compile(r"^core-real-v2-attempt-([1-9][0-9]*)\.json$")
    numbered_paths: list[tuple[int, Path]] = []
    for path in history_directory.glob("core-real-v2-attempt-*.json"):
        match = pattern.fullmatch(path.name)
        if match is None:
            raise CoreReleaseError(f"invalid v2 attempt history filename: {path.name}")
        numbered_paths.append((int(match.group(1)), path))
    numbered_paths.sort(key=lambda item: item[0])
    attempt_numbers = tuple(number for number, _ in numbered_paths)
    if not attempt_numbers:
        raise CoreReleaseError("immutable v2 history must contain at least one attempt")
    if len(set(attempt_numbers)) != len(attempt_numbers):
        raise CoreReleaseError("immutable v2 history contains duplicate attempt numbers")
    if attempt_numbers != tuple(range(1, attempt_numbers[-1] + 1)):
        raise CoreReleaseError("immutable v2 history must be contiguous beginning at attempt 1")
    paths = tuple(path for _, path in numbered_paths)
    try:
        histories = tuple(json.loads(path.read_text(encoding="utf-8")) for path in paths)
        references = tuple(path.relative_to(repository_root).as_posix() for path in paths)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise CoreReleaseError("invalid immutable v2 history artifact") from exc
    if any(not isinstance(history, dict) for history in histories):
        raise CoreReleaseError("immutable v2 history artifact must be an object")
    return histories, references


def validate_dynamic_v2_history(
    histories: tuple[dict[str, Any], ...],
    references: tuple[str, ...],
    summary: ReleaseHistorySummary,
    *,
    smoke_plan_digest: str,
    release_plan_digest: str,
    smoke_call_ids: tuple[str, ...],
) -> None:
    if not histories or len(histories) != len(references):
        raise CoreReleaseError("v2 history and reference sets must be non-empty and aligned")
    for attempt_number, (history, reference) in enumerate(
        zip(histories, references, strict=True), start=1
    ):
        expected_attempt_id = f"core-real-smoke-v2-attempt-{attempt_number}"
        if history.get("attempt_id") != expected_attempt_id:
            raise CoreReleaseError("v2 history attempt identity disagrees with its sequence")
        if reference != f"release/history/core-real-v2-attempt-{attempt_number}.json":
            raise CoreReleaseError("v2 history reference disagrees with its sequence")
        if (
            history.get("smoke_plan_digest") != smoke_plan_digest
            or history.get("release_plan_digest") != release_plan_digest
        ):
            raise CoreReleaseError("v2 history frozen plan digest drifted")
        if history.get("retry_count") != 0 or history.get("fallback_count") != 0:
            raise CoreReleaseError("v2 history retry/fallback invariant drifted")
        attempted = history.get("attempted_top_level_launches")
        if not isinstance(attempted, int) or not 1 <= attempted <= len(smoke_call_ids):
            raise CoreReleaseError("v2 history attempted launch count is invalid")
        calls = history.get("calls")
        if (
            not isinstance(calls, list)
            or any(not isinstance(call, dict) for call in calls)
            or tuple(call.get("call_id") for call in calls) != smoke_call_ids[:attempted]
        ):
            raise CoreReleaseError("v2 history call sequence disagrees with the frozen smoke order")
        status = history.get("status")
        if status == "ABORTED":
            if history.get("failing_call_id") != smoke_call_ids[attempted - 1]:
                raise CoreReleaseError("aborted v2 history failing call disagrees with call order")
        elif status == "SUCCEEDED":
            if attempted != len(smoke_call_ids) or history.get("failing_call_id") is not None:
                raise CoreReleaseError("successful v2 history must complete every frozen call")
        else:
            raise CoreReleaseError("v2 history has an unsupported terminal status")
        if attempted < len(smoke_call_ids):
            marker = f"calls_{attempted + 1}_to_{len(smoke_call_ids)}"
            if history.get(marker) != "NOT_RUN":
                raise CoreReleaseError("v2 history NOT_RUN marker disagrees with attempted calls")

    latest = histories[-1]
    attempted = int(latest["attempted_top_level_launches"])
    expected_not_run = smoke_call_ids[attempted:]
    if (
        summary.attempt_references != references
        or summary.latest_attempt_id != latest.get("attempt_id")
        or summary.latest_attempt_status != latest.get("status")
        or summary.latest_failing_call_id != latest.get("failing_call_id")
        or summary.latest_not_run_call_ids != expected_not_run
    ):
        raise CoreReleaseError(
            "top-level latest-attempt summary disagrees with immutable v2 history"
        )


def evaluate_release_readiness(manifest: ReleaseEvidenceManifest) -> ReleaseReadiness:
    checks = {
        "RELEASE_COMMIT": manifest.release_commit,
        "EXPERIMENT_PLAN": manifest.experiment_plan,
        "REAL_MATRIX_EVIDENCE": manifest.real_matrix,
        "PAIRED_LANE": manifest.paired_lane,
        "ABLATION": manifest.controlled_ablation,
        "JUDGE_EVIDENCE": manifest.judge_report,
        "REMOTE_CI": manifest.remote_ci,
    }
    blockers = tuple(
        key for key, binding in checks.items() if binding.state is not EvidenceState.VERIFIED
    )
    if any(binding.state is not EvidenceState.VERIFIED for binding in manifest.badcase_evidence):
        blockers += ("BADCASE_EVIDENCE",)
    blockers += tuple(
        key
        for key, state in sorted(manifest.real_statuses.items())
        if state is not EvidenceState.VERIFIED
    )
    return ReleaseReadiness(
        core_release_ready=manifest.core_release_ready and not blockers,
        blockers=blockers,
        real_evidence_authorization_required=manifest.real_evidence_authorization_required,
    )


def validate_keyless_contract_state(manifest: ReleaseEvidenceManifest) -> None:
    expected = {
        "REAL_PROVIDER_SMOKE": EvidenceState.NOT_VERIFIED,
        "REAL_CODEX_SMOKE": EvidenceState.NOT_VERIFIED,
        "REAL_CLAUDE_SMOKE": EvidenceState.NOT_RUN,
        "REAL_DEEPSEEK_SMOKE": EvidenceState.NOT_RUN,
        "REAL_MATRIX_EVIDENCE": EvidenceState.NOT_RUN,
        "REAL_JUDGE_SMOKE": EvidenceState.NOT_RUN,
    }
    if manifest.real_statuses != expected:
        raise CoreReleaseError("K-B1-R5 REAL_* stop state drifted")
    if manifest.core_release_ready:
        raise CoreReleaseError("K-B1-R5 cannot report CORE_RELEASE_READY")
    if not manifest.real_evidence_authorization_required:
        raise CoreReleaseError("K-B1-R5 must require explicit real-evidence authorization")


def tag_creation_authorized(
    manifest: ReleaseEvidenceManifest, receipt: SemanticReleaseReceipt | None = None
) -> bool:
    readiness = evaluate_release_readiness(manifest)
    return (
        readiness.core_release_ready
        and not readiness.real_evidence_authorization_required
        and receipt is not None
        and receipt.semantic_verified
        and receipt.release_manifest_digest == manifest.digest
    )
