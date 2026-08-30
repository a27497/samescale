from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from harnesslab.core.config import Settings
from harnesslab.db.session import create_engine, create_session_factory
from harnesslab.release.throughput_qualification import qualify_v6_throughput_r2
from harnesslab.release.v6 import build_v6_plan, v6_throughput_r2_profiles

EXPECTED_BASE_SHA = "00bea2eab9e2b1d493bad8f1de594e6a740b7d63"
EXPECTED_V6_CONTROL_SHA256 = "52318dd45e843611840a046f7f85670941281026d10f56b36fe0df421e69f42f"
EXPECTED_V5_INCIDENT_SHA256 = "02f1b49092b2c592231e132fdcc97135f876d6694f513f2bc0b49897ad8e8cac"


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _git_head(root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _implementation_digests(root: Path) -> dict[str, str]:
    paths = (
        "src/harnesslab/experiment/dispatch.py",
        "src/harnesslab/release/throughput_qualification.py",
        "src/harnesslab/release/v6.py",
        "scripts/qualify_kb3_v6_throughput_r2.py",
    )
    return {path: _sha256(root / path) for path in paths}


async def _build(root: Path, database_url: str, repetitions: int) -> dict[str, Any]:
    head = _git_head(root)
    if head != EXPECTED_BASE_SHA:
        raise RuntimeError("R2 qualification is not based on the accepted V6 head")
    v6_control = root / "release/core-real-matrix-v6-control.json"
    v5_incident = root / "release/kb3-v5-attempt1-scheduling-incident.json"
    if _sha256(v6_control) != "sha256:" + EXPECTED_V6_CONTROL_SHA256:
        raise RuntimeError("accepted V6 control artifact was mutated")
    if _sha256(v5_incident) != "sha256:" + EXPECTED_V5_INCIDENT_SHA256:
        raise RuntimeError("frozen V5 incident artifact was mutated")
    plan = build_v6_plan(root, {})
    engine = create_engine(Settings.without_dotenv(database_url=database_url))
    factory = create_session_factory(engine)
    started = datetime.now(UTC)
    try:
        qualification = await qualify_v6_throughput_r2(
            plan,
            v6_throughput_r2_profiles(),
            factory,
            repetitions=repetitions,
        )
    finally:
        await engine.dispose()
    finished = datetime.now(UTC)
    return {
        "schema_version": 1,
        "phase": "K_B3_V6_PRODUCTION_THROUGHPUT_R2",
        "evidence_class": qualification.evidence_class,
        "accepted_v6_base_sha": EXPECTED_BASE_SHA,
        "accepted_v6_control_sha256": _sha256(v6_control),
        "frozen_v5_incident_sha256": _sha256(v5_incident),
        "qualification_started_at": started.isoformat(),
        "qualification_finished_at": finished.isoformat(),
        "qualification_implementation_digests": _implementation_digests(root),
        "host": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
        },
        "plan": {
            "experiment_id": plan.experiment_id,
            "plan_digest": plan.digest,
            "schedule_seed": plan.schedule_seed,
            "block_count": len(plan.schedule_blocks),
            "logical_slot_count": len(plan.run_slots),
            "scheduling_policy": plan.scheduling_policy,
        },
        "qualification": qualification.model_dump(mode="json"),
        "resource_safety_thresholds": {
            "cpu_average_max_fraction": 0.8,
            "memory_used_max_fraction": 0.9,
            "swap_growth_max_mib": 64,
            "load_1m_max_cpu_count_multiple": 1.25,
            "database_connection_growth_max": "global_concurrency+3",
            "process_fd_growth_max": "global_concurrency*8+32",
            "host_allocated_fd_growth_max": 4096,
            "container_peak_max": "max_harness_concurrency",
        },
        "scientific_controls_unchanged": {
            "cells": True,
            "tasks": True,
            "repeat_count": True,
            "judge_design": True,
            "scoring": True,
            "budgets": True,
            "paired_lane": True,
            "ablation": True,
            "provider_concurrency_caps": True,
            "runtime_adaptive_concurrency": False,
        },
        "limitations": [
            "Provider/model outputs are deterministic local fixtures, not real model responses.",
            (
                "Harness containers exercise real image startup, security limits, filesystem "
                "I/O, and cleanup but not provider-backed CLI inference."
            ),
            (
                "Host telemetry is system-wide and may include unrelated local services "
                "present during the bounded trials."
            ),
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("release/core-real-matrix-v6-throughput-r2.json"),
    )
    args = parser.parse_args()
    if not args.database_url:
        raise RuntimeError("DATABASE_URL is required")
    root = args.repository_root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    if output.exists():
        raise FileExistsError(f"append-only R2 qualification already exists: {output}")
    artifact = asyncio.run(_build(root, args.database_url, args.repetitions))
    output.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"FROZEN={output}")
    print(f"DIGEST={_sha256(output)}")
    print(f"SELECTED={artifact['qualification']['selection']['selected_profile_id']}")


if __name__ == "__main__":
    main()
