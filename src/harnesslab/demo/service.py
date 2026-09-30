from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from harnesslab.api.workbench_errors import WorkbenchAPIError
from harnesslab.api.workbench_models import RegressionCompareRequest
from harnesslab.api.workbench_service import (
    experiment_detail,
    regression_compare,
    run_detail,
    trace_detail,
)
from harnesslab.db.models.experiment import ExperimentRecord, ExperimentRunRecord
from harnesslab.demo.integrity import DemoBundle, DemoIntegrityError, load_bundle
from harnesslab.diagnosis.service import diagnose_experiment
from harnesslab.evidence.reader import (
    EvidenceReadError,
    load_verified_manifest,
    trusted_artifact_path,
)


def configured_bundle(roots: tuple[Path, ...]) -> tuple[DemoBundle, Path]:
    path_value = os.environ.get("HARNESSLAB_PUBLIC_DEMO_MANIFEST")
    expected_digest = os.environ.get("HARNESSLAB_PUBLIC_DEMO_DIGEST", "")
    if not path_value:
        raise WorkbenchAPIError(
            404, "DEMO_NOT_CONFIGURED", "No public demo evidence is configured."
        )
    path = Path(path_value)
    try:
        bundle = load_bundle(path, expected_digest)
        artifact_root = trusted_artifact_path(path.parent / "artifacts", roots)
    except (DemoIntegrityError, EvidenceReadError) as exc:
        raise WorkbenchAPIError(
            409,
            "ARTIFACT_INTEGRITY_ERROR",
            "Public demo evidence integrity failed. No replacement evidence was used.",
        ) from exc
    return bundle, artifact_root


async def verify_demo_records(
    session: AsyncSession, bundle: DemoBundle, artifact_root: Path
) -> None:
    ids = (bundle.baseline_id, bundle.candidate_id)
    if len(set(ids)) != 2 or any(not value.startswith(bundle.demo_id + "-") for value in ids):
        raise WorkbenchAPIError(
            409, "ARTIFACT_INTEGRITY_ERROR", "Public demo experiment identity mismatch."
        )
    records = (
        await session.scalars(
            select(ExperimentRunRecord).where(ExperimentRunRecord.experiment_id.in_(ids))
        )
    ).all()
    if {r.run_id for r in records} != {r.run_id for r in bundle.runs} or len(records) != len(
        bundle.runs
    ):
        raise WorkbenchAPIError(
            409, "ARTIFACT_INTEGRITY_ERROR", "Public demo run identity mismatch."
        )
    expected = {r.run_id: r for r in bundle.runs}
    for record in records:
        identity = expected[record.run_id]
        try:
            manifest = load_verified_manifest(record, (artifact_root,))
            if (
                record.experiment_id != identity.experiment_id
                or record.attempt != identity.attempt
                or record.evidence_digest != identity.digest
                or manifest.path.relative_to(artifact_root).as_posix() != identity.manifest
                or manifest.raw.get("verifier_passed") is not identity.verifier_passed
            ):
                raise EvidenceReadError("demo identity mismatch")
        except (EvidenceReadError, ValueError) as exc:
            raise WorkbenchAPIError(
                409, "ARTIFACT_INTEGRITY_ERROR", "Public demo run/artifact identity mismatch."
            ) from exc
    for experiment_id in ids:
        experiment = await session.get(ExperimentRecord, experiment_id)
        if experiment is None or experiment.plan_digest != bundle.plan_digests.get(experiment_id):
            raise WorkbenchAPIError(
                409, "ARTIFACT_INTEGRITY_ERROR", "Public demo plan identity mismatch."
            )


async def public_demo(session: AsyncSession, roots: tuple[Path, ...]) -> dict[str, Any]:
    bundle, root = configured_bundle(roots)
    await verify_demo_records(session, bundle, root)
    for experiment_id in (bundle.baseline_id, bundle.candidate_id):
        detail = await experiment_detail(session, experiment_id, roots)
        if detail.provenance != "FIXTURE_OFFLINE":
            raise WorkbenchAPIError(
                409, "ARTIFACT_INTEGRITY_ERROR", "Public demo provenance mismatch."
            )
    failed = await run_detail(session, bundle.failed_run_id, roots)
    if failed.experiment_id != bundle.baseline_id or failed.verifier_passed is not False:
        raise WorkbenchAPIError(
            409, "ARTIFACT_INTEGRITY_ERROR", "Public demo failure identity mismatch."
        )
    trace = await trace_detail(session, bundle.failed_run_id, roots)
    if trace.status != "REPORTED":
        raise WorkbenchAPIError(
            409, "ARTIFACT_INTEGRITY_ERROR", "Public demo trace is unavailable."
        )
    await diagnose_experiment(
        session,
        bundle.baseline_id,
        artifact_roots=roots,
        repository_root=Path(__file__).resolve().parents[3],
    )
    await regression_compare(
        session,
        RegressionCompareRequest(
            baseline_experiment_id=bundle.baseline_id,
            candidate_experiment_id=bundle.candidate_id,
            intent="GENERAL",
        ),
        roots,
    )
    return {
        "demo_id": bundle.demo_id,
        "generated_at": bundle.generated_at,
        "provenance": bundle.provenance,
        "public_demo_ready": True,
        "baseline_id": bundle.baseline_id,
        "candidate_id": bundle.candidate_id,
        "failed_run_id": bundle.failed_run_id,
        "run_count": len(bundle.runs),
        "artifact_file_count": len(bundle.files),
        "manifest_digest": os.environ.get("HARNESSLAB_PUBLIC_DEMO_DIGEST"),
        "historical_integrity_failures": bundle.historical_integrity_failures,
        "limitation": (
            "New keyless Fake fixtures with independent verifier results; "
            "no real Provider/model execution, benchmark ranking, or causal claim."
        ),
    }


async def public_artifact(
    session: AsyncSession, run_id: str, roots: tuple[Path, ...]
) -> tuple[bytes, str]:
    """Only fixture verifier stdout; digest-bound original bytes, no native transcript."""
    bundle, root = configured_bundle(roots)
    await verify_demo_records(session, bundle, root)
    identity = next((r for r in bundle.runs if r.run_id == run_id), None)
    if identity is None:
        raise WorkbenchAPIError(404, "NOT_FOUND", "No public artifact exists for this run.")
    relative = str(Path(identity.manifest).parent / "verifier" / "stdout.txt")
    expected = bundle.files.get(relative)
    if expected is None:
        raise WorkbenchAPIError(
            409, "ARTIFACT_INTEGRITY_ERROR", "Public verifier artifact is missing."
        )
    try:
        data = (root / relative).read_bytes()
    except OSError as exc:
        raise WorkbenchAPIError(
            409, "ARTIFACT_INTEGRITY_ERROR", "Public artifact is missing."
        ) from exc
    if "sha256:" + hashlib.sha256(data).hexdigest() != expected.sha256:
        raise WorkbenchAPIError(409, "ARTIFACT_INTEGRITY_ERROR", "Public artifact hash mismatch.")
    # load_bundle already verifies the exact file bytes, including this public allowlist member.
    return data, expected.sha256
