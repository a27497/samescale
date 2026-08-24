from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from harnesslab.comparability.engine import ComparabilityEngine
from harnesslab.comparability.models import (
    ComparabilityIntent,
    ComparabilityStatus,
    ComparisonFacts,
    canonical_digest,
)
from harnesslab.release.contracts import (
    CoreReleaseError,
    build_corpus_manifest,
    evaluate_release_readiness,
    load_badcase_plan,
    load_core_corpus,
    load_real_evidence_plan,
    load_release_evidence,
    load_resume_claim_map,
    tag_creation_authorized,
    validate_keyless_contract_state,
)
from harnesslab.release.models import EvidenceBinding, EvidenceState, ResumeClaim

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "release"
REQUIRED_DOCS = {
    "README.md",
    "docs/ARCHITECTURE.md",
    "docs/EVAL_METHODOLOGY.md",
    "docs/FAIRNESS_CONTRACT.md",
    "docs/BADCASES.md",
    "docs/INTERVIEW_GUIDE.md",
    "docs/RESUME_SCOPE.md",
    "docs/SECURITY.md",
    "docs/RELEASE_EVIDENCE.md",
    "docs/REAL_EVIDENCE_AUTHORIZATION.md",
}


def test_core_corpus_is_exact_balanced_deterministic_and_validated() -> None:
    checked = load_core_corpus(RELEASE / "core-corpus.json")
    rebuilt = build_corpus_manifest(ROOT)

    assert len(checked.tasks) == 18
    assert 15 <= len(checked.tasks) <= 25
    assert rebuilt == checked
    assert (
        rebuilt.digest == "sha256:353362d4075db0dacd90f865cd0a8f9e79ca625ee11808fd80faa17c2b0d669b"
    )
    assert len({(task.task_id, task.version) for task in checked.tasks}) == 18
    assert {
        language: sum(task.language == language for task in checked.tasks)
        for language in ("python", "java", "typescript")
    } == {
        "python": 6,
        "java": 6,
        "typescript": 6,
    }
    assert len({task.category for task in checked.tasks}) >= 5
    assert all(not task.baseline.passed for task in checked.tasks)
    assert all(task.oracle.passed and task.oracle.score == 1 for task in checked.tasks)
    assert not any(path.is_symlink() for path in (ROOT / "tasks").rglob("*"))


