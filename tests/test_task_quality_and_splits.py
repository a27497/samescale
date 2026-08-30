from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from harnesslab.comparability.models import canonical_digest
from harnesslab.tasks.package import TaskPackage
from harnesslab.tasks.quality import (
    BenchmarkTier,
    QualificationCheck,
    QualificationEvidence,
    QualificationStatus,
    TaskFamily,
    TaskProvenance,
    TaskQualification,
    TaskQualityError,
    TaskQualityMetadata,
    TaskSourceKind,
    qualify_task,
    unqualified_task,
)
from harnesslab.tasks.splits import (
    DevelopmentExposure,
    SplitFindingCode,
    SplitRole,
    TaskSplitAssignment,
    TaskSplitError,
    evaluate_split,
    freeze_split,
    load_split_freeze,
)

ROOT = Path(__file__).resolve().parents[1]


def _digest(label: str) -> str:
    return canonical_digest({"test-evidence": label})


def _quality(task_id: str, version: str = "1.0.0") -> TaskQualityMetadata:
    package = TaskPackage.load(ROOT / "tasks" / task_id / version)
    return TaskQualityMetadata.from_package(package)


def _evidence(tier: BenchmarkTier, prefix: str) -> tuple[QualificationEvidence, ...]:
    checks = {
        QualificationCheck.PACKAGE_VALID,
        QualificationCheck.BASELINE_FAILS,
        QualificationCheck.ORACLE_PASSES,
        QualificationCheck.DETERMINISTIC_HEALTH,
    }
    if tier is BenchmarkTier.TIER_B:
        checks |= {
            QualificationCheck.FROZEN_REPOSITORY_SNAPSHOT,
            QualificationCheck.WORKSPACE_ISOLATION,
            QualificationCheck.HIDDEN_ASSETS_ISOLATED,
            QualificationCheck.ROBUSTNESS_VARIANTS_FAIL,
            QualificationCheck.FAILURE_BOUNDARIES_VALID,
        }
    return tuple(
        QualificationEvidence(check=check, evidence_identity=_digest(f"{prefix}:{check.value}"))
        for check in sorted(checks, key=lambda item: item.value)
    )


def _qualified(task_id: str, version: str = "1.0.0") -> TaskQualification:
    quality = _quality(task_id, version)
    return qualify_task(
        quality,
        qualification_id=f"qualification-{task_id}-{version.replace('.', '-')}",
        evidence=_evidence(quality.benchmark_tier, task_id),
    )


def test_quality_metadata_distinguishes_tier_a_tier_b_imported_and_custom() -> None:
    core_package = TaskPackage.load(ROOT / "tasks/core-python-deduplicate/1.0.0")
    repo_package = TaskPackage.load(ROOT / "tasks/repo-python-ledger-transfer/1.0.0")

    core = TaskQualityMetadata.from_package(core_package)
    repo = TaskQualityMetadata.from_package(repo_package)
    imported = TaskQualityMetadata.from_package(
        core_package,
        source_kind=TaskSourceKind.IMPORTED,
        source_identity=_digest("upstream-corpus-item"),
        source_revision="upstream-v4",
    )
    custom = TaskQualityMetadata.from_package(
        core_package,
        source_kind=TaskSourceKind.CUSTOM,
        source_identity=_digest("customer-authored-item"),
    )

    assert (core.family, core.benchmark_tier) == (TaskFamily.CORE, BenchmarkTier.TIER_A)
    assert (repo.family, repo.benchmark_tier) == (
        TaskFamily.REPO_ENGINEERING,
        BenchmarkTier.TIER_B,
    )
    assert (imported.family, imported.benchmark_tier) == (
        TaskFamily.IMPORTED,
        BenchmarkTier.UNASSIGNED,
    )
    assert (custom.family, custom.benchmark_tier) == (
        TaskFamily.CUSTOM,
        BenchmarkTier.UNASSIGNED,
    )
    assert core.task.task_id == core_package.definition.id
    assert core.task.task_version == core_package.definition.version
    assert core.task.task_digest == core_package.definition.content_digest


def test_quality_category_invariants_reject_relabeling() -> None:
    core = _quality("core-python-deduplicate")
    with pytest.raises(ValidationError, match="inconsistent"):
        TaskQualityMetadata(
            task=core.task,
            family=TaskFamily.CORE,
            benchmark_tier=BenchmarkTier.TIER_B,
            provenance=core.provenance,
        )


def test_qualification_is_categorical_evidence_bound_and_contains_no_score() -> None:
    core = _quality("core-python-deduplicate")
    qualification = qualify_task(
        core,
        qualification_id="core-qualification-v1",
        evidence=_evidence(core.benchmark_tier, "core"),
    )

    assert qualification.status is QualificationStatus.QUALIFIED
    assert qualification.qualification_identity.startswith("sha256:")
    assert "score" not in json.dumps(qualification.model_dump(mode="json"))

    with pytest.raises(TaskQualityError, match="missing checks"):
        qualify_task(
            core,
            qualification_id="incomplete",
            evidence=(
                QualificationEvidence(
                    check=QualificationCheck.PACKAGE_VALID,
                    evidence_identity=_digest("package-valid-only"),
                ),
            ),
        )


