from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError
from scripts.freeze_kb4_badcases import audit_originals

from harnesslab.contracts.common import EvaluationLane
from harnesslab.contracts.run import RunStatus
from harnesslab.evidence.reader import EvidenceReadError
from harnesslab.experiment.outcomes import StatisticalOutcome
from harnesslab.release import badcases
from harnesslab.release.final_verifier import RunEvidenceSummary, _badcase_trace_matches
from harnesslab.release.models import BadCasePlan, BadCaseSlot, EvidenceState
from harnesslab.sandbox.artifacts import sha256_file

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def plan() -> BadCasePlan:
    return badcases.verify_frozen_badcases(ROOT)


@pytest.mark.parametrize(
    ("reference", "historical_digest"),
    (
        (
            "src/harnesslab/diagnosis/service.py",
            "sha256:84b6fb001654e38cccc690da53711e96030376967fb3e02c0965e01245d6b524",
        ),
        (
            "docs/ANALYST.md",
            "sha256:d793cfbd1f0a2aad650161058fe874ddded30a7399475b26626327b1413eac39",
        ),
    ),
)
def test_current_repairs_preserve_frozen_badcase_provenance(
    monkeypatch: pytest.MonkeyPatch, reference: str, historical_digest: str
) -> None:
    real_hash = sha256_file
    monkeypatch.setattr(
        badcases,
        "sha256_file",
        lambda path: "sha256:" + "0" * 64 if path == ROOT / reference else real_hash(path),
    )
    source = badcases.accepted_source(ROOT)
    assert source["provenance"]["sources"][reference]["sha256"] == historical_digest
    assert badcases.verify_frozen_badcases(ROOT).canonical_json() == (
        BadCasePlan.model_validate_json((ROOT / badcases.CANONICAL).read_text()).canonical_json()
    )


@pytest.mark.parametrize("reference", ("src/harnesslab/diagnosis/service.py", "docs/ANALYST.md"))
def test_frozen_source_binding_cannot_be_rebound(
    monkeypatch: pytest.MonkeyPatch, reference: str
) -> None:
    source = badcases.read_object(ROOT / badcases.SOURCE)
    source["provenance"]["sources"][reference]["sha256"] = "sha256:" + "0" * 64
    monkeypatch.setattr(badcases, "read_object", lambda _: source)
    with pytest.raises(ValueError, match=r"historical K-B4\.2 input identity drift"):
        badcases.accepted_source(ROOT)


def test_current_unsuperseded_source_drift_is_still_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = "src/harnesslab/diagnosis/models.py"
    real_hash = sha256_file
    monkeypatch.setattr(
        badcases,
        "sha256_file",
        lambda path: "sha256:" + "0" * 64 if path == ROOT / reference else real_hash(path),
    )
    with pytest.raises(ValueError, match=f"K-B4.2 repository source drift: {reference}"):
        badcases.accepted_source(ROOT)


def test_exact_three_frozen_badcases_and_accepted_execution_identities(plan: BadCasePlan) -> None:
    expected = (
        ("badcase-1", "harness-codex-gpt56-high", "core-java-settings-merge", 0),
        ("badcase-2", "harness-codex-gpt56-high", "core-python-deduplicate", 2),
        ("badcase-3", "model-gpt56-relay-responses", "core-python-deduplicate", 0),
    )
    source = badcases.accepted_source(ROOT)
    assert len(plan.slots) == 3
    for slot, (slot_id, cell, task, repeat), candidate in zip(
        plan.slots, expected, badcases.SELECTED, strict=True
    ):
        assert slot.slot_id == slot_id
        assert slot.status is EvidenceState.VERIFIED
        assert slot.placeholder is None
        detail = slot.frozen_evidence
        assert detail is not None and detail.candidate_id == candidate
        member = source["members"][detail.experiment_slot_id]
        assert member["cell_id"] == cell and member["task_id"] == task
        assert member["task_version"] == "1.0.2"
        assert slot.cell_identity == f"cell:{cell}"
        assert slot.task_identity == f"task:{task}@1.0.2#{member['task_digest']}"
        assert detail.repeat_index == repeat == member["repeat_index"]
        assert detail.execution_run_identity == "run:" + member["effective_run_id"]
        assert slot.run_identity is not None
        assert detail.execution_run_identity == slot.run_identity + "-a1"
        assert detail.primary_run_identity == detail.execution_run_identity
        assert detail.effective_source == "primary" and detail.recovery_run_identity is None
        assert detail.manifest_digest == member["manifest_digest"]
        assert detail.verifier_report.model_dump(mode="json") == member["verifier"]["report"]
    assert "kb4-candidate-d010ad8e7a9a9e42" not in plan.canonical_json()
    assert "NOT_VERIFIED" not in plan.canonical_json()


