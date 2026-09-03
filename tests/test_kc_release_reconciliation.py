from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from harnesslab.release import final_verifier as final
from harnesslab.release import reconciliation as kc
from harnesslab.release.badcases import build_badcases
from harnesslab.release.contracts import (
    CoreReleaseError,
    evaluate_release_readiness,
    load_core_corpus,
    tag_creation_authorized,
)
from harnesslab.release.judge_j4 import build_j4_plan
from harnesslab.release.models import EvidenceState, ReleaseEvidenceManifest
from harnesslab.release.v6 import build_v6_plan

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def snapshot() -> final.AuthoritativeReleaseSnapshot:
    """Deterministic verifier fixture; never represented as new real evidence."""
    accepted, rows, pairs = kc.stable_sources(ROOT)
    plan = build_v6_plan(ROOT, {})
    badcases = {s.run_identity: s for s in build_badcases(ROOT).slots}
    runs = []
    for row in rows:
        case = badcases.get("run:" + row["run_id"])
        detail = case.frozen_evidence if case else None
        trace_digest = detail.normalized_trace_digest if detail else None
        runs.append(
            final.RunEvidenceSummary.model_validate(
                {
                    **{
                        k: row[k]
                        for k in (
                            "run_id",
                            "slot_id",
                            "cell_id",
                            "task_id",
                            "task_version",
                            "task_digest",
                            "verifier_identity",
                            "repeat_index",
                            "evidence_digest",
                            "lane",
                        )
                    },
                    "status": row["primary_status"],
                    "normalized_outcome": row["primary_normalized_outcome"],
                    "source_outcome": row["primary_source_outcome"],
                    "safe_trace_available": trace_digest is not None,
                    "normalized_trace_digest": trace_digest,
                    "safe_trace_facts": case.safe_trace_facts if case else (),
                }
            )
        )
    pair, ablation = kc.accepted_comparison_summaries(pairs)
    experiment = final.ExperimentEvidenceSummary(
        experiment_id=accepted.experiment_id,
        record_status="queued",
        plan=plan,
        runs=tuple(runs),
        report_experiment_id=accepted.experiment_id,
        report_plan_digest=plan.digest,
        report_run_count=630,
        report_digest=kc.raw_digest(ROOT / (kc.MATRIX_PREFIX + "final-analysis.json")),
        pair=pair,
        ablation=ablation,
        authoritative_loader_verified=True,
        accepted_successor_digest=accepted.digest,
    )
    judge_plan = build_j4_plan(ROOT)
    judge = final.JudgeEvidenceSummary(
        calibration_id=accepted.judge_calibration_id,
        record_status="completed",
        plan=judge_plan,
        evaluation_count=63,
        completed_evaluation_count=63,
        observed_models=("grok-4.6-build",),
        report_calibration_id=accepted.judge_calibration_id,
        report_plan_digest=judge_plan.plan_digest,
        report_suite_id=judge_plan.suite_id,
        report_suite_version=judge_plan.suite_version,
        report_suite_digest=judge_plan.suite_digest,
        report_digest=accepted.judge_report_digest,
        l0_override_count=0,
        real_judge_smoke="VERIFIED",
        authoritative_report_verified=True,
    )
    return final.AuthoritativeReleaseSnapshot(experiment=experiment, judge=judge)