def test_imported_and_custom_tasks_are_not_silently_promoted_to_a_tier() -> None:
    package = TaskPackage.load(ROOT / "tasks/core-python-deduplicate/1.0.0")
    imported = TaskQualityMetadata.from_package(
        package,
        source_kind=TaskSourceKind.IMPORTED,
        source_identity=_digest("imported"),
    )

    assert unqualified_task(imported).status is QualificationStatus.NOT_QUALIFIED
    with pytest.raises(TaskQualityError, match="assigned governed tier"):
        qualify_task(
            imported,
            qualification_id="unsupported-promotion",
            evidence=_evidence(BenchmarkTier.TIER_A, "imported"),
        )


def test_split_freeze_is_deterministic_canonical_and_round_trips(tmp_path: Path) -> None:
    development = TaskSplitAssignment(
        role=SplitRole.DEVELOPMENT,
        qualification=_qualified("core-python-deduplicate"),
        development_exposure=DevelopmentExposure.USED,
    )
    held_out = TaskSplitAssignment(
        role=SplitRole.HELD_OUT,
        qualification=_qualified("core-python-feature-flag"),
        development_exposure=DevelopmentExposure.NOT_USED,
    )

    first = freeze_split("core-python-split-v1", (held_out, development))
    second = freeze_split("core-python-split-v1", (development, held_out))

    assert first == second
    assert first.split_identity == second.split_identity
    assert first.assignments[0].role is SplitRole.DEVELOPMENT
    path = tmp_path / "split.json"
    path.write_text(first.canonical_json(), encoding="utf-8")
    assert load_split_freeze(path) == first

    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["assignments"][1]["development_exposure"] = "UNKNOWN"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(TaskSplitError, match="invalid task split freeze"):
        load_split_freeze(path)


def test_split_checks_exact_identity_task_id_and_provenance_leakage() -> None:
    development_qualification = _qualified("core-python-deduplicate", "1.0.0")
    exact_held_out = TaskSplitAssignment(
        role=SplitRole.HELD_OUT,
        qualification=development_qualification,
        development_exposure=DevelopmentExposure.NOT_USED,
    )
    development = TaskSplitAssignment(
        role=SplitRole.DEVELOPMENT,
        qualification=development_qualification,
        development_exposure=DevelopmentExposure.USED,
    )
    exact_report = evaluate_split((development, exact_held_out))
    exact_codes = {finding.code for finding in exact_report.findings}
    assert SplitFindingCode.TASK_IDENTITY_CROSS_SPLIT in exact_codes
    assert SplitFindingCode.PROVENANCE_CROSS_SPLIT in exact_codes

    later_version = _qualified("core-python-deduplicate", "1.0.1")
    same_id_report = evaluate_split(
        (
            development,
            TaskSplitAssignment(
                role=SplitRole.HELD_OUT,
                qualification=later_version,
                development_exposure=DevelopmentExposure.NOT_USED,
            ),
        )
    )
    assert SplitFindingCode.TASK_ID_CROSS_SPLIT in {
        finding.code for finding in same_id_report.findings
    }

    with pytest.raises(TaskSplitError, match="TASK_IDENTITY_CROSS_SPLIT"):
        freeze_split("leaky", (development, exact_held_out))


def test_held_out_exposure_and_qualification_fail_closed() -> None:
    development = TaskSplitAssignment(
        role=SplitRole.DEVELOPMENT,
        qualification=_qualified("core-python-deduplicate"),
        development_exposure=DevelopmentExposure.USED,
    )
    held_out_quality = _quality("core-python-feature-flag")
    held_out = TaskSplitAssignment(
        role=SplitRole.HELD_OUT,
        qualification=unqualified_task(held_out_quality),
        development_exposure=DevelopmentExposure.UNKNOWN,
    )

    report = evaluate_split((development, held_out))
    codes = {finding.code for finding in report.findings}
    assert codes == {
        SplitFindingCode.HELD_OUT_EXPOSURE_UNKNOWN,
        SplitFindingCode.HELD_OUT_TASK_UNQUALIFIED,
    }


def test_parent_lineage_overlap_blocks_a_nominally_distinct_holdout() -> None:
    development_quality = _quality("core-python-deduplicate")
    held_out_quality = _quality("core-python-feature-flag")
    shared_parent = _digest("shared-generator-or-source-record")
    development_quality = development_quality.model_copy(
        update={
            "provenance": TaskProvenance(
                source_kind=TaskSourceKind.HARNESSLAB,
                source_identity=development_quality.provenance.source_identity,
                parent_identities=(shared_parent,),
            )
        }
    )
    held_out_quality = held_out_quality.model_copy(
        update={
            "provenance": TaskProvenance(
                source_kind=TaskSourceKind.HARNESSLAB,
                source_identity=held_out_quality.provenance.source_identity,
                parent_identities=(shared_parent,),
            )
        }
    )
    development = TaskSplitAssignment(
        role=SplitRole.DEVELOPMENT,
        qualification=qualify_task(
            development_quality,
            qualification_id="development-qualified",
            evidence=_evidence(BenchmarkTier.TIER_A, "development"),
        ),
        development_exposure=DevelopmentExposure.USED,
    )
    held_out = TaskSplitAssignment(
        role=SplitRole.HELD_OUT,
        qualification=qualify_task(
            held_out_quality,
            qualification_id="held-out-qualified",
            evidence=_evidence(BenchmarkTier.TIER_A, "held-out"),
        ),
        development_exposure=DevelopmentExposure.NOT_USED,
    )

    report = evaluate_split((development, held_out))
    assert [finding.code for finding in report.findings] == [
        SplitFindingCode.PROVENANCE_CROSS_SPLIT
    ]
