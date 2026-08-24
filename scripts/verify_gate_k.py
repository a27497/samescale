from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

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
from harnesslab.release.models import EvidenceBinding, EvidenceState

ROOT = Path(__file__).resolve().parents[1]
JUNIT = ROOT / "gate-k-results.xml"
REQUIRED_DOCS = (
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
)
CRITICAL_TESTS = {
    "test_core_corpus_is_exact_balanced_deterministic_and_validated",
    "test_corpus_rejects_a_mutated_verifier",
    "test_real_plan_has_strict_unresolved_profiles_and_exact_preflight",
    "test_planned_uplift_pair_cannot_bypass_provider_route_comparability",
    "test_ablation_plan_freezes_hard_controls_and_is_not_run",
    "test_release_evidence_is_strict_keyless_and_not_ready",
    "test_verified_evidence_and_resume_claims_cannot_be_forged",
    "test_resume_claim_map_refs_exist_and_real_claims_remain_unverified",
    "test_three_badcase_slots_are_explicitly_pending",
    "test_tag_guard_refuses_incomplete_release_and_tag_is_absent",
    "test_release_docs_and_fresh_setup_contract_exist",
    "test_ci_runs_keyless_gate_k_after_gate_j_without_real_execution",
}


@dataclass(frozen=True)
class Check:
    name: str
    command: tuple[str, ...]
    timeout_seconds: int = 1200


def run(check: Check) -> bool:
    print(f"\n=== {check.name} ===", flush=True)
    print("COMMAND:", subprocess.list2cmdline(check.command), flush=True)
    try:
        result = subprocess.run(check.command, cwd=ROOT, check=False, timeout=check.timeout_seconds)
    except subprocess.TimeoutExpired:
        print(f"FAIL: command exceeded {check.timeout_seconds}s")
        return False
    print(f"{'PASS' if result.returncode == 0 else 'FAIL'}: exit={result.returncode}")
    return result.returncode == 0


def verify_junit() -> bool:
    try:
        cases = ET.parse(JUNIT).getroot().findall(".//testcase")
    except (OSError, ET.ParseError):
        print("FAIL: Gate K JUnit evidence is unavailable")
        return False
    names = {case.attrib.get("name", "") for case in cases}
    skipped = [
        case.attrib.get("name", "unknown") for case in cases if case.find("skipped") is not None
    ]
    missing = CRITICAL_TESTS - names
    if not cases or skipped or missing:
        print(
            "FAIL: Gate K test evidence incomplete: "
            f"cases={len(cases)} skipped={skipped} missing={sorted(missing)}"
        )
        return False
    print(f"PASS: {len(cases)} Gate K focused tests recorded; critical set present; zero skipped")
    return True