def test_kc_stable_contract_preserves_science_history_and_hard_stop() -> None:
    manifest = kc.verify_candidate(ROOT)
    readiness = evaluate_release_readiness(manifest)
    assert readiness.blockers == ("RELEASE_COMMIT", "REMOTE_CI")
    assert not readiness.core_release_ready
    assert not tag_creation_authorized(manifest)
    assert manifest.release_history.complete_smoke is EvidenceState.NOT_VERIFIED
    assert manifest.release_history.matrix_evidence is EvidenceState.NOT_RUN
    assert manifest.real_statuses["REAL_DEEPSEEK_SMOKE"] is EvidenceState.DEFERRED_NOT_VERIFIED
    _, claims = kc.build_candidate(ROOT)
    states = {c.claim_id: c.status for c in claims.claims if c.source_phase == "K-B"}
    assert states == {
        "real-matrix-results": EvidenceState.VERIFIED,
        "real-judge-quality": EvidenceState.VERIFIED,
        "real-badcases": EvidenceState.VERIFIED,
        "harness-uplift": EvidenceState.NOT_VERIFIED,
    }
    with pytest.raises(ValidationError):
        ReleaseEvidenceManifest.model_validate(
            {**manifest.model_dump(), "core_release_ready": True}
        )
    with pytest.raises(ValidationError, match="scope"):
        ReleaseEvidenceManifest.model_validate(
            {
                **manifest.model_dump(),
                "real_statuses": {
                    **manifest.real_statuses,
                    "REAL_DEEPSEEK_SMOKE": EvidenceState.VERIFIED,
                },
            }
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("comparable", 90),
        ("total_observations", 90),
        ("formal_eligible", True),
        ("not_comparable", 0),
        ("changed_dimension", "model"),
        ("source_digest", "sha256:" + "0" * 64),
        ("base_cell_id", "model-gpt56-relay-responses"),
    ],
)
def test_kc_rejects_fabricated_stronger_ablation(
    snapshot: final.AuthoritativeReleaseSnapshot,
    field: str,
    value: Any,
) -> None:
    ablation = snapshot.experiment.ablation.model_copy(update={field: value})
    experiment = snapshot.experiment.model_copy(update={"ablation": ablation})
    with pytest.raises(CoreReleaseError, match="Pair/Ablation"):
        kc.verify_v6_snapshot(ROOT, snapshot.model_copy(update={"experiment": experiment}))


def test_kc_rejects_relabeling_one_not_comparable_pair(monkeypatch: pytest.MonkeyPatch) -> None:
    original = kc.read_object

    def changed(root: Path, reference: str) -> dict[str, Any]:
        value = original(root, reference)
        if reference == kc.PAIR_REFERENCE:
            value = copy.deepcopy(value)
            records = value["pairs"][kc.ABLATION_ID]["records"]
            pair = next(
                p for p in records if p["effective"]["comparability"]["status"] == "NOT_COMPARABLE"
            )
            pair["effective"]["comparability"]["status"] = "COMPARABLE"
        return value

    monkeypatch.setattr(kc, "read_object", changed)
    with pytest.raises(CoreReleaseError, match="Comparability results"):
        kc.stable_sources(ROOT)


@pytest.mark.parametrize(
    "field,value",
    [
        ("provider_route", "fabricated-route"),
        ("profile_identity", "sha256:" + "1" * 64),
        ("reasoning_effort", "medium"),
        ("resource_envelope_identity", "sha256:" + "1" * 64),
    ],
)
def test_kc_rejects_treatment_and_hard_control_drift(
    snapshot: final.AuthoritativeReleaseSnapshot,
    field: str,
    value: str,
) -> None:
    plan = snapshot.experiment.plan
    cells = tuple(
        c.model_copy(update={field: value}) if c.id == "harness-codex-gpt56-high" else c
        for c in plan.cells
    )
    changed = snapshot.experiment.model_copy(
        update={"plan": plan.model_copy(update={"cells": cells})}
    )
    with pytest.raises(CoreReleaseError, match="plan binding"):
        kc.verify_v6_snapshot(ROOT, snapshot.model_copy(update={"experiment": changed}))


@pytest.mark.parametrize(
    "field,value",
    [
        ("completed_evaluation_count", 62),
        ("observed_models", ("grok-4.6",)),
        ("report_digest", "sha256:" + "0" * 64),
        ("l0_override_count", 1),
        ("real_judge_smoke", "NOT_RUN"),
        ("authoritative_report_verified", False),
    ],
)
def test_kc_judge_authority_is_fail_closed(
    snapshot: final.AuthoritativeReleaseSnapshot,
    field: str,
    value: Any,
) -> None:
    with pytest.raises(CoreReleaseError, match="J4 release authority"):
        kc.verify_v6_snapshot(
            ROOT,
            snapshot.model_copy(update={"judge": snapshot.judge.model_copy(update={field: value})}),
        )


def test_kc_report_alone_cannot_verify_real_judge() -> None:
    plan = build_j4_plan(ROOT)
    with pytest.raises(CoreReleaseError, match="63 unique"):
        kc.verify_j4_live_report(ROOT, plan, None, (), (ROOT,))


