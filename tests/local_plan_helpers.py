"""Synthetic prior evidence for Phase-1 contract tests, never real verifier observations."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from harnesslab.custom_eval.models import canonical_digest
from harnesslab.tasks.models import (
    CheckResult,
    EvidenceAsset,
    EvidenceManifest,
    OutcomeCategory,
    TaskValidationResult,
    VerifierExecutionResult,
)
from harnesslab.tasks.package import TaskPackage, digest_tree
from harnesslab.tasks.quality import (
    CUSTOM_TECHNICAL_CHECKS,
    QualificationCheck,
    QualificationEvidence,
    TaskQualityMetadata,
    TaskSourceKind,
    qualify_task,
)

TOKEN = "local-operator-test-placeholder-1234567890"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Origin": "http://localhost"}


def prepare_policy(root: Path) -> tuple[Path, Path]:
    package_root = root / "sources" / "phase1-fixture" / "1.0.0"
    for name in ("workspace", "verifier", "oracle"):
        (package_root / name).mkdir(parents=True)
    (package_root / "instruction.md").write_text(
        "Synthetic Phase-1 planning fixture; implement ANSWER=42."
    )
    (package_root / "workspace" / "answer.py").write_text("ANSWER = 0\n")
    (package_root / "oracle" / "answer.py").write_text("ANSWER = 42\n")
    (package_root / "verifier" / "verify.py").write_text(
        "raise AssertionError('Phase 1 must never execute a Verifier')\n"
    )
    manifest = {
        "schema_version": 1,
        "id": "phase1-fixture",
        "version": "1.0.0",
        "domain": "synthetic-phase1-contract-test",
        "lane_support": ["H"],
        "verifier": {"kind": "python", "version": "1", "entrypoint": "verifier/verify.py"},
        "oracle": {"path": "oracle"},
        "budget": {"timeout_seconds": 90, "network_policy": "deny"},
    }
    (package_root / "task.yaml").write_text(yaml.safe_dump(manifest))
    package = TaskPackage.load(package_root)
    evidence = EvidenceAsset(
        kind="hidden_verifier",
        path=package.manifest.verifier.entrypoint,
        digest=package.verifier_digest,
    )

    def result(passed: bool) -> VerifierExecutionResult:
        return VerifierExecutionResult(
            passed=passed,
            score=int(passed),
            checks=(
                CheckResult(name="synthetic-contract-fixture", passed=passed, score=int(passed)),
            ),
            summary="Synthetic fixture only; no Verifier was run",
            category=OutcomeCategory.SUBJECT_RESULT,
            exit_code=0,
            duration_ms=0,
            stdout_digest=canonical_digest({"synthetic_stdout": passed}),
            stderr_digest=canonical_digest({"synthetic_stderr": passed}),
        )

    def observation(passed: bool) -> EvidenceManifest:
        return EvidenceManifest(
            task_id=package.definition.id,
            task_version=package.definition.version,
            task_digest=package.definition.content_digest,
            workspace_digest=digest_tree(package.oracle_path)
            if passed
            else package.definition.workspace.digest,
            verifier=evidence,
            result=result(passed),
            run_kind="oracle" if passed else "baseline",
        )

    validation = TaskValidationResult(
        valid=True,
        task_id=package.definition.id,
        task_version=package.definition.version,
        task_digest=package.definition.content_digest,
        baseline=observation(False),
        oracle=observation(True),
    )
    quality = TaskQualityMetadata.from_package(package, source_kind=TaskSourceKind.CUSTOM)
    identities = {
        QualificationCheck.PACKAGE_VALID: package.definition.content_digest,
        QualificationCheck.BASELINE_FAILS: canonical_digest(
            validation.baseline.model_dump(mode="json")
        ),
        QualificationCheck.ORACLE_PASSES: canonical_digest(
            validation.oracle.model_dump(mode="json")
        ),
    }
    q = qualify_task(
        quality,
        qualification_id="synthetic-phase1-prior-evidence",
        evidence=tuple(
            QualificationEvidence(
                check=c,
                evidence_identity=identities.get(
                    c, canonical_digest({"synthetic_isolation": c.value})
                ),
            )
            for c in sorted(CUSTOM_TECHNICAL_CHECKS)
        ),
    )
    qualification_path = root / "qualification.json"
    validation_path = root / "validation.json"
    qualification_path.write_text(q.model_dump_json())
    validation_path.write_text(validation.model_dump_json())
    policy = {
        "schema_version": 1,
        "source_roots": {"trusted": str(root / "sources")},
        "managed_store": str(root / "managed"),
        "runtime_images": {"harnesslab-phase-e-codex:0.149.0": "sha256:" + "a" * 64},
        "admissions": [
            {
                "task_identity": package.definition.content_digest,
                "qualification_file": str(qualification_path),
                "qualification_identity": q.qualification_identity,
                "validation_file": str(validation_path),
                "validation_identity": canonical_digest(validation.model_dump(mode="json")),
            }
        ],
    }
    policy_path = root / "policy.json"
    policy_path.write_text(json.dumps(policy))
    for owned_file in (policy_path, qualification_path, validation_path):
        owned_file.chmod(0o600)
    return policy_path, package_root


def request() -> dict[str, object]:
    return {
        "name": "Phase-1 single Codex plan",
        "task_reference": "phase1-fixture@1.0.0",
        "provider_profile_id": "gpt56-relay-gpt56-responses",
        "harness_profile_id": "codex-gpt56-high",
        "budget": {"wall_time_seconds": 90, "output_tokens_estimate": 1000, "cost_budget_usd": 1.0},
    }