def verify_contract_mode() -> bool:
    try:
        checked = load_core_corpus(ROOT / "release/core-corpus.json")
        rebuilt = build_corpus_manifest(ROOT)
        plan = load_real_evidence_plan(ROOT / "release/core-real-evidence-plan.json")
        evidence = load_release_evidence(ROOT / "release/release-evidence.json")
        claims = load_resume_claim_map(ROOT / "release/resume-claim-evidence.json")
        badcases = load_badcase_plan(ROOT / "release/badcases.json")
        validate_keyless_contract_state(evidence)
    except CoreReleaseError as exc:
        print(f"FAIL: release contract invalid: {exc}")
        return False
    if rebuilt != checked:
        print("FAIL: checked corpus differs from independently rebuilt task inventory")
        return False
    if any(not (ROOT / path).is_file() for path in REQUIRED_DOCS):
        print("FAIL: Core document set is incomplete")
        return False
    if any(
        not (ROOT / reference).exists()
        for claim in claims.claims
        if claim.status is EvidenceState.VERIFIED
        for reference in claim.evidence_refs
    ):
        print("FAIL: VERIFIED resume claim references missing evidence")
        return False
    if len(badcases.slots) != 3 or any(
        slot.status is not EvidenceState.NOT_VERIFIED for slot in badcases.slots
    ):
        print("FAIL: K-A BadCase placeholders are not fail-closed")
        return False
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    if workflow.index("scripts/verify_gate_j.py") >= workflow.index("scripts/verify_gate_k.py"):
        print("FAIL: Gate K is not ordered after Gate J")
        return False
    if "--final-release" in workflow:
        print("FAIL: ordinary CI invokes final release mode")
        return False
    tracked_environment_files = subprocess.run(
        ("git", "ls-files", "*.env", ".env", ".env.*"),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    tracked_env = [path for path in tracked_environment_files if not path.endswith(".env.example")]
    if tracked_env:
        print(f"FAIL: environment credential file is tracked: {tracked_env}")
        return False
    serialized_release = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (
            "release/core-real-evidence-plan.json",
            "release/release-evidence.json",
            "release/resume-claim-evidence.json",
        )
    )
    secret_patterns = (r"sk-[A-Za-z0-9_-]{20,}", r"(?i)bearer\s+[A-Za-z0-9._-]{20,}")
    if any(re.search(pattern, serialized_release) for pattern in secret_patterns):
        print("FAIL: release artifact contains secret-like material")
        return False
    readiness = evaluate_release_readiness(evidence)
    if readiness.core_release_ready or tag_creation_authorized(evidence):
        print("FAIL: incomplete K-A evidence authorized a release")
        return False
    if plan.deepseek_e2 is not EvidenceState.DEFERRED_NOT_VERIFIED:
        print("FAIL: DeepSeek E2 state drifted")
        return False
    tag = subprocess.run(
        ("git", "tag", "--list", "v1.0.0-core"),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if tag:
        print("FAIL: v1.0.0-core exists before final release authorization")
        return False
    print(f"CORE_CORPUS={len(checked.tasks)} digest={checked.digest} PASS")
    print(f"MODEL_ONLY_PROFILE_SLOTS={len(plan.model_profile_slots)} selections=NOT_VERIFIED PASS")
    print(
        f"REAL_MATRIX_PLAN={len(plan.cells)} cells x {plan.preflight.task_count} tasks "
        f"x {plan.preflight.repeat_count} repeats PASS"
    )
    print("PAIRED_LANE=PLANNED_NOT_VERIFIED; provider-route mismatch remains blocking")
    print("CONTROLLED_ABLATION=PLANNED_NOT_RUN; reasoning_effort is sole treatment")
    print("DEEPSEEK_E2=DEFERRED_NOT_VERIFIED")
    print("FAKE_KEYLESS_CONTRACT_EVIDENCE=PASS; REAL_RELEASE_EVIDENCE=NOT_RUN")
    print("CORE_RELEASE_READY=FALSE")
    print("REAL_EVIDENCE_AUTHORIZATION_REQUIRED=TRUE")
    for key, state in sorted(evidence.real_statuses.items()):
        print(f"{key}={state.value}")
    print("v1.0.0-core=ABSENT")
    return True


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def verify_artifact_binding(binding: EvidenceBinding, artifact_root: Path, label: str) -> None:
    if binding.state is not EvidenceState.VERIFIED or not binding.identity or not binding.digest:
        raise CoreReleaseError(f"{label} is not VERIFIED")
    if not binding.identity.startswith("artifact:"):
        raise CoreReleaseError(f"{label} must use artifact:<relative-path> identity")
    relative = binding.identity.removeprefix("artifact:")
    candidate = (artifact_root / relative).resolve()
    resolved_root = artifact_root.resolve()
    if resolved_root not in candidate.parents or not candidate.is_file():
        raise CoreReleaseError(f"{label} artifact is outside the trusted root or missing")
    if sha256_file(candidate) != binding.digest:
        raise CoreReleaseError(f"{label} artifact digest mismatch")


def verify_final_release(
    database_url: str | None, artifact_root_raw: str | None, remote_head: str | None
) -> bool:
    try:
        manifest = load_release_evidence(ROOT / "release/release-evidence.json")
        claims = load_resume_claim_map(ROOT / "release/resume-claim-evidence.json")
        badcases = load_badcase_plan(ROOT / "release/badcases.json")
        readiness = evaluate_release_readiness(manifest)
        if not database_url or not database_url.startswith("postgresql+"):
            raise CoreReleaseError(
                "--database-url must identify the trusted PostgreSQL evidence store"
            )
        if not artifact_root_raw or not remote_head:
            raise CoreReleaseError("--artifact-root and --remote-head are required")
        local_head = subprocess.run(
            ("git", "rev-parse", "HEAD"), cwd=ROOT, check=True, capture_output=True, text=True
        ).stdout.strip()
        if remote_head != local_head:
            raise CoreReleaseError("remote CI head does not match the checked-out release head")
        if manifest.release_commit.identity != f"git:{local_head}":
            raise CoreReleaseError("release commit evidence does not bind the checked-out head")
        with create_engine(database_url).connect() as connection:
            if connection.execute(text("SELECT 1")).scalar_one() != 1:
                raise CoreReleaseError("trusted PostgreSQL evidence store is unavailable")
        artifact_root = Path(artifact_root_raw)
        for label, binding in (
            ("real_matrix", manifest.real_matrix),
            ("paired_lane", manifest.paired_lane),
            ("controlled_ablation", manifest.controlled_ablation),
            ("judge_report", manifest.judge_report),
            *tuple(
                (f"badcase_{index}", binding)
                for index, binding in enumerate(manifest.badcase_evidence, 1)
            ),
        ):
            verify_artifact_binding(binding, artifact_root, label)
        for claim in claims.claims:
            if claim.status is EvidenceState.VERIFIED and (
                not claim.evidence_refs
                or any(not (ROOT / ref).exists() for ref in claim.evidence_refs)
            ):
                raise CoreReleaseError(f"VERIFIED resume claim lacks evidence: {claim.claim_id}")
        if any(slot.status is not EvidenceState.VERIFIED for slot in badcases.slots):
            raise CoreReleaseError("three evidence-bound VERIFIED BadCases are required")
        if not readiness.core_release_ready or not tag_creation_authorized(manifest):
            raise CoreReleaseError(f"hard-stop blockers remain: {readiness.blockers}")
    except (CoreReleaseError, OSError, SQLAlchemyError, subprocess.SubprocessError) as exc:
        print(f"NOT_VERIFIED: final release refused: {exc}")
        print("CORE_RELEASE_READY=FALSE")
        return False
    print("CORE_RELEASE_READY=TRUE")
    print("TAG_CREATION_AUTHORIZED=TRUE")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="HarnessLab Phase K release verifier")
    parser.add_argument("--final-release", action="store_true")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--artifact-root")
    parser.add_argument("--remote-head")
    arguments = parser.parse_args()
    if arguments.final_release:
        return (
            0
            if verify_final_release(
                arguments.database_url, arguments.artifact_root, arguments.remote_head
            )
            else 2
        )
    JUNIT.unlink(missing_ok=True)
    checks = (
        Check(
            "Gate K focused contract tests",
            (
                "uv",
                "run",
                "--locked",
                "pytest",
                "tests/test_release_contracts.py",
                f"--junitxml={JUNIT}",
                "-q",
            ),
        ),
        Check(
            "Fresh setup contract",
            ("uv", "run", "--locked", "python", "scripts/verify_fresh_setup.py"),
        ),
        Check("Ruff lint", ("uv", "run", "--locked", "ruff", "check", ".")),
        Check("Ruff format", ("uv", "run", "--locked", "ruff", "format", "--check", ".")),
        Check("Mypy", ("uv", "run", "--locked", "mypy", "src", "tests", "scripts")),
        Check("Git whitespace", ("git", "diff", "--check")),
    )
    for check in checks:
        if not run(check):
            return 1
    return 0 if verify_junit() and verify_contract_mode() else 1


if __name__ == "__main__":
    sys.exit(main())
