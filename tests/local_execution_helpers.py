"""Owned keyless fixture setup; behavioral admission comes from real Docker verifiers."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from harnesslab.local_execution.sandbox import PinnedVerifierSandbox
from harnesslab.local_plans.service import local_image_identity
from harnesslab.registry.models import canonical_digest
from harnesslab.sandbox.models import IsolatedVerifierResult
from harnesslab.sandbox.runner import SANDBOX_IMAGE
from harnesslab.tasks.models import (
    EvidenceAsset,
    EvidenceManifest,
    OutcomeCategory,
    TaskValidationResult,
    VerifierExecutionResult,
    VerifierReport,
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

ROOT = Path(__file__).resolve().parents[1]


async def prepare_execution_fixture(
    root: Path, *, scenario: str = "solve"
) -> tuple[Path, Path, Path]:
    package_path = root / "sources/micro-python-clamp/1.0.2"
    shutil.copytree(ROOT / "tasks/micro-python-clamp/1.0.2", package_path)
    package = TaskPackage.load(package_path)
    image = local_image_identity(SANDBOX_IMAGE)
    codex_image = local_image_identity("harnesslab-phase-e-codex:0.149.0")
    if image is None or codex_image is None:
        raise RuntimeError("Existing pinned local test images required; do not build or pull")
    sandbox = PinnedVerifierSandbox(
        image_id=image,
        run_id="admission-test",
        runtime_root=root / "admission/runtime",
        artifact_root=root / "admission/artifacts",
    )
    observations = []
    for oracle in (False, True):
        materialized = package.materialize()
        try:
            if oracle:
                package.apply_oracle(materialized)
            observed: IsolatedVerifierResult = await sandbox.run_hidden_verifier_workspace(
                package, materialized.workspace, run_id="unused"
            )
            assert observed.passed is oracle
            manifest = observed.run.manifest
            report = VerifierReport.model_validate_json(observed.run.stdout)
            result = VerifierExecutionResult(
                passed=report.passed,
                score=report.score,
                checks=report.checks,
                summary=report.summary,
                category=OutcomeCategory.SUBJECT_RESULT,
                exit_code=manifest.exit_code,
                duration_ms=manifest.duration_ms,
                stdout_digest=manifest.stdout.digest,
                stderr_digest=manifest.stderr.digest,
            )
            observations.append(
                EvidenceManifest(
                    task_id=package.definition.id,
                    task_version=package.definition.version,
                    task_digest=package.definition.content_digest,
                    workspace_digest=digest_tree(materialized.workspace),
                    verifier=EvidenceAsset(
                        kind="hidden_verifier",
                        path=package.manifest.verifier.entrypoint,
                        digest=package.verifier_digest,
                    ),
                    result=result,
                    run_kind="oracle" if oracle else "baseline",
                )
            )
            # New isolated verifier identity for the second admission observation.
            sandbox.verifier_run_id = "admission-test-oracle-verifier"
        finally:
            materialized.cleanup()
    validation = TaskValidationResult(
        valid=True,
        task_id=package.definition.id,
        task_version=package.definition.version,
        task_digest=package.definition.content_digest,
        baseline=observations[0],
        oracle=observations[1],
    )
    identities = {
        QualificationCheck.PACKAGE_VALID: package.definition.content_digest,
        QualificationCheck.BASELINE_FAILS: canonical_digest(
            observations[0].model_dump(mode="json")
        ),
        QualificationCheck.ORACLE_PASSES: canonical_digest(observations[1].model_dump(mode="json")),
    }
    qualification = qualify_task(
        TaskQualityMetadata.from_package(package, source_kind=TaskSourceKind.CUSTOM),
        qualification_id="isolated-phase2-fixture",
        evidence=tuple(
            QualificationEvidence(
                check=c,
                evidence_identity=identities.get(
                    c,
                    canonical_digest(
                        {"observed": "docker-hidden-assets-isolated", "check": c.value}
                    ),
                ),
            )
            for c in sorted(CUSTOM_TECHNICAL_CHECKS)
        ),
    )
    evidence_root = root / "admission"
    qualification_path = evidence_root / "qualification.json"
    validation_path = evidence_root / "validation.json"
    qualification_path.write_text(qualification.model_dump_json())
    validation_path.write_text(validation.model_dump_json())
    policy = {
        "source_roots": {"trusted": str(root / "sources")},
        "managed_store": str(root / "managed"),
        "runtime_images": {"harnesslab-phase-e-codex:0.149.0": codex_image},
        "admissions": [
            {
                "task_identity": package.definition.content_digest,
                "qualification_file": str(qualification_path),
                "qualification_identity": qualification.qualification_identity,
                "validation_file": str(validation_path),
                "validation_identity": canonical_digest(validation.model_dump(mode="json")),
            }
        ],
    }
    policy_path = root / "task-policy.json"
    policy_path.write_text(json.dumps(policy))
    execution_path = root / "execution-policy.json"
    execution_path.write_text(
        json.dumps(
            {
                "artifact_root": str(root / "worker/artifacts"),
                "runtime_root": str(root / "worker/runtime"),
                "subject_image_identity": image,
                "verifier_image_identity": image,
                "fixture_task_identities": [package.definition.content_digest],
                "scenario": scenario,
                "lease_seconds": 5,
            }
        )
    )
    for path in (policy_path, execution_path, qualification_path, validation_path):
        path.chmod(0o600)
    return policy_path, execution_path, package_path