def test_kc_source_digest_cannot_be_rebound_to_fabricated_evidence(tmp_path: Path) -> None:
    plan = kc.load_accepted_plan(ROOT).model_dump(mode="json")
    plan["source_digests"][kc.PAIR_REFERENCE] = "sha256:" + "0" * 64
    target = tmp_path / kc.PLAN_REFERENCE
    target.parent.mkdir()
    target.write_text(json.dumps(plan))
    with pytest.raises(CoreReleaseError, match="authority drifted"):
        kc.load_accepted_plan(tmp_path)


def ci_fixture() -> final.RemoteCIAttestation:
    return final.RemoteCIAttestation(
        run_id="fake-ci-only",
        head_sha="a" * 40,
        workflow_name=final.EXPECTED_WORKFLOW,
        conclusion="success",
        successful_gates=final.EXPECTED_GATES,
        successful_jobs=tuple(sorted(final.REQUIRED_RELEASE_JOBS)),
        url="https://example.invalid/fake-ci",
    )


def verify_fixture(
    snapshot: final.AuthoritativeReleaseSnapshot,
    ci: final.RemoteCIAttestation,
    claims_override: Any = None,
) -> Any:
    candidate, claims = kc.build_candidate(ROOT)
    corpus = load_core_corpus(ROOT / "release/core-corpus-v4.json")
    return final.verify_semantic_final_release(
        repository_root=ROOT,
        checked_corpus=corpus,
        rebuilt_corpus=corpus,
        release_plan=kc.load_accepted_plan(ROOT),
        manifest=final.bind_final_head(candidate, ci, ci.head_sha),
        claims=claims_override or claims,
        badcases=build_badcases(ROOT),
        snapshot=snapshot,
        ci=ci,
        local_head=ci.head_sha,
    )


def test_kc_detached_fixture_preserves_committed_candidate_and_requires_receipt(
    snapshot: final.AuthoritativeReleaseSnapshot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = (ROOT / "release/release-evidence.json").read_bytes()
    monkeypatch.setattr(final, "_verify_final_checkout", lambda *args: None)
    ci = ci_fixture()
    receipt = verify_fixture(snapshot, ci)
    candidate = kc.verify_candidate(ROOT)
    bound = final.bind_final_head(candidate, ci, ci.head_sha)
    assert receipt.candidate_manifest_digest == candidate.digest
    assert not tag_creation_authorized(candidate, receipt)
    assert not tag_creation_authorized(bound)
    assert tag_creation_authorized(bound, receipt)
    assert not tag_creation_authorized(bound, receipt.model_copy(update={"release_head": "b" * 40}))
    assert (ROOT / "release/release-evidence.json").read_bytes() == before


def test_kc_rejects_prior_head_ci_and_missing_qualification(
    snapshot: final.AuthoritativeReleaseSnapshot,
) -> None:
    candidate = kc.verify_candidate(ROOT)
    with pytest.raises(CoreReleaseError, match="exact-head"):
        final.bind_final_head(candidate, ci_fixture(), "b" * 40)
    ci = ci_fixture().model_copy(update={"successful_jobs": ("gate-K",)})
    with pytest.raises(CoreReleaseError, match="Full Release CI"):
        verify_fixture(snapshot, ci)
    with pytest.raises(CoreReleaseError, match="exact clean"):
        final._verify_final_checkout(ROOT, "b" * 40, candidate)


def test_kc_rejects_new_causal_claim_even_with_an_authoritative_reference(
    snapshot: final.AuthoritativeReleaseSnapshot,
) -> None:
    _, claims = kc.build_candidate(ROOT)
    claim = claims.claims[-1].model_copy(
        update={
            "claim_id": "reasoning-causal-effect",
            "claim": "Higher effort causes improvement",
            "evidence_refs": (f"experiment-ablation:{kc.ABLATION_ID}",),
        }
    )
    with pytest.raises(CoreReleaseError, match="Claim Map"):
        verify_fixture(
            snapshot, ci_fixture(), claims.model_copy(update={"claims": (*claims.claims, claim)})
        )
