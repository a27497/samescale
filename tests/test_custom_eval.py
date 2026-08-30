from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from typer.testing import CliRunner

from harnesslab.api.app import create_app
from harnesslab.cli import app
from harnesslab.custom_eval.api import custom_task_store
from harnesslab.custom_eval.builder import CustomTaskBuilder
from harnesslab.custom_eval.evaluation import (
    build_custom_plan,
    build_custom_report,
    evaluate_criteria,
)
from harnesslab.custom_eval.models import (
    CriterionEvidence,
    CriterionKind,
    CriterionStatus,
    CustomEvaluationPreset,
    CustomPlanRequest,
    CustomRunEvidence,
    CustomTarget,
    CustomTaskBuilderSpec,
    EvaluationCriterion,
    SourceType,
)
from harnesslab.custom_eval.store import ManagedTaskStore, ManagedTaskStoreError
from harnesslab.experiment.spec import ExperimentSpec
from harnesslab.tasks.package import TaskPackage, digest_tree

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PACKAGE = ROOT / "tasks/micro-python-clamp/1.0.0"
runner = CliRunner()


def copy_package(root: Path) -> Path:
    package = root / "micro-python-clamp" / "1.0.0"
    shutil.copytree(SOURCE_PACKAGE, package)
    return package


def plan_request(preset: CustomEvaluationPreset) -> CustomPlanRequest:
    return CustomPlanRequest(
        evaluation_id=f"custom-{preset.value.lower()}",
        name=f"Custom {preset.value}",
        preset=preset,
        task_references=("micro-python-clamp@1.0.0",),
        targets=(
            CustomTarget(
                id="model-harness",
                requested_model="example-model",
                harness="example-harness",
                harness_version="1.2.3",
            ),
        ),
    )


def pass_evidence(slot_id: str, *, cost: float | None = None) -> CustomRunEvidence:
    return CustomRunEvidence(
        slot_id=slot_id,
        criteria=(
            CriterionEvidence(
                criterion_id="hidden-verifier",
                status=CriterionStatus.PASS,
                evidence_identity="sha256:" + "1" * 64,
            ),
        ),
        cost=cost,
        trace_identity="sha256:" + "2" * 64,
    )


