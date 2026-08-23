from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path


class ExitCode(IntEnum):
    PASS = 0
    FAIL = 1
    NOT_VERIFIED = 2


@dataclass(frozen=True)
class Check:
    name: str
    command: tuple[str, ...]
    timeout_seconds: int = 1200


ROOT = Path(__file__).resolve().parents[1]
JUNIT = ROOT / "gate-h-results.xml"
EVIDENCE = ROOT / "harnesslab-artifacts/gate-h-evidence.json"
PHASE_H_TESTS = (
    "tests/test_judge_contracts.py",
    "tests/test_judge_plan.py",
    "tests/test_judge_e2e.py",
)
CRITICAL_TESTS = {
    "test_strict_judge_definition_suite_and_deterministic_digests",
    "test_suite_rejects_invalid_gold_and_probe_metadata",
    "test_public_suite_no_answer_key_and_hidden_gold_mutation_preserves_request_bytes",
    "test_adversarial_candidate_remains_delimited_untrusted_data",
    "test_score_parser_rejects_range_and_abstain_invariant",
    "test_refusal_malformed_provider_failure_and_private_reasoning_taxonomy",
    "test_artifact_persistence_failure_is_explicit_artifact_error",
    "test_l0_authority_cannot_be_overridden_by_l2_judge",
    "test_plan_is_timestamp_free_deterministic_and_explicitly_repeated",
    "test_pairwise_swap_is_one_logical_trial_with_two_order_variants",
    "test_judge_definition_is_authoritative_pairwise_order_policy",
    "test_cell_cannot_override_order_policy_and_unsupported_modes_fail_before_enqueue",
    "test_qualification_policy_is_versioned_all_required_checks_pass",
    "test_plan_digest_changes_for_every_frozen_calibration_dimension",
    "test_persisted_good_vs_biased_judge_e2e_and_phase_g_read_only",
    "test_judge_artifact_reload_digest_and_slot_identity_fail_closed",
    "test_provider_infra_only_lowers_coverage_and_cannot_dilute_capability_errors",
    "test_real_judge_requires_explicit_opt_in_before_enqueue_or_provider_call",
    "test_phase_g_to_phase_h_migration_preserves_experiment_evidence",
}


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


def verify_environment() -> ExitCode:
    missing = [tool for tool in ("uv", "git") if shutil.which(tool) is None]
    if missing:
        print(f"NOT_VERIFIED: required Gate H tools unavailable: {missing}")
        return ExitCode.NOT_VERIFIED
    if not os.environ.get("DATABASE_URL"):
        print("NOT_VERIFIED: DATABASE_URL is required for PostgreSQL Judge evidence")
        return ExitCode.NOT_VERIFIED
    return ExitCode.PASS


