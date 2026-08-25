from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.run import RunStatus
from harnesslab.experiment.outcomes import (
    StatisticalOutcome,
    terminal_status_for_outcome,
    validate_terminal_run_lifecycle,
)
from harnesslab.harness_lane.models import HarnessLaneOutcome
from harnesslab.model_lane.models import DirectModelOutcome
from harnesslab.release.contracts import (
    CoreReleaseError,
    build_corpus_manifest,
    tag_creation_authorized,
)
from harnesslab.release.final_verifier import (
    _resolve_snapshot_in_session,
    verify_semantic_final_release,
)
from harnesslab.release.models import (
    CoreCorpusManifest,
    EvidenceBinding,
    EvidenceState,
    ResumeClaimMap,
)
from tests.release_semantic_fixture import semantic_fixture

ROOT = Path(__file__).resolve().parents[1]


def _verify(fixture: dict[str, Any]) -> Any:
    return verify_semantic_final_release(**fixture)


def test_phase_g_lifecycle_accepts_completed_capability_pass() -> None:
    validate_terminal_run_lifecycle(RunStatus.COMPLETED, StatisticalOutcome.CAPABILITY_PASS)
    assert terminal_status_for_outcome(StatisticalOutcome.CAPABILITY_PASS) is RunStatus.COMPLETED


def test_phase_g_lifecycle_accepts_failed_subject_capability_fail() -> None:
    validate_terminal_run_lifecycle(RunStatus.FAILED_SUBJECT, StatisticalOutcome.CAPABILITY_FAIL)
    assert (
        terminal_status_for_outcome(StatisticalOutcome.CAPABILITY_FAIL) is RunStatus.FAILED_SUBJECT
    )


def test_phase_g_lifecycle_accepts_failed_infra_infra_failure() -> None:
    validate_terminal_run_lifecycle(RunStatus.FAILED_INFRA, StatisticalOutcome.INFRA_FAILURE)
    assert terminal_status_for_outcome(StatisticalOutcome.INFRA_FAILURE) is RunStatus.FAILED_INFRA


def test_phase_g_lifecycle_accepts_cancelled_cancelled() -> None:
    validate_terminal_run_lifecycle(RunStatus.CANCELLED, StatisticalOutcome.CANCELLED)
    assert terminal_status_for_outcome(StatisticalOutcome.CANCELLED) is RunStatus.CANCELLED


def test_phase_g_lifecycle_rejects_completed_capability_fail() -> None:
    with pytest.raises(ValueError, match="inconsistent terminal run lifecycle"):
        validate_terminal_run_lifecycle(RunStatus.COMPLETED, StatisticalOutcome.CAPABILITY_FAIL)


def test_phase_g_lifecycle_rejects_failed_subject_capability_pass() -> None:
    with pytest.raises(ValueError, match="inconsistent terminal run lifecycle"):
        validate_terminal_run_lifecycle(
            RunStatus.FAILED_SUBJECT, StatisticalOutcome.CAPABILITY_PASS
        )


def test_phase_g_lifecycle_rejects_failed_infra_capability_pass() -> None:
    with pytest.raises(ValueError, match="inconsistent terminal run lifecycle"):
        validate_terminal_run_lifecycle(RunStatus.FAILED_INFRA, StatisticalOutcome.CAPABILITY_PASS)


def test_phase_g_lifecycle_rejects_cancelled_capability_fail() -> None:
    with pytest.raises(ValueError, match="inconsistent terminal run lifecycle"):
        validate_terminal_run_lifecycle(RunStatus.CANCELLED, StatisticalOutcome.CAPABILITY_FAIL)


def test_corpus_has_sixteen_semantic_families_and_one_cross_language_control() -> None:
    corpus = build_corpus_manifest(ROOT)
    controls = [item for item in corpus.tasks if item.benchmark_role == "CROSS_LANGUAGE_CONTROL"]
    independent = [item for item in corpus.tasks if item.benchmark_role == "INDEPENDENT"]

    assert len({item.scenario_family for item in corpus.tasks}) == 16
    assert len(controls) == 3
    assert {item.language for item in controls} == {"python", "java", "typescript"}
    assert len({item.scenario_family for item in controls}) == 1
    assert len(independent) == 15
    assert len({item.scenario_family for item in independent}) == 15


