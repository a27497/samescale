from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from harnesslab.db.models.local_execution import LocalExecutionResultRecord
from harnesslab.episodes.service import Episode, read_codex_episode
from harnesslab.harness_lane.models import HarnessLaneEvidence
from harnesslab.local_execution.models import ExecutionAuthorization
from harnesslab.local_execution.policy import load_execution_policy
from harnesslab.local_plans.tasks import fail, no_links
from harnesslab.registry.models import canonical_digest


def result_document(
    auth: ExecutionAuthorization,
    run_id: str,
    status: str,
    reason: str,
    *,
    episode: Episode | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": 1,
        "plan_id": auth.plan_id,
        "plan_digest": auth.plan_digest,
        "authorization_digest": auth.digest,
        "run_slot_digest": auth.run_slot_digest,
        "run_id": run_id,
        "attempt_number": 1,
        "mode": "FAKE_CODEX",
        "status": status,
        "reason_code": reason,
        "acceptance": (
            episode.acceptance
            if episode and status in {"VERIFIED_PASS", "VERIFIED_FAIL"}
            else "NOT_VERIFIED"
        ),
        "episode_id": episode.identity if episode else None,
        "episode": episode.model_dump(mode="json") if episode else None,
        "model_calls": 0,
        "model_cost_usd": 0,
        "real_codex_runtime": "NOT_PROBED",
        "comparison_eligible": False,
    }
    result["digest"] = canonical_digest(result)
    return result


def read_bound_episode(root: Path, auth: ExecutionAuthorization, run_id: str) -> Episode:
    no_links(root)
    episode = read_codex_episode(root, source_kind="synthetic")
    evidence = HarnessLaneEvidence.model_validate_json((root / "manifest.json").read_bytes())
    if (
        episode.run_id != run_id
        or evidence.plan_profile_identity != auth.plan_digest
        or evidence.plan_harness_config_identity != auth.digest
    ):
        raise ValueError("Episode does not bind the authorized attempt")
    if (
        episode.acceptance in {"RECORDED_PASS", "RECORDED_FAIL"}
        and episode.verifier_check_count == 0
    ):
        raise ValueError("Zero verifier checks are not acceptance")
    return episode


def validate_result(
    row: LocalExecutionResultRecord, auth: ExecutionAuthorization
) -> dict[str, Any]:
    try:
        result = row.document
        if (
            result["digest"] != row.digest
            or row.digest != canonical_digest({k: v for k, v in result.items() if k != "digest"})
            or result["run_id"] != row.run_id
            or result["authorization_digest"] != auth.digest
            or result["plan_id"] != auth.plan_id
            or result["plan_digest"] != auth.plan_digest
            or result["run_slot_digest"] != auth.run_slot_digest
        ):
            raise ValueError("result binding failed")
        if result["episode"] is not None:
            root = load_execution_policy().artifact_root / row.run_id
            observed = read_bound_episode(root, auth, row.run_id)
            if (
                observed.model_dump(mode="json") != result["episode"]
                or observed.identity != result["episode_id"]
                or (
                    result["status"] in {"VERIFIED_PASS", "VERIFIED_FAIL"}
                    and observed.acceptance != result["acceptance"]
                )
            ):
                raise ValueError("episode identity failed")
        elif (
            result["status"] in {"VERIFIED_PASS", "VERIFIED_FAIL"}
            or result["acceptance"] != "NOT_VERIFIED"
        ):
            raise ValueError("missing acceptance evidence")
        expected = {"VERIFIED_PASS": "RECORDED_PASS", "VERIFIED_FAIL": "RECORDED_FAIL"}.get(
            result["status"], "NOT_VERIFIED"
        )
        if (
            result["acceptance"] != expected
            or result["mode"] != "FAKE_CODEX"
            or result["model_calls"] != 0
            or result["model_cost_usd"] != 0
        ):
            raise ValueError("Result authority or zero-cost scope failed")
        return result
    except (OSError, ValueError, KeyError, TypeError):
        raise fail(
            "EXECUTION_EVIDENCE_INTEGRITY_ERROR",
            "Saved execution evidence is missing, altered or inconsistent. "
            "No replacement was produced.",
            409,
        ) from None


def persist_completion(root: Path, result: dict[str, Any]) -> None:
    # Exclusive append, fsync, atomic rename. Recovery may import only this sealed result;
    # unsealed/partial files can never trigger another subject invocation.
    import os

    target = root / (result["run_id"] + ".result.json")
    temporary = root / (result["run_id"] + ".result.tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, sort_keys=True))
        stream.flush()
        os.fsync(stream.fileno())
    if target.exists():
        raise ValueError("completion already sealed")
    temporary.rename(target)
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
