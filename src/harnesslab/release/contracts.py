from __future__ import annotations

import json
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
    ReleaseReadiness,
    ResumeClaimMap,
    SemanticReleaseReceipt,
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


def discover_task_packages(repository_root: Path) -> tuple[Path, ...]:
    tasks_root = repository_root / "tasks"
    return tuple(sorted(path.parent for path in tasks_root.glob("*/*/task.yaml")))


def build_corpus_manifest(repository_root: Path) -> CoreCorpusManifest:
    entries: list[CoreTaskInventoryEntry] = []
    for task_path in discover_task_packages(repository_root):
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


def load_resume_claim_map(path: Path) -> ResumeClaimMap:
    return _load_json(path, ResumeClaimMap.model_validate, "resume claim map")


def load_badcase_plan(path: Path) -> BadCasePlan:
    return _load_json(path, BadCasePlan.model_validate, "BadCase plan")


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