def git(*arguments: str, cwd: Path) -> str:
    result = subprocess.run(
        ("git", *arguments),
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def test_local_folder_and_prepared_package_imports_freeze_provenance(tmp_path: Path) -> None:
    source = copy_package(tmp_path / "source")
    folder = ManagedTaskStore(tmp_path / "folder-store").import_local_folder(
        source, owner="team-a", category="repair"
    )
    prepared = ManagedTaskStore(tmp_path / "prepared-store").import_prepared_package(
        source, owner="team-a", category="repair"
    )

    assert folder.provenance.source_type is SourceType.LOCAL_FOLDER
    assert prepared.provenance.source_type is SourceType.PREPARED_PACKAGE
    assert folder.namespace.value == "CUSTOM"
    assert folder.task_owner == "team-a"
    assert folder.task_category == "repair"
    assert folder.provenance.source_content_identity == folder.task_identity
    assert folder.managed_snapshot_identity == prepared.managed_snapshot_identity


def test_local_repository_import_records_head_without_mutating_repo(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    source = copy_package(repository / "packages")
    git("init", "--quiet", cwd=repository)
    git("config", "user.email", "offline@example.invalid", cwd=repository)
    git("config", "user.name", "Offline Fixture", cwd=repository)
    git("add", ".", cwd=repository)
    git("commit", "--quiet", "-m", "fixture", cwd=repository)
    head = git("rev-parse", "HEAD", cwd=repository)
    before = digest_tree(source)

    record = ManagedTaskStore(tmp_path / "store").import_local_repository(
        repository,
        "packages/micro-python-clamp/1.0.0",
        owner="fixture-owner",
        category="fixture",
    )

    assert record.provenance.source_type is SourceType.LOCAL_REPOSITORY
    assert record.provenance.source_commit == head
    assert digest_tree(source) == before


def test_exact_local_git_commit_import_is_offline_and_exact(tmp_path: Path) -> None:
    repository = tmp_path / "git-source"
    copy_package(repository / "packages")
    git("init", "--quiet", cwd=repository)
    git("config", "user.email", "offline@example.invalid", cwd=repository)
    git("config", "user.name", "Offline Fixture", cwd=repository)
    git("add", ".", cwd=repository)
    git("commit", "--quiet", "-m", "fixture", cwd=repository)
    commit = git("rev-parse", "HEAD", cwd=repository)

    record = ManagedTaskStore(tmp_path / "store").import_git_exact_commit(
        str(repository),
        commit,
        "packages/micro-python-clamp/1.0.0",
        owner="fixture-owner",
        category="fixture",
    )

    assert record.provenance.source_type is SourceType.GIT_EXACT_COMMIT
    assert record.provenance.source_commit == commit
    with pytest.raises(ManagedTaskStoreError, match="exact lowercase"):
        ManagedTaskStore(tmp_path / "other-store").import_git_exact_commit(
            str(repository), "HEAD", "packages/micro-python-clamp/1.0.0"
        )


def test_remote_git_is_denied_by_default_and_always_denied_in_ci(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ManagedTaskStoreError, match="remote git fetch is disabled"):
        ManagedTaskStore._safe_git_source(
            "https://example.invalid/task.git", allow_remote_git=False
        )
    monkeypatch.setenv("CI", "true")
    with pytest.raises(ManagedTaskStoreError, match="disabled in CI"):
        ManagedTaskStore._safe_git_source("https://example.invalid/task.git", allow_remote_git=True)
    assert (
        ManagedTaskStore._git_reference(
            "https://literal-secret@example.invalid/task.git?token=literal-secret"
        )
        == "https://example.invalid/task.git"
    )


def test_path_traversal_and_symlink_escape_are_rejected(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / ".git").mkdir()
    store = ManagedTaskStore(tmp_path / "store")
    with pytest.raises(ManagedTaskStoreError, match="subpath is unsafe"):
        store.import_local_repository(repository, "../outside")

    package = copy_package(tmp_path / "linked")
    (package / "workspace/escape").symlink_to(tmp_path / "outside")
    with pytest.raises(ManagedTaskStoreError, match="links and junctions"):
        store.import_local_folder(package)


def test_invalid_and_malicious_task_packages_fail_before_storage(tmp_path: Path) -> None:
    package = copy_package(tmp_path / "invalid")
    manifest = package / "task.yaml"
    manifest.write_text(manifest.read_text(encoding="utf-8") + "id: duplicate\n", encoding="utf-8")
    store = ManagedTaskStore(tmp_path / "store")

    with pytest.raises(ManagedTaskStoreError, match="invalid task package"):
        store.import_prepared_package(package)
    assert store.list() == ()


def test_hidden_verifier_and_oracle_never_enter_subject_materialization(tmp_path: Path) -> None:
    source = copy_package(tmp_path / "source")
    store = ManagedTaskStore(tmp_path / "store")
    record = store.import_local_folder(source)
    _record, package = store.load_package(record.reference)

    materialized = package.materialize(tmp_path / "runs")
    try:
        assert {path.name for path in materialized.root.iterdir()} <= {"workspace", "context"}
        assert not (materialized.workspace / "verifier").exists()
        assert not (materialized.workspace / "oracle").exists()
    finally:
        materialized.cleanup()


def test_duplicate_identity_is_idempotent_and_conflicts_fail_closed(tmp_path: Path) -> None:
    source = copy_package(tmp_path / "source")
    store = ManagedTaskStore(tmp_path / "store")
    first = store.import_local_folder(source, owner="owner", category="category")
    second = store.import_local_folder(source, owner="owner", category="category")
    assert first == second
    assert len(store.list()) == 1

    changed = copy_package(tmp_path / "changed")
    (changed / "workspace/calculator.py").write_text("CHANGED = True\n", encoding="utf-8")
    with pytest.raises(ManagedTaskStoreError, match="different immutable snapshot"):
        store.import_local_folder(changed, owner="owner", category="category")


def test_snapshot_identity_drift_is_detected_and_cannot_be_consumed(tmp_path: Path) -> None:
    source = copy_package(tmp_path / "source")
    store = ManagedTaskStore(tmp_path / "store")
    record = store.import_local_folder(source)
    workspace_file = store.package_path(record) / "workspace/calculator.py"

    workspace_file.write_text("tampered = True\n", encoding="utf-8")
    with pytest.raises(
        ManagedTaskStoreError, match=r"integrity validation failed|content identity changed"
    ):
        store.inspect(record.reference)


def test_official_corpus_freezes_and_qualification_inputs_are_unchanged(tmp_path: Path) -> None:
    official_tasks_before = digest_tree(ROOT / "tasks")
    release_before = digest_tree(ROOT / "release")
    source = copy_package(tmp_path / "source")
    store = ManagedTaskStore(tmp_path / "managed")
    record = store.import_local_folder(source)
    plan = build_custom_plan(plan_request(CustomEvaluationPreset.QUICK), store)

    assert plan.namespace.value == "CUSTOM"
    assert not plan.official_benchmark_eligible
    assert plan.tasks[0].managed_snapshot_identity == record.managed_snapshot_identity
    assert digest_tree(ROOT / "tasks") == official_tasks_before
    assert digest_tree(ROOT / "release") == release_before
    with pytest.raises(ValueError, match="task packages must live below tasks"):
        ExperimentSpec.model_validate(
            {
                "experiment_id": "bad-official-plan",
                "name": "Bad",
                "task_packages": ("managed/custom/1.0.0",),
                "cells": ({"not": "relevant"},),
            }
        )


def test_store_rejects_official_task_and_release_locations(tmp_path: Path) -> None:
    for protected in (ROOT / "tasks/custom-store", ROOT / "release/custom-store"):
        with pytest.raises(ManagedTaskStoreError, match="Official namespace"):
            ManagedTaskStore(protected)


@pytest.mark.parametrize(
    ("preset", "repeats"),
    [
        (CustomEvaluationPreset.QUICK, 1),
        (CustomEvaluationPreset.COMPARE, 3),
        (CustomEvaluationPreset.FORMAL, 5),
    ],
)
def test_presets_reuse_canonical_methodology_repeat_counts(
    tmp_path: Path, preset: CustomEvaluationPreset, repeats: int
) -> None:
    source = copy_package(tmp_path / preset.value)
    store = ManagedTaskStore(tmp_path / f"store-{preset.value}")
    store.import_local_folder(source)

    plan = build_custom_plan(plan_request(preset), store)

    assert plan.repeat_count == repeats == preset.evaluation_mode.repeat_count
    assert len(plan.run_slots) == repeats
    assert {slot.repeat_index for slot in plan.run_slots} == set(range(repeats))


def test_deterministic_l0_failure_has_authority_over_judge_pass() -> None:
    criteria = (
        EvaluationCriterion(
            id="contract",
            kind=CriterionKind.CONTRACT_CHECK,
            description="Required deterministic contract.",
        ),
        EvaluationCriterion(
            id="judge",
            kind=CriterionKind.JUDGE_RUBRIC,
            description="Optional qualitative check.",
            required=False,
            rubric="Assess clarity.",
        ),
    )
    decision = evaluate_criteria(
        criteria,
        (
            CriterionEvidence(criterion_id="contract", status=CriterionStatus.FAIL),
            CriterionEvidence(criterion_id="judge", status=CriterionStatus.PASS),
        ),
    )

    assert decision.status is CriterionStatus.FAIL
    assert decision.deterministic_l0_failed
    assert decision.reason_codes == ("L0_FAIL:contract",)


def test_report_discloses_outcomes_cost_trace_and_n1_limits(tmp_path: Path) -> None:
    source = copy_package(tmp_path / "source")
    store = ManagedTaskStore(tmp_path / "store")
    store.import_local_folder(source)
    plan = build_custom_plan(plan_request(CustomEvaluationPreset.QUICK), store)
    report = build_custom_report(
        plan,
        (pass_evidence(plan.run_slots[0].slot_id, cost=0.25),),
    )

    target = report.targets[0]
    assert target.capability_passes == 1
    assert target.pass_rate == 1.0
    assert target.cost_availability == "AVAILABLE"
    assert target.total_cost == 0.25
    assert target.trace_availability == "AVAILABLE"
    assert not report.universal_model_claim_allowed
    assert any("n=1" in limit for limit in report.comparability_limits)
    assert report.missing_treatment == "EXCLUDED_FROM_CAPABILITY_DENOMINATOR"
    assert report.infrastructure_treatment == "EXCLUDED_AND_REPORTED_SEPARATELY"


def test_report_separates_infrastructure_and_missing_from_capability(tmp_path: Path) -> None:
    source = copy_package(tmp_path / "source")
    store = ManagedTaskStore(tmp_path / "store")
    store.import_local_folder(source)
    plan = build_custom_plan(plan_request(CustomEvaluationPreset.COMPARE), store)
    evidence = (
        pass_evidence(plan.run_slots[0].slot_id),
        CustomRunEvidence(slot_id=plan.run_slots[1].slot_id, infrastructure_failure=True),
    )

    target = build_custom_report(plan, evidence).targets[0]

    assert target.planned_runs == 3
    assert target.capability_passes == 1
    assert target.capability_failures == 0
    assert target.infrastructure_failures == 1
    assert target.missing_runs == 1
    assert target.pass_rate == 1.0


def test_builder_creates_structurally_validated_managed_package(tmp_path: Path) -> None:
    spec = CustomTaskBuilderSpec(
        task_id="built-custom-task",
        version="1.2.3",
        domain="software-engineering",
        owner="builder-owner",
        category="contract",
        instruction_source=str(SOURCE_PACKAGE / "instruction.md"),
        workspace_source=str(SOURCE_PACKAGE / "workspace"),
        verifier_source=str(SOURCE_PACKAGE / "verifier"),
        oracle_source=str(SOURCE_PACKAGE / "oracle"),
        protected_paths=("public_check.py",),
        criteria=(
            EvaluationCriterion(
                id="build",
                kind=CriterionKind.BUILD,
                description="Project builds successfully.",
            ),
            EvaluationCriterion(
                id="performance",
                kind=CriterionKind.PERFORMANCE_THRESHOLD,
                description="Completes within the threshold.",
                threshold=250.0,
                unit="milliseconds",
            ),
        ),
    )

    built = CustomTaskBuilder().build(spec, tmp_path / "output")
    package = TaskPackage.load(built.path)
    record = ManagedTaskStore(tmp_path / "store").import_prepared_package(built.path)

    assert built.structurally_validated
    assert package.definition.id == "built-custom-task"
    assert record.task_owner == "builder-owner"
    assert {criterion.kind for criterion in record.criteria} == {
        CriterionKind.BUILD,
        CriterionKind.PERFORMANCE_THRESHOLD,
    }


def test_cli_management_import_list_inspect_validate_and_plan(tmp_path: Path) -> None:
    source = copy_package(tmp_path / "source")
    store_root = tmp_path / "store"
    imported = runner.invoke(
        app,
        [
            "custom-eval",
            "import",
            str(source),
            "--source-type",
            "local_folder",
            "--store",
            str(store_root),
        ],
    )
    assert imported.exit_code == 0, imported.stdout
    assert json.loads(imported.stdout)["namespace"] == "CUSTOM"

    listed = runner.invoke(app, ["custom-eval", "list", "--store", str(store_root)])
    inspected = runner.invoke(
        app,
        [
            "custom-eval",
            "inspect",
            "micro-python-clamp@1.0.0",
            "--store",
            str(store_root),
        ],
    )
    validated = runner.invoke(
        app,
        [
            "custom-eval",
            "validate",
            "micro-python-clamp@1.0.0",
            "--store",
            str(store_root),
        ],
    )
    request_path = tmp_path / "plan.json"
    request_path.write_text(plan_request(CustomEvaluationPreset.QUICK).model_dump_json())
    planned = runner.invoke(
        app,
        ["custom-eval", "plan", str(request_path), "--store", str(store_root)],
    )

    assert len(json.loads(listed.stdout)) == 1
    assert json.loads(inspected.stdout)["task_id"] == "micro-python-clamp"
    assert json.loads(validated.stdout)["behavioral_validation"] == "NOT_RUN"
    assert json.loads(planned.stdout)["repeat_count"] == 1


async def test_api_management_operations_are_keyless(tmp_path: Path) -> None:
    source = copy_package(tmp_path / "source")
    store = ManagedTaskStore(tmp_path / "store")
    application = create_app()
    application.dependency_overrides[custom_task_store] = lambda: store
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        imported = await client.post(
            "/api/custom-eval/imports",
            json={"source_type": "local_folder", "source": str(source)},
        )
        listed = await client.get("/api/custom-eval/tasks")
        inspected = await client.get("/api/custom-eval/tasks/micro-python-clamp/1.0.0")
        validated = await client.post("/api/custom-eval/validate/micro-python-clamp/1.0.0")
        planned = await client.post(
            "/api/custom-eval/plan",
            json=plan_request(CustomEvaluationPreset.QUICK).model_dump(mode="json"),
        )
        plan = planned.json()
        evidence = [
            pass_evidence(plan["run_slots"][0]["slot_id"], cost=0.1).model_dump(mode="json")
        ]
        reported = await client.post(
            "/api/custom-eval/report", json={"plan": plan, "evidence": evidence}
        )

    assert imported.status_code == 200
    assert len(listed.json()) == 1
    assert inspected.json()["namespace"] == "CUSTOM"
    assert validated.json() == {
        "reference": "micro-python-clamp@1.0.0",
        "snapshot_integrity": "PASS",
        "behavioral_validation": "NOT_RUN",
        "provider_calls": 0,
        "judge_calls": 0,
    }
    assert planned.status_code == 200
    assert reported.status_code == 200
    assert reported.json()["targets"][0]["capability_passes"] == 1


def test_planning_and_reporting_never_call_provider_or_judge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = copy_package(tmp_path / "source")
    store = ManagedTaskStore(tmp_path / "store")
    store.import_local_folder(source)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("provider/Judge execution is forbidden in custom evaluation foundation")

    monkeypatch.setattr("harnesslab.model_lane.runner.DirectModelRunner.run", forbidden)
    monkeypatch.setattr("harnesslab.judgelab.runner.JudgeRunner.run", forbidden)
    plan = build_custom_plan(plan_request(CustomEvaluationPreset.QUICK), store)
    report = build_custom_report(plan, (pass_evidence(plan.run_slots[0].slot_id),))

    assert report.targets[0].capability_passes == 1
