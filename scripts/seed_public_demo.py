"""Create once, never regenerate: new keyless public-demo identities and protected bytes."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from sqlalchemy import select

from harnesslab.core.config import get_settings
from harnesslab.db.models.experiment import ExperimentRunRecord
from harnesslab.db.session import create_engine, create_session_factory
from harnesslab.demo.fixtures import demo_plan
from harnesslab.demo.integrity import DemoBundle, DemoRunIdentity
from harnesslab.evidence.protection import snapshot_tree
from harnesslab.evidence.reader import load_verified_manifest
from harnesslab.experiment.executor import ExperimentRunExecutor
from harnesslab.experiment.queue import enqueue_plan


async def seed(destination: Path, runtime: Path) -> None:
    settings = get_settings()
    parsed = urlsplit(settings.database_url_value)
    if (
        settings.environment != "qa"
        or parsed.hostname != "127.0.0.1"
        or parsed.port != 55471
        or parsed.path != "/samescale_qa"
    ):
        raise SystemExit("This recovery seed requires the dedicated keyless QA database")
    if destination.exists() or runtime.exists():
        raise SystemExit("Refusing to reuse an existing artifact/runtime identity")
    # Distinct from the old test root and all tracked/frozen repository evidence.
    repository = Path(__file__).resolve().parents[1]
    if destination.resolve().is_relative_to(repository) or runtime.resolve().is_relative_to(
        repository
    ):
        raise SystemExit("Demo storage must be outside the repository/test workspace")
    destination.mkdir(parents=True)
    artifacts = destination / "artifacts"
    artifacts.mkdir()
    runtime.mkdir(parents=True)
    now = datetime.now(UTC)
    demo_id = f"public-demo-{now:%Y%m%d}-{uuid4().hex[:12]}"
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    plans: dict[str, str] = {}
    try:
        for candidate in (False, True):
            experiment_id = demo_id + ("-candidate" if candidate else "-baseline")
            plan, bindings = demo_plan(
                repository, experiment_id, artifacts, runtime, candidate=candidate
            )
            async with factory() as session, session.begin():
                await enqueue_plan(session, plan)
            completed = await ExperimentRunExecutor(
                repository_root=repository,
                session_factory=factory,
                bindings=bindings,
                owner="public-demo-keyless-seed",
            ).run_until_idle(experiment_id)
            if len(completed) != len(plan.run_slots):
                raise RuntimeError("New public demo did not complete its planned runs")
            plans[experiment_id] = plan.digest
        async with factory() as session:
            records = (
                await session.scalars(
                    select(ExperimentRunRecord)
                    .where(ExperimentRunRecord.experiment_id.in_(plans))
                    .order_by(ExperimentRunRecord.run_id)
                )
            ).all()
            identities: list[DemoRunIdentity] = []
            for record in records:
                manifest = load_verified_manifest(record, (artifacts,))
                passed = manifest.raw.get("verifier_passed")
                if not isinstance(passed, bool):
                    raise RuntimeError("Missing independent verifier verdict")
                identities.append(
                    DemoRunIdentity(
                        run_id=record.run_id,
                        experiment_id=record.experiment_id,
                        attempt=record.attempt,
                        manifest=manifest.path.relative_to(artifacts).as_posix(),
                        digest=record.evidence_digest,
                        verifier_passed=passed,
                    )
                )
        baseline = demo_id + "-baseline"
        failed = next(
            r.run_id for r in identities if r.experiment_id == baseline and not r.verifier_passed
        )
        bundle = DemoBundle(
            demo_id=demo_id,
            generated_at=now,
            baseline_id=baseline,
            candidate_id=demo_id + "-candidate",
            failed_run_id=failed,
            plan_digests=plans,
            runs=tuple(identities),
            files=snapshot_tree(artifacts),
            historical_integrity_failures=(
                "phase-i-matrix-baseline",
                "phase-i-matrix-candidate",
                "phase-i-matrix-multi-task",
            ),
        )
        manifest_path = destination / "public-demo.json"
        manifest_path.write_text(bundle.model_dump_json(indent=2) + "\n")
        digest = "sha256:" + hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        for path in destination.rglob("*"):
            path.chmod(0o555 if path.is_dir() else 0o444)
        destination.chmod(0o555)
        print(
            json.dumps(
                {
                    "demo_id": demo_id,
                    "manifest": str(manifest_path),
                    "manifest_digest": digest,
                    "runs": len(identities),
                    "files": len(bundle.files),
                },
                indent=2,
            )
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--runtime", required=True, type=Path)
    args = parser.parse_args()
    asyncio.run(seed(args.destination, args.runtime))