def verify_test_evidence() -> ExitCode:
    if not JUNIT.is_file():
        print("NOT_VERIFIED: pytest did not create Gate H JUnit evidence")
        return ExitCode.NOT_VERIFIED
    cases = ET.parse(JUNIT).getroot().findall(".//testcase")
    if not cases:
        print("NOT_VERIFIED: Gate H collected zero tests")
        return ExitCode.NOT_VERIFIED
    skipped = [
        case.attrib.get("name", "unknown") for case in cases if case.find("skipped") is not None
    ]
    present = {case.attrib.get("name", "") for case in cases}
    missing = CRITICAL_TESTS - present
    if skipped or missing or len(cases) < 20:
        print(
            f"NOT_VERIFIED: tests={len(cases)} skipped={skipped} missing_critical={sorted(missing)}"
        )
        return ExitCode.NOT_VERIFIED
    if not EVIDENCE.is_file():
        print("NOT_VERIFIED: persisted Good-vs-Biased evidence summary is unavailable")
        return ExitCode.NOT_VERIFIED
    try:
        evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        print("NOT_VERIFIED: Gate H evidence summary is unreadable")
        return ExitCode.NOT_VERIFIED
    required = {
        "evaluation_slot_count": 126,
        "good_status": "QUALIFIED_FOR_SUITE",
        "biased_status": "NOT_QUALIFIED",
    }
    if any(evidence.get(key) != value for key, value in required.items()):
        print(f"NOT_VERIFIED: Gate H evidence summary is incomplete: {evidence}")
        return ExitCode.NOT_VERIFIED
    for key in ("suite_digest", "definition_digest", "plan_digest", "report_digest"):
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(evidence.get(key))):
            print(f"NOT_VERIFIED: invalid {key}")
            return ExitCode.NOT_VERIFIED
    good = evidence["good_metrics"]
    biased = evidence["biased_metrics"]
    if not (
        good["position_consistency"] == 1.0
        and good["verbosity_bias_rate"] == 0.0
        and good["l0_overrides"] == 0
        and biased["position_consistency"] < good["position_consistency"]
        and biased["verbosity_bias_rate"] > good["verbosity_bias_rate"]
        and biased["l0_overrides"] == 0
    ):
        print("NOT_VERIFIED: bias, hierarchy, or qualification evidence is incomplete")
        return ExitCode.NOT_VERIFIED
    print(f"PASS: {len(cases)} Gate H tests recorded; critical set present; zero skipped")
    print(f"JUDGE_SUITE_DIGEST={evidence['suite_digest']}")
    print(f"JUDGE_DEFINITION_DIGEST={evidence['definition_digest']}")
    print(f"JUDGE_CALIBRATION_PLAN_DIGEST={evidence['plan_digest']}")
    print(f"JUDGE_REPORT_DIGEST={evidence['report_digest']}")
    print(f"GOOD_JUDGE_METRICS={json.dumps(good, sort_keys=True, separators=(',', ':'))}")
    print(f"BIASED_JUDGE_METRICS={json.dumps(biased, sort_keys=True, separators=(',', ':'))}")
    print("L0_AUTHORITY=FAIL+JudgePASS->FAIL;PASS+JudgeFAIL->PASS;overrides=0 PASS")
    print("PAIRWISE=original+swapped canonicalized as one logical trial PASS")
    print("LEAKAGE=answer-keys+gold+oracle+verifier+identity+private-reasoning absent PASS")
    print(
        "REAL_JUDGE_OPT_IN=service authorization+credential reference required before enqueue; "
        "fake cells keyless PASS"
    )
    print("REAL_JUDGE_SMOKE=NOT_RUN")
    return ExitCode.PASS


def verify_scope_and_contracts() -> bool:
    required = (
        ROOT / "src/harnesslab/judgelab/models.py",
        ROOT / "src/harnesslab/judgelab/runner.py",
        ROOT / "src/harnesslab/judgelab/report.py",
        ROOT / "alembic/versions/20260823_0004_phase_h_judgelab.py",
        ROOT / "docs/JUDGELAB.md",
    )
    forbidden = (
        ROOT / "src/harnesslab/analyst",
        ROOT / "src/harnesslab/langgraph",
    )
    if any(not path.is_file() for path in required) or any(path.exists() for path in forbidden):
        print("FAIL: required Phase H surface missing or Phase J scope detected")
        return False
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in (ROOT / "src/harnesslab/judgelab").glob("*.py")
    )
    required_tokens = (
        "ProviderAdapter",
        "JudgeEvidence",
        "REJECT_PRIVATE_REASONING_FIELDS",
        "OrderVariant",
        "QUALIFIED_FOR_SUITE",
    )
    if any(token not in source for token in required_tokens):
        print("FAIL: JudgeLab provider/evidence/qualification contract is incomplete")
        return False
    if "langgraph" in source.casefold():
        print("FAIL: out-of-scope LangGraph dependency detected")
        return False
    print("PASS: Phase I allowed; Phase H contracts intact; no Phase J analyst or LangGraph")
    return True


def main() -> int:
    environment = verify_environment()
    if environment is not ExitCode.PASS:
        return environment
    checks = (
        Check(
            "Alembic upgrade to Phase H head",
            ("uv", "run", "--locked", "alembic", "upgrade", "head"),
        ),
        Check(
            "Gate H tests",
            (
                "uv",
                "run",
                "--locked",
                "pytest",
                *PHASE_H_TESTS,
                f"--junitxml={JUNIT}",
                "-q",
            ),
        ),
        Check("Ruff lint", ("uv", "run", "--locked", "ruff", "check", ".")),
        Check("Ruff format", ("uv", "run", "--locked", "ruff", "format", "--check", ".")),
        Check("Mypy", ("uv", "run", "--locked", "mypy", "src", "tests", "scripts")),
        Check("Judge CLI", ("uv", "run", "--locked", "harnesslab", "judge", "--help")),
    )
    for check in checks:
        if not run(check):
            return ExitCode.FAIL
    evidence = verify_test_evidence()
    if evidence is not ExitCode.PASS:
        return evidence
    if not verify_scope_and_contracts():
        return ExitCode.FAIL
    print("\nGATE_H=PASS")
    return ExitCode.PASS


if __name__ == "__main__":
    raise SystemExit(main())