def test_required_refs_resolve_to_bound_catalog_and_repository_files(plan: BadCasePlan) -> None:
    source = badcases.accepted_source(ROOT)
    for slot in plan.slots:
        detail = slot.frozen_evidence
        assert detail is not None
        member = source["members"][detail.experiment_slot_id]
        resolved = {
            slot.run_identity,
            slot.cell_identity,
            slot.task_identity,
            "manifest:" + detail.manifest_digest,
            badcases.SOURCE,
            *detail.file_digests,
            *detail.tree_digests,
        }
        verifier_ref = next(r for r in slot.evidence_refs if r.startswith("verifier:"))
        # The current task package identity is independently checked by accepted_source.
        task_path = ROOT / f"tasks/{member['task_id']}/{member['task_version']}"
        from harnesslab.tasks.package import TaskPackage

        assert verifier_ref == "verifier:" + TaskPackage.load(task_path).verifier_digest
        resolved.add(verifier_ref)
        if detail.normalized_trace_digest:
            assert slot.run_identity is not None
            resolved.add(
                f"trace:{slot.run_identity.removeprefix('run:')}#{detail.normalized_trace_digest}"
            )
        assert set(slot.evidence_refs) == resolved
        for ref, digest in detail.file_digests.items():
            assert source["provenance"]["sources"][ref]["sha256"] == digest
            if not ref.startswith("evidence:"):
                assert sha256_file(ROOT / ref) == digest
        for part in ("workspace", "verifier"):
            binding = member[part]["binding"]
            assert binding["status"] == "MATCH"
            assert detail.tree_digests[binding["reference"]] == binding["actual_digest"]
        for hypothesis in slot.hypotheses:
            assert all((ROOT / ref).is_file() for ref in hypothesis.evidence_refs)


def test_observed_failures_hypotheses_and_trace_limits(plan: BadCasePlan) -> None:
    java, high, direct = plan.slots
    assert all(
        s.root_cause is None and s.attribution_classification == "OBSERVED_FACT" for s in plan.slots
    )
    assert java.hypotheses == ()
    assert java.frozen_evidence is not None
    assert java.frozen_evidence.failure_class.value == "No Modification"
    assert not java.frozen_evidence.source_diffs
    assert {c.name for c in java.frozen_evidence.verifier_report.checks if not c.passed} == {
        "normalizes",
        "preserves-order",
        "duplicate-rejected",
        "invalid-rejected",
    }
    for slot in (high, direct):
        detail = slot.frozen_evidence
        assert detail is not None
        assert detail.failure_class.value == "Test Failure"
        assert [c.name for c in detail.verifier_report.checks if not c.passed] == [
            "empty-key-rejected"
        ]
        assert sum(c.passed for c in detail.verifier_report.checks) == 4
        assert detail.verifier_report.score == 0.8
        assert detail.source_diffs
        assert len(slot.hypotheses) == 1
        assert slot.hypotheses[0].classification == "ATTRIBUTION_HYPOTHESIS"
        assert slot.hypotheses[0].verify_or_falsify
    assert high.hypotheses == direct.hypotheses
    assert direct.frozen_evidence is not None
    assert direct.frozen_evidence.trace_status == "NOT_REPORTED"
    assert direct.safe_trace_facts == direct.frozen_evidence.safe_tool_facts == ()
    assert all(
        not p.controlled_attribution_claimed
        for s in plan.slots
        if s.frozen_evidence
        for p in s.frozen_evidence.comparisons
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("root_cause", "Reasoning effort caused the failure"),
        ("attribution_classification", "CONTROLLED_ATTRIBUTION"),
        ("safe_trace_facts", ["TRACE_EVENT_TYPE:COMMAND_EXECUTION"]),
    ],
)
def test_schema_rejects_unsupported_causes_and_invented_direct_trace(
    plan: BadCasePlan,
    field: str,
    value: Any,
) -> None:
    raw = plan.slots[2].model_dump(mode="json")
    raw[field] = value
    with pytest.raises(ValidationError):
        BadCaseSlot.model_validate(raw)


@pytest.mark.parametrize(
    "field,value",
    [
        ("run_identity", "run:wrong-run"),
        ("candidate_id", "kb4-candidate-d010ad8e7a9a9e42"),
        ("manifest_digest", "sha256:" + "0" * 64),
    ],
)
def test_frozen_check_rejects_identity_or_held_candidate_drift(
    plan: BadCasePlan,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: str,
) -> None:
    monkeypatch.setattr(badcases, "build_badcases", lambda _: plan)
    raw = plan.model_dump(mode="json")
    target = raw["slots"][0] if field == "run_identity" else raw["slots"][0]["frozen_evidence"]
    target[field] = value
    (tmp_path / "release").mkdir()
    (tmp_path / badcases.CANONICAL).write_text(badcases.encoded(raw))
    with pytest.raises(ValueError, match="canonical BadCase drift"):
        badcases.verify_frozen_badcases(tmp_path)


def test_freeze_and_receipt_reproduce_byte_for_byte(plan: BadCasePlan) -> None:
    assert plan == badcases.build_badcases(ROOT) == badcases.build_badcases(ROOT)
    receipt = json.loads((ROOT / badcases.RECEIPT).read_text())
    assert receipt == badcases.freeze_receipt(plan)
    assert receipt["canonical_model_digest"] == plan.digest
    assert receipt["distinct_failure_signatures"] == 2
    assert receipt["controlled_attribution_claims"] == 0
    assert set(receipt["external_execution"].values()) == {0}


