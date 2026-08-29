from __future__ import annotations

import json
from pathlib import Path

from harnesslab.experiment.methodology import load_evaluation_methodology
from harnesslab.registry.seeds import build_registry_catalog
from harnesslab.release.contracts import discover_task_packages
from harnesslab.sandbox.models import (
    SandboxStatus,
    VerifierFailureSubtype,
    VerifierLifecycleStage,
)
from harnesslab.sandbox.runner import DockerSandbox
from harnesslab.tasks.package import TaskPackage

ROOT = Path(__file__).resolve().parents[1]


def _items(path: Path) -> dict[str, dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {item["task_id"]: item for item in payload["tasks"]}


def test_tier_a_versions_are_additive_explicit_and_historically_immutable() -> None:
    methodology = load_evaluation_methodology(ROOT / "release/evaluation-methodology-v2.json")
    tier_a = next(
        item for item in methodology.task_tiers if item.tier.value == "TIER_A_MICRO_CONTRACT"
    )
    historical = _items(ROOT / "release/core-corpus.json")
    repaired_v1 = _items(ROOT / "release/tier-a-verifier-robustness-v1.json")
    repaired_v2 = _items(ROOT / "release/tier-a-verifier-robustness-v2.json")

    assert set(historical) == set(repaired_v1) == set(repaired_v2) == set(tier_a.current_task_ids)
    assert len(discover_task_packages(ROOT)) == 18
    assert len(discover_task_packages(ROOT, task_version="1.0.1")) == 18
    assert len(discover_task_packages(ROOT, task_version="1.0.2")) == 18

    for task_id in tier_a.current_task_ids:
        old = TaskPackage.load(ROOT / str(historical[task_id]["package_path"]))
        v1 = TaskPackage.load(ROOT / str(repaired_v1[task_id]["package_path"]))
        v2 = TaskPackage.load(ROOT / str(repaired_v2[task_id]["package_path"]))
        assert (old.definition.version, v1.definition.version, v2.definition.version) == (
            "1.0.0",
            "1.0.1",
            "1.0.2",
        )
        assert old.definition.content_digest == historical[task_id]["task_digest"]
        assert old.verifier_digest == historical[task_id]["verifier_identity"]
        assert v1.definition.content_digest == repaired_v1[task_id]["task_digest"]
        assert v1.verifier_digest == repaired_v1[task_id]["verifier_identity"]
        assert v2.definition.content_digest == repaired_v2[task_id]["task_digest"]
        assert v2.verifier_digest == repaired_v2[task_id]["verifier_identity"]


def test_registry_resolves_repaired_versions_without_removing_historical_packages() -> None:
    catalog = build_registry_catalog(ROOT, {})

    assert len(catalog.tasks) == 18
    assert {task.task_version for task in catalog.tasks} == {"1.0.2"}
    assert all(task.package_path.endswith("/1.0.2") for task in catalog.tasks)
    assert all(
        (ROOT / "tasks" / task.task_id / "1.0.0" / "task.yaml").is_file() for task in catalog.tasks
    )
    assert all(
        (ROOT / "tasks" / task.task_id / "1.0.1" / "task.yaml").is_file() for task in catalog.tasks
    )


def test_v2_workers_do_not_guess_provenance_from_exception_types() -> None:
    for worker in ROOT.glob("tasks/*/1.0.2/verifier/subject_worker.py"):
        source = worker.read_text(encoding="utf-8")
        assert "_declared_subject_failure" not in source
        assert "isinstance(error" not in source
        assert "SUBJECT_EXCEPTION_" not in source


def test_verifier_process_nonzero_remains_infrastructure() -> None:
    stage, subtype, reason = DockerSandbox._verifier_status_failure(SandboxStatus.FAILED)

    assert stage is VerifierLifecycleStage.PROCESS_WAIT
    assert subtype is VerifierFailureSubtype.VERIFIER_PROCESS_NONZERO
    assert reason == "VERIFIER_PROCESS_EXITED_NONZERO"
