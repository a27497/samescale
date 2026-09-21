from __future__ import annotations

from pathlib import Path

import pytest

from harnesslab.contracts.common import NetworkPolicy
from harnesslab.episodes.service import import_codex_episode
from harnesslab.harness_lane.fake import FakeCodexBackend
from harnesslab.harness_lane.profile import CODEX_IMAGE, canonical_codex_profile
from harnesslab.harness_lane.prompt import CodexHarnessPrompt, render_codex_harness_prompt
from harnesslab.harness_lane.runner import CodexHarnessRunner
from harnesslab.sandbox.models import ImageIdentity

ROOT = Path(__file__).resolve().parents[1]


def render(addendum: str | None = None) -> CodexHarnessPrompt:
    return render_codex_harness_prompt(
        task_instruction="Fix the task.",
        task_digest="sha256:" + "1" * 64,
        workspace_input_digest="sha256:" + "2" * 64,
        context_digest=None,
        network_policy=NetworkPolicy.DENY,
        prompt_addendum=addendum,
    )


def test_default_prompt_preserves_frozen_identity_and_candidate_is_distinct() -> None:
    baseline = render()
    assert baseline.template_version == "codex-harness-v1"
    assert baseline.prompt_hash == (
        "sha256:6e52cc358a0495c5e17094972a590e8d4a69aacbd59deaa5c6a8aa43494dc2ea"
    )
    candidate = render("Check the public contract before editing.")
    assert candidate.text.startswith(baseline.text + "\n\nAdditional coding instructions:\n")
    assert candidate.template_version == "codex-harness-addendum-v1"
    assert candidate.prompt_hash != baseline.prompt_hash
    assert candidate.prompt_hash != render("Check the contract after editing.").prompt_hash


@pytest.mark.parametrize("value", ["", " \n\t", "a" * 4001, "before\x00after"])
def test_invalid_addendum_is_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="prompt addendum"):
        render(value)


@pytest.mark.asyncio
async def test_prompt_treatment_reaches_subject_and_episode_without_changing_task(
    tmp_path: Path,
) -> None:
    profile = canonical_codex_profile(
        ImageIdentity(reference=CODEX_IMAGE, image_id="sha256:" + "1" * 64)
    )
    runner = CodexHarnessRunner(artifact_root=tmp_path / "runs", runtime_root=tmp_path / "runtime")
    observations = []
    prompts = []
    task = ROOT / "tasks" / "micro-python-clamp" / "1.0.0"
    for label, addendum in (("current", None), ("candidate", "Check the public contract.")):
        backend = FakeCodexBackend()
        result = await runner.run(
            task, profile, backend=backend, run_id=label, prompt_addendum=addendum
        )
        episode = import_codex_episode(
            result.artifact_directory, tmp_path / "episodes", source_kind="synthetic"
        )
        assert episode.acceptance == "RECORDED_PASS"
        assert not episode.comparison_eligible
        assert not episode.execution_authorized
        observations.append(episode)
        prompts.append(backend.plans[0].prompt)
    current, candidate = observations
    assert current.task_digest == candidate.task_digest
    assert current.workspace_input_digest == candidate.workspace_input_digest
    assert current.workspace_output_digest == candidate.workspace_output_digest
    assert current.profile_identity == candidate.profile_identity
    assert current.prompt_identity != candidate.prompt_identity
    assert current.setup_identity != candidate.setup_identity
    assert (
        prompts[1] == prompts[0] + "\n\nAdditional coding instructions:\nCheck the public contract."
    )