def test_original_audit_blocks_missing_or_changed_selected_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises((FileNotFoundError, EvidenceReadError)):
        audit_originals(ROOT, tmp_path)
    source = badcases.accepted_source(ROOT)
    member = copy.deepcopy(next(iter(source["members"].values())))
    member["complete_bundle_verified"] = False
    monkeypatch.setattr("scripts.freeze_kb4_badcases.inspect_member", lambda *args: member)
    with pytest.raises(ValueError, match="selected evidence drift"):
        audit_originals(ROOT, tmp_path)


def test_direct_trace_exception_never_accepts_missing_harness_trace(plan: BadCasePlan) -> None:
    slot = plan.slots[2]
    detail = slot.frozen_evidence
    assert detail is not None
    assert slot.run_identity is not None
    source = badcases.accepted_source(ROOT)["members"][detail.experiment_slot_id]
    run = RunEvidenceSummary(
        run_id=slot.run_identity.removeprefix("run:"),
        slot_id=detail.experiment_slot_id,
        cell_id=source["cell_id"],
        task_id=source["task_id"],
        task_version=source["task_version"],
        task_digest=source["task_digest"],
        verifier_identity="sha256:" + "0" * 64,
        repeat_index=detail.repeat_index,
        status=RunStatus.FAILED_SUBJECT,
        normalized_outcome=StatisticalOutcome.CAPABILITY_FAIL,
        source_outcome="verified_fail",
        evidence_digest=detail.manifest_digest,
        safe_trace_available=False,
        normalized_trace_digest=None,
        safe_trace_facts=(),
        lane=EvaluationLane.MODEL,
    )
    assert _badcase_trace_matches(slot, run)
    assert not _badcase_trace_matches(slot, run.model_copy(update={"lane": EvaluationLane.HARNESS}))
    assert not _badcase_trace_matches(slot, run.model_copy(update={"evidence_digest": "wrong"}))
    assert not _badcase_trace_matches(slot, run.model_copy(update={"repeat_index": 99}))


async def test_readiness_reports_checked_badcases_without_promoting_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from harnesslab.api import workbench_service

    session = AsyncMock()
    session.scalars.return_value = Mock(all=lambda: [])
    response = await workbench_service.core_readiness(session, ())
    check = next(c for c in response.checks if c.key == "BADCASE_EVIDENCE")
    assert check.status == "READY" and "frozen" in check.evidence
    assert response.status == "NOT_READY" and "RELEASE_EVIDENCE" in response.blockers

    def invalid(_: Path) -> BadCasePlan:
        raise ValueError("freeze receipt drift")

    monkeypatch.setattr(workbench_service, "verify_frozen_badcases", invalid)
    response = await workbench_service.core_readiness(session, ())
    check = next(c for c in response.checks if c.key == "BADCASE_EVIDENCE")
    assert check.status == "NOT_VERIFIED" and "BADCASE_EVIDENCE" in response.blockers


@pytest.mark.parametrize("changed_file", [badcases.CANONICAL, badcases.RECEIPT])
def test_generator_refuses_to_repair_existing_frozen_drift(
    plan: BadCasePlan,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    changed_file: str,
) -> None:
    from scripts import freeze_kb4_badcases

    (tmp_path / "release").mkdir()
    (tmp_path / badcases.CANONICAL).write_text(badcases.encoded(plan.model_dump(mode="json")))
    (tmp_path / badcases.RECEIPT).write_text(badcases.encoded(badcases.freeze_receipt(plan)))
    altered = (tmp_path / changed_file).read_text() + " "
    (tmp_path / changed_file).write_text(altered)
    monkeypatch.setattr(freeze_kb4_badcases, "audit_originals", lambda *_: plan)
    monkeypatch.setattr(badcases, "build_badcases", lambda _: plan)
    monkeypatch.setattr("sys.argv", ["freeze_kb4_badcases", "--repo-root", str(tmp_path)])
    with pytest.raises(SystemExit, match="BLOCKED_BADCASE_FREEZE_INTEGRITY"):
        freeze_kb4_badcases.main()
    assert (tmp_path / changed_file).read_text() == altered


def test_release_consumer_rejects_altered_frozen_factual_payload(plan: BadCasePlan) -> None:
    from harnesslab.release.contracts import CoreReleaseError
    from harnesslab.release.final_verifier import _verify_badcases_and_claims
    from tests.release_semantic_fixture import semantic_fixture

    fixture = semantic_fixture()
    altered = plan.slots[0].model_copy(update={"observed_failure": "Unbound invented fact"})
    changed = plan.model_copy(update={"slots": (altered, *plan.slots[1:])})
    with pytest.raises(CoreReleaseError, match="frozen evidence drifted"):
        _verify_badcases_and_claims(
            fixture["manifest"], changed, fixture["claims"], fixture["snapshot"]
        )