def test_corpus_rejects_a_mutated_verifier(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    shutil.copytree(ROOT / "tasks", repository / "tasks")
    verifier = repository / "tasks/core-python-deduplicate/1.0.0/verifier/verify.py"
    verifier.write_text("this is not valid Python!\n", encoding="utf-8")

    with pytest.raises(CoreReleaseError, match="Core task validation failed"):
        build_corpus_manifest(repository)


def test_real_plan_has_strict_unresolved_profiles_and_exact_preflight() -> None:
    plan = load_real_evidence_plan(RELEASE / "core-real-evidence-plan.json")

    assert len(plan.model_profile_slots) == 3
    assert all(slot.requested_model is None for slot in plan.model_profile_slots)
    assert all(
        slot.selection_state is EvidenceState.NOT_VERIFIED for slot in plan.model_profile_slots
    )
    assert len(plan.cells) == 7
    assert {cell.runtime for cell in plan.cells} == {
        "direct-model",
        "codex",
        "claude-code",
        "deepseek-e1",
    }
    assert plan.deepseek_e2 is EvidenceState.DEFERRED_NOT_VERIFIED
    assert plan.preflight.total_subject_runs == 630
    assert plan.preflight.total_top_level_external_calls == 693
    assert plan.preflight.total_output_token_ceiling == 1_276_128
    assert plan.preflight.monetary_cost == "NOT_CALCULATED_FROM_REPOSITORY_EVIDENCE"


def test_planned_uplift_pair_cannot_bypass_provider_route_comparability() -> None:
    common = {
        "task_id": "task",
        "task_version": "1.0.0",
        "task_digest": canonical_digest({"task": 1}),
        "workspace_input_digest": canonical_digest({"workspace": 1}),
        "context_identity": "NONE",
        "verifier_identity": canonical_digest({"verifier": 1}),
        "requested_model": "future-frozen-model",
        "observed_model": "future-frozen-model",
        "budget_identity": canonical_digest({"budget": 1}),
        "network_policy": "deny",
        "trace_coverage": "FULL",
    }
    direct = ComparisonFacts(
        evidence_identity=canonical_digest({"side": "direct"}),
        provider_route="openai|responses|https://api.openai.com/v1/responses",
        harness="direct-model",
        harness_version="1",
        harness_profile_identity=canonical_digest({"direct": 1}),
        prompt_identity=canonical_digest({"direct-prompt": 1}),
        **common,
    )
    codex = ComparisonFacts(
        evidence_identity=canonical_digest({"side": "codex"}),
        provider_route="codex-cli-default",
        harness="codex",
        harness_version="cli",
        harness_profile_identity=canonical_digest({"codex": 1}),
        prompt_identity=canonical_digest({"codex-prompt": 1}),
        **common,
    )

    report = ComparabilityEngine().assess(direct, codex, intent=ComparabilityIntent.HARNESS_UPLIFT)
    assert report.status is ComparabilityStatus.NOT_COMPARABLE
    plan = load_real_evidence_plan(RELEASE / "core-real-evidence-plan.json")
    assert plan.paired_lane.comparability_state is EvidenceState.NOT_VERIFIED
    assert "route differs" in plan.paired_lane.blocker.lower()


def test_ablation_plan_freezes_hard_controls_and_is_not_run() -> None:
    plan = load_real_evidence_plan(RELEASE / "core-real-evidence-plan.json")
    cells = {cell.cell_id: cell for cell in plan.cells}
    base = cells[plan.ablation.base_cell_id]
    variant = cells[plan.ablation.variant_cell_id]

    assert plan.ablation.changed_dimension == "reasoning_effort"
    assert base.reasoning_effort == "medium"
    assert variant.reasoning_effort == "high"
    assert base.runtime == variant.runtime == "codex"
    assert base.provider_route == variant.provider_route
    assert plan.ablation.evidence_state is EvidenceState.NOT_RUN
    assert set(plan.ablation.frozen_hard_controls) >= {
        "provider_route",
        "task identities",
        "verifier identities",
    }


def test_release_evidence_is_strict_keyless_and_not_ready() -> None:
    manifest = load_release_evidence(RELEASE / "release-evidence.json")
    validate_keyless_contract_state(manifest)
    readiness = evaluate_release_readiness(manifest)

    assert not manifest.core_release_ready
    assert not readiness.core_release_ready
    assert readiness.real_evidence_authorization_required
    assert "REAL_MATRIX_EVIDENCE" in readiness.blockers
    assert "JUDGE_EVIDENCE" in readiness.blockers
    assert all(state is EvidenceState.NOT_RUN for state in manifest.real_statuses.values())


def test_verified_evidence_and_resume_claims_cannot_be_forged() -> None:
    with pytest.raises(ValidationError, match="VERIFIED evidence requires identity and digest"):
        EvidenceBinding(state=EvidenceState.VERIFIED)
    with pytest.raises(ValidationError, match="VERIFIED resume claim requires evidence"):
        ResumeClaim(
            claim_id="forged",
            claim="Unsupported claim",
            status=EvidenceState.VERIFIED,
            required_evidence_type="missing",
            evidence_refs=(),
            source_phase="K",
        )


def test_resume_claim_map_refs_exist_and_real_claims_remain_unverified() -> None:
    claim_map = load_resume_claim_map(RELEASE / "resume-claim-evidence.json")
    for claim in claim_map.claims:
        if claim.status is EvidenceState.VERIFIED:
            assert claim.evidence_refs
            assert all((ROOT / reference).exists() for reference in claim.evidence_refs)
    assert all(
        claim.status is EvidenceState.NOT_VERIFIED
        for claim in claim_map.claims
        if claim.source_phase == "K-B"
    )


def test_three_badcase_slots_are_explicitly_pending() -> None:
    plan = load_badcase_plan(RELEASE / "badcases.json")
    assert len(plan.slots) == 3
    assert all(slot.status is EvidenceState.NOT_VERIFIED for slot in plan.slots)
    assert all(slot.placeholder == "NOT_VERIFIED — REAL EVIDENCE PENDING" for slot in plan.slots)
    assert all(not slot.evidence_refs for slot in plan.slots)


def test_tag_guard_refuses_incomplete_release_and_tag_is_absent() -> None:
    manifest = load_release_evidence(RELEASE / "release-evidence.json")
    assert not tag_creation_authorized(manifest)
    tags = subprocess.run(
        ("git", "tag", "--list", "v1.0.0-core"),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert not tags


def test_release_docs_and_fresh_setup_contract_exist() -> None:
    assert not {path for path in REQUIRED_DOCS if not (ROOT / path).is_file()}
    assert (ROOT / "scripts/verify_fresh_setup.py").is_file()


def test_ci_runs_keyless_gate_k_after_gate_j_without_real_execution() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert workflow.index("scripts/verify_gate_j.py") < workflow.index("scripts/verify_gate_k.py")
    assert "--final-release" not in workflow
    assert "REAL_EVIDENCE_AUTHORIZED" not in workflow
    assert not any(
        marker in json.dumps(json.loads((RELEASE / "release-evidence.json").read_text()))
        for marker in ("sk-", "Bearer ", 'api_key": "')
    )
