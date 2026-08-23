from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from harnesslab.contracts.common import NetworkPolicy
from harnesslab.multi_harness.models import HarnessKind

CLAUDE_PROMPT_VERSION = "claude-harness-v1"
DEEPSEEK_PROMPT_VERSION = "deepseek-headless-v1"


@dataclass(frozen=True)
class MultiHarnessPrompt:
    template_version: str
    text: str
    prompt_hash: str


def render_harness_prompt(
    harness: HarnessKind,
    *,
    task_instruction: str,
    task_digest: str,
    workspace_input_digest: str,
    context_digest: str | None,
    network_policy: NetworkPolicy,
) -> MultiHarnessPrompt:
    version = (
        CLAUDE_PROMPT_VERSION if harness is HarnessKind.CLAUDE_CODE else DEEPSEEK_PROMPT_VERSION
    )
    context_line = (
        "Subject-visible context is mounted read-only at /context."
        if context_digest is not None
        else "No subject-visible context is provided."
    )
    text = "\n".join(
        (
            f"You are executing one HarnessLab coding task through {harness.value}.",
            "",
            "Task instruction:",
            task_instruction.strip(),
            "",
            "Working directory: /workspace",
            context_line,
            "Modify only files inside /workspace.",
            f"Subject tool network policy: {network_policy.value}.",
            "Do not attempt network access when the policy is deny.",
            "HarnessLab Hidden Verifier is authoritative; your own success report is not.",
            "No verifier or oracle details are available to you.",
        )
    )
    canonical = json.dumps(
        {
            "template_version": version,
            "text": text,
            "task_digest": task_digest,
            "workspace_input_digest": workspace_input_digest,
            "context_digest": context_digest,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    digest = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
    return MultiHarnessPrompt(version, text, digest)
