from __future__ import annotations

from pathlib import Path

import pytest

from harnesslab.harness_lane.models import HarnessLaneOutcome
from harnesslab.sandbox.models import (
    VerifierLifecycleStage,
    VerifierLifecycleStageStatus,
)
from harnesslab.sandbox.runner import no_harnesslab_containers
from tests.verifier_lifecycle_handoff import exact_live_handoff


@pytest.mark.integration
async def test_claude_keyless_provider_uses_exact_live_workspace_verifier_handoff(
    tmp_path: Path,
) -> None:
    result = await exact_live_handoff(tmp_path / "live", run_id="keyless-live-handoff")

    lifecycle = result.evidence.verifier_lifecycle
    assert result.evidence.outcome is HarnessLaneOutcome.VERIFIED_PASS
    assert result.evidence.requested_model == "qwen3.8-max"
    assert result.evidence.observed_model == "qwen3.8-max"
    assert result.evidence.process_exit_code == 0
    assert result.evidence.changed_paths
    assert result.evidence.verifier_passed is True
    assert result.evidence.verifier_score == 1.0
    assert lifecycle is not None
    assert lifecycle.failure_subtype is None
    assert {item.stage for item in lifecycle.stages} == set(VerifierLifecycleStage)
    assert all(item.status is VerifierLifecycleStageStatus.COMPLETED for item in lifecycle.stages)
    assert await no_harnesslab_containers()


@pytest.mark.integration
async def test_claude_keyless_live_handoff_survives_recent_runtime_and_egress_teardown(
    tmp_path: Path,
) -> None:
    result = await exact_live_handoff(
        tmp_path / "pressure",
        run_id="keyless-pressure-handoff",
        preceding_lifecycle_pressure=True,
    )

    assert result.evidence.outcome is HarnessLaneOutcome.VERIFIED_PASS
    assert result.evidence.verifier_lifecycle is not None
    assert result.evidence.verifier_lifecycle.failure_subtype is None
    assert await no_harnesslab_containers()
