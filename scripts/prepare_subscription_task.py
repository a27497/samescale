"""Admit one copied real engineering task using deterministic hidden Docker checks.

No Subject/Codex/model is run. No image build/pull or database access is performed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import tempfile
from pathlib import Path

from harnesslab.local_execution.sandbox import PinnedVerifierSandbox
from harnesslab.local_plans.service import local_image_identity
from harnesslab.local_plans.tasks import (
    LocalImport,
    import_task,
    inspect_task,
    load_policy,
    no_links,
)
from harnesslab.registry.models import canonical_digest
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


async def prepare(root: Path) -> dict[str, object]:
    no_links(root)
    if (
        root.exists()
        or not root.is_relative_to(Path(tempfile.gettempdir()).resolve())
        or root == Path(tempfile.gettempdir()).resolve()
    ):
        raise ValueError("Use a new isolated output directory outside the checkout")
    image = local_image_identity(SANDBOX_IMAGE)
    if image is None:
        raise ValueError("Existing pinned hidden-verifier image required; no build/pull")
    root.mkdir(mode=0o700, parents=True)
    source = ROOT / "tasks/core-python-deduplicate/1.0.2"
    destination = root / "sources/core-python-deduplicate/1.0.2"
    shutil.copytree(source, destination)
    package = TaskPackage.load(destination)
    if digest_tree(source) != package.definition.content_digest:
        raise ValueError("Source changed while copying")
    observations: list[EvidenceManifest] = []
    receipt_refs: list[dict[str, object]] = []
    workspace_isolation: list[str] = []
    for index, oracle in enumerate((False, True, False, True)):
        materialized = package.materialize()
        try:
            if oracle:
                package.apply_oracle(materialized)
            names = sorted(
                p.relative_to(materialized.root).as_posix()
                for p in materialized.root.rglob("*")
                if p.is_file()
            )
            if any(x.startswith(("verifier/", "oracle/")) for x in names):
                raise ValueError("Hidden assets leaked into Subject materialization")
            workspace_isolation.append(
                canonical_digest(
                    {"files": names, "workspace_digest": digest_tree(materialized.workspace)}
                )
            )
            run_id = f"phase25-admission-{index}"
            sandbox = PinnedVerifierSandbox(
                image_id=image,
                run_id=run_id,
                runtime_root=root / "runtime",
                artifact_root=root / "verifier-artifacts",
            )
            observed = await sandbox.run_hidden_verifier_workspace(package, materialized.workspace)
            manifest = observed.run.manifest
            report = VerifierReport.model_validate_json(observed.run.stdout)
            if (
                not report.checks
                or observed.passed != oracle
                or not manifest.cleanup_verified
                or manifest.workspace_input_digest != manifest.workspace_output_digest
            ):
                raise ValueError(
                    "Nonzero deterministic baseline-fail/oracle-pass and cleanup required"
                )
            # PinnedVerifierSandbox enforces readonly workspace/verifier, network none,
            # separate UID/PID, no Docker socket and bounded resources before execution.
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
            receipt_refs.append(
                {
                    "run_id": run_id,
                    "passed": observed.passed,
                    "checks": len(report.checks),
                    "stdout_digest": manifest.stdout.digest,
                    "manifest_identity": canonical_digest(manifest.model_dump(mode="json")),
                    "security_identity": canonical_digest(
                        manifest.security.model_dump(mode="json")
                    ),
                    "cleanup_verified": manifest.cleanup_verified,
                }
            )
        finally:
            materialized.cleanup()
    if (
        observations[0].result.checks != observations[2].result.checks
        or observations[1].result.checks != observations[3].result.checks
    ):
        raise ValueError("Repeated deterministic checks drifted")
    validation = TaskValidationResult(
        valid=True,
        task_id=package.definition.id,
        task_version=package.definition.version,
        task_digest=package.definition.content_digest,
        baseline=observations[0],
        oracle=observations[1],
    )
    bindings = {
        QualificationCheck.PACKAGE_VALID: package.definition.content_digest,
        QualificationCheck.BASELINE_FAILS: canonical_digest(
            observations[0].model_dump(mode="json")
        ),
        QualificationCheck.ORACLE_PASSES: canonical_digest(observations[1].model_dump(mode="json")),
        QualificationCheck.WORKSPACE_ISOLATION: canonical_digest(workspace_isolation),
        QualificationCheck.HIDDEN_ASSETS_ISOLATED: canonical_digest(receipt_refs),
    }
    qualification = qualify_task(
        TaskQualityMetadata.from_package(
            package,
            source_kind=TaskSourceKind.CUSTOM,
            source_revision="3cbefb6731d07c6eddb3463c895eeef60b2f0fd9",
        ),
        qualification_id="phase25-real-task-admission",
        evidence=tuple(
            QualificationEvidence(check=c, evidence_identity=bindings[c])
            for c in sorted(CUSTOM_TECHNICAL_CHECKS)
        ),
    )
    qpath, vpath = root / "qualification.json", root / "validation.json"
    qpath.write_text(qualification.model_dump_json(indent=2))
    vpath.write_text(validation.model_dump_json(indent=2))
    policy = root / "task-policy.json"
    policy.write_text(
        json.dumps(
            {
                "source_roots": {"trusted": str(root / "sources")},
                "managed_store": str(root / "managed"),
                "admissions": [
                    {
                        "task_identity": package.definition.content_digest,
                        "qualification_file": str(qpath),
                        "qualification_identity": qualification.qualification_identity,
                        "validation_file": str(vpath),
                        "validation_identity": canonical_digest(validation.model_dump(mode="json")),
                    }
                ],
            }
        )
    )
    for path in (qpath, vpath, policy):
        path.chmod(0o600)
    # Reuse actual Phase-1 import/qualification gates, not a hand-built ready result.
    import os

    old = os.environ.get("HARNESSLAB_LOCAL_TASK_POLICY")
    os.environ["HARNESSLAB_LOCAL_TASK_POLICY"] = str(policy)
    try:
        imported = import_task(
            load_policy(),
            LocalImport(root_id="trusted", relative_path="core-python-deduplicate/1.0.2"),
        )
        inspection, _ = inspect_task(load_policy(), imported.reference)
        if not inspection.eligible_for_planning:
            raise ValueError("Existing task admission rejected the real observations")
    finally:
        if old is None:
            os.environ.pop("HARNESSLAB_LOCAL_TASK_POLICY", None)
        else:
            os.environ["HARNESSLAB_LOCAL_TASK_POLICY"] = old
    receipt: dict[str, object] = {
        "source": "ACTUAL_DETERMINISTIC_DOCKER_TASK_ADMISSION",
        "task_reference": inspection.reference,
        "task_identity": package.definition.content_digest,
        "workspace_identity": inspection.workspace_identity,
        "verifier_identity": inspection.verifier_identity,
        "oracle_identity": inspection.oracle_identity,
        "qualification_identity": qualification.qualification_identity,
        "validation_identity": canonical_digest(validation.model_dump(mode="json")),
        "image_identity": image,
        "observations": receipt_refs,
        "eligible_for_planning": True,
        "real_subject_execution": "NOT_RUN",
        "model_requests": 0,
        "official_qualification_changed": False,
    }
    (root / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    receipt = asyncio.run(prepare(args.output))
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