def test_corpus_rejects_duplicate_independent_scenario_family() -> None:
    corpus = build_corpus_manifest(ROOT)
    raw = corpus.model_dump(mode="json")
    independent = [
        index for index, item in enumerate(raw["tasks"]) if item["benchmark_role"] == "INDEPENDENT"
    ]
    raw["tasks"][independent[1]]["scenario_family"] = raw["tasks"][independent[0]][
        "scenario_family"
    ]

    with pytest.raises(ValidationError, match="unique scenario family"):
        CoreCorpusManifest.model_validate(raw)


def test_corpus_reconstruction_detects_semantic_metadata_drift(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    shutil.copytree(ROOT / "tasks", repository / "tasks")
    task = repository / "tasks/core-python-deduplicate/1.0.0/task.yaml"
    task.write_text(
        task.read_text(encoding="utf-8").replace(
            "scenario_family: retry-ledger-idempotency",
            "scenario_family: retry-ledger-idempotency-drift",
        ),
        encoding="utf-8",
    )

    assert build_corpus_manifest(repository) != build_corpus_manifest(ROOT)


def test_final_release_rejects_arbitrary_matching_sha_artifact() -> None:
    fixture = semantic_fixture()
    arbitrary = canonical_digest({"arbitrary_file_with_matching_sha": True})
    binding = EvidenceBinding(
        state=EvidenceState.VERIFIED,
        identity=f"experiment-report:{fixture['snapshot'].experiment.experiment_id}",
        digest=arbitrary,
    )
    fixture["manifest"] = fixture["manifest"].model_copy(update={"real_matrix": binding})

    with pytest.raises(CoreReleaseError, match="real_matrix"):
        _verify(fixture)


@pytest.mark.asyncio
async def test_final_release_rejects_postgresql_select_one_without_experiment() -> None:
    class EmptySession:
        async def get(self, model: object, identity: str) -> None:
            return None

    with pytest.raises(CoreReleaseError, match="experiment record does not exist"):
        await _resolve_snapshot_in_session(
            EmptySession(),  # type: ignore[arg-type]
            (ROOT / "artifacts",),
            experiment_id="core-real-matrix-v2",
            calibration_id="core-real-judge-v2",
        )


def test_final_release_rejects_wrong_experiment_plan_digest() -> None:
    fixture = semantic_fixture()
    experiment = fixture["snapshot"].experiment.model_copy(
        update={"report_plan_digest": canonical_digest({"wrong": "plan"})}
    )
    fixture["snapshot"] = fixture["snapshot"].model_copy(update={"experiment": experiment})

    with pytest.raises(CoreReleaseError, match="Report identity or plan binding"):
        _verify(fixture)


def test_final_release_rejects_wrong_experiment_corpus() -> None:
    fixture = semantic_fixture()
    experiment = fixture["snapshot"].experiment
    first = experiment.plan.tasks[0].model_copy(
        update={"task_digest": canonical_digest({"wrong": "task"})}
    )
    plan = experiment.plan.model_copy(update={"tasks": (first, *experiment.plan.tasks[1:])})
    fixture["snapshot"] = fixture["snapshot"].model_copy(
        update={"experiment": experiment.model_copy(update={"plan": plan})}
    )

    with pytest.raises(CoreReleaseError, match="wrong Core corpus"):
        _verify(fixture)


def test_final_release_rejects_629_runs() -> None:
    fixture = semantic_fixture()
    experiment = fixture["snapshot"].experiment.model_copy(
        update={"runs": fixture["snapshot"].experiment.runs[:-1]}
    )
    fixture["snapshot"] = fixture["snapshot"].model_copy(update={"experiment": experiment})

    with pytest.raises(CoreReleaseError, match="exact 630 slots"):
        _verify(fixture)


def test_final_release_rejects_corrupt_run_manifest_set() -> None:
    fixture = semantic_fixture()
    experiment = fixture["snapshot"].experiment.model_copy(
        update={"authoritative_loader_verified": False}
    )
    fixture["snapshot"] = fixture["snapshot"].model_copy(update={"experiment": experiment})

    with pytest.raises(CoreReleaseError, match="authoritative manifest loader"):
        _verify(fixture)


def test_final_release_accepts_production_valid_capability_failure() -> None:
    fixture = semantic_fixture()
    failed = fixture["snapshot"].experiment.runs[0]

    assert failed.status is RunStatus.FAILED_SUBJECT
    assert failed.normalized_outcome is StatisticalOutcome.CAPABILITY_FAIL
    assert _verify(fixture).semantic_verified


def test_final_release_rejects_inconsistent_run_lifecycle() -> None:
    fixture = semantic_fixture()
    experiment = fixture["snapshot"].experiment
    runs = list(experiment.runs)
    runs[10] = runs[10].model_copy(
        update={
            "status": RunStatus.COMPLETED,
            "normalized_outcome": StatisticalOutcome.CAPABILITY_FAIL,
            "source_outcome": DirectModelOutcome.VERIFIED_FAIL.value,
        }
    )
    fixture["snapshot"] = fixture["snapshot"].model_copy(
        update={"experiment": experiment.model_copy(update={"runs": tuple(runs)})}
    )

    with pytest.raises(CoreReleaseError, match="lifecycle disagrees with Phase G"):
        _verify(fixture)


def test_final_release_accepts_infra_and_cancelled_without_artifact_identity() -> None:
    fixture = semantic_fixture()
    experiment = fixture["snapshot"].experiment
    formal_cells = {
        experiment.pair.left_cell_id,
        experiment.pair.right_cell_id,
        experiment.ablation.base_cell_id,
        experiment.ablation.variant_cell_id,
    }
    candidates = [
        index
        for index, run in enumerate(experiment.runs)
        if index >= 3 and run.cell_id not in formal_cells
    ]
    assert len(candidates) >= 2
    runs = list(experiment.runs)
    replacements = (
        (
            RunStatus.FAILED_INFRA,
            StatisticalOutcome.INFRA_FAILURE,
            HarnessLaneOutcome.INFRA_ERROR.value,
        ),
        (RunStatus.CANCELLED, StatisticalOutcome.CANCELLED, "cancellation_requested"),
    )
    for index, (status, outcome, source) in zip(candidates[:2], replacements, strict=True):
        runs[index] = runs[index].model_copy(
            update={
                "status": status,
                "normalized_outcome": outcome,
                "source_outcome": source,
                "evidence_digest": None,
                "safe_trace_available": False,
                "normalized_trace_digest": None,
                "safe_trace_facts": (),
            }
        )
    fixture["snapshot"] = fixture["snapshot"].model_copy(
        update={"experiment": experiment.model_copy(update={"runs": tuple(runs)})}
    )

    assert _verify(fixture).semantic_verified


def test_final_release_rejects_fake_pair_evidence() -> None:
    fixture = semantic_fixture()
    pair = fixture["snapshot"].experiment.pair.model_copy(update={"total_observations": 89})
    experiment = fixture["snapshot"].experiment.model_copy(update={"pair": pair})
    fixture["snapshot"] = fixture["snapshot"].model_copy(update={"experiment": experiment})

    with pytest.raises(CoreReleaseError, match="paired lane"):
        _verify(fixture)


def test_final_release_rejects_ablation_hard_control_drift() -> None:
    fixture = semantic_fixture()
    experiment = fixture["snapshot"].experiment
    cells = list(experiment.plan.cells)
    variant_id = experiment.ablation.variant_cell_id
    cells = [
        cell.model_copy(update={"profile_reference": "builtin:drift"})
        if cell.id == variant_id
        else cell
        for cell in cells
    ]
    plan = experiment.plan.model_copy(update={"cells": tuple(cells)})
    experiment = experiment.model_copy(update={"plan": plan, "report_plan_digest": plan.digest})
    fixture["snapshot"] = fixture["snapshot"].model_copy(update={"experiment": experiment})
    plan_binding = EvidenceBinding(
        state=EvidenceState.VERIFIED,
        identity=f"experiment-plan:{plan.experiment_id}",
        digest=plan.digest,
    )
    fixture["manifest"] = fixture["manifest"].model_copy(update={"experiment_plan": plan_binding})

    with pytest.raises(CoreReleaseError, match="hard-control drift"):
        _verify(fixture)


def test_final_release_rejects_corrupt_judge_report() -> None:
    fixture = semantic_fixture()
    judge = fixture["snapshot"].judge.model_copy(update={"authoritative_report_verified": False})
    fixture["snapshot"] = fixture["snapshot"].model_copy(update={"judge": judge})

    with pytest.raises(CoreReleaseError, match="authoritative report verification"):
        _verify(fixture)


def test_final_release_rejects_badcase_bound_to_wrong_run() -> None:
    fixture = semantic_fixture()
    slots = list(fixture["badcases"].slots)
    slots[0] = slots[0].model_copy(update={"run_identity": "run:does-not-exist"})
    fixture["badcases"] = fixture["badcases"].model_copy(update={"slots": tuple(slots)})

    with pytest.raises(CoreReleaseError, match="references the wrong run"):
        _verify(fixture)


def test_final_release_rejects_capability_pass_badcase() -> None:
    fixture = semantic_fixture()
    experiment = fixture["snapshot"].experiment
    runs = list(experiment.runs)
    runs[0] = runs[0].model_copy(
        update={
            "status": RunStatus.COMPLETED,
            "normalized_outcome": StatisticalOutcome.CAPABILITY_PASS,
            "source_outcome": DirectModelOutcome.VERIFIED_PASS.value,
        }
    )
    fixture["snapshot"] = fixture["snapshot"].model_copy(
        update={"experiment": experiment.model_copy(update={"runs": tuple(runs)})}
    )

    with pytest.raises(CoreReleaseError, match="not a verifier-backed capability failure"):
        _verify(fixture)


def test_final_release_rejects_unsupported_real_resume_claim() -> None:
    fixture = semantic_fixture()
    claims = list(fixture["claims"].claims)
    index = next(i for i, claim in enumerate(claims) if claim.claim_id == "real-matrix-results")
    claims[index] = claims[index].model_copy(update={"evidence_refs": ("artifact:forged.json",)})
    claim_map = ResumeClaimMap(claims=tuple(claims))
    fixture["claims"] = claim_map
    binding = EvidenceBinding(
        state=EvidenceState.VERIFIED,
        identity="release/resume-claim-evidence.json",
        digest=claim_map.digest,
    )
    fixture["manifest"] = fixture["manifest"].model_copy(update={"resume_claim_map": binding})

    with pytest.raises(CoreReleaseError, match="real release claims"):
        _verify(fixture)


def test_final_release_rejects_remote_ci_head_or_workflow_mismatch() -> None:
    fixture = semantic_fixture()
    ci = fixture["ci"].model_copy(update={"workflow_name": "untrusted workflow"})
    fixture["ci"] = ci
    binding = EvidenceBinding(
        state=EvidenceState.VERIFIED,
        identity=f"github-actions:{ci.run_id}",
        digest=ci.digest,
    )
    fixture["manifest"] = fixture["manifest"].model_copy(update={"remote_ci": binding})

    with pytest.raises(CoreReleaseError, match="exact-head Gates A-K"):
        _verify(fixture)


def test_fully_valid_fake_semantic_fixture_passes_and_issues_receipt() -> None:
    fixture = semantic_fixture()
    badcase_runs = fixture["snapshot"].experiment.runs[:3]
    assert all(run.status is RunStatus.FAILED_SUBJECT for run in badcase_runs)
    assert all(run.normalized_outcome is StatisticalOutcome.CAPABILITY_FAIL for run in badcase_runs)
    assert all(
        run.status is RunStatus.COMPLETED
        and run.normalized_outcome is StatisticalOutcome.CAPABILITY_PASS
        for run in fixture["snapshot"].experiment.runs[3:]
    )
    assert not tag_creation_authorized(fixture["manifest"])
    receipt = _verify(fixture)

    assert receipt.semantic_verified
    assert receipt.release_manifest_digest == fixture["manifest"].digest
    assert tag_creation_authorized(fixture["manifest"], receipt)
