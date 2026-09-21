from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from harnesslab.contracts.common import NetworkPolicy

PROMPT_TEMPLATE_VERSION = "codex-harness-v1"


@dataclass(frozen=True)
class CodexHarnessPrompt:
    template_version: str
    text: str
    prompt_hash: str


def render_codex_harness_prompt(
    *,
    task_instruction: str,
    task_digest: str,
    workspace_input_digest: str,
    context_digest: str | None,
    network_policy: NetworkPolicy,
    prompt_addendum: str | None = None,
) -> CodexHarnessPrompt:
    if prompt_addendum is not None and (
        not prompt_addendum.strip() or len(prompt_addendum) > 4000 or "\x00" in prompt_addendum
    ):
        raise ValueError("prompt addendum must contain 1-4000 characters without NUL")
    context_line = (
        "Subject-visible context is mounted read-only at /context."
        if context_digest is not None
        else "No subject-visible context is provided."
    )
    text = "\n".join(
        (
            "You are executing one HarnessLab coding task inside the Codex H-Lane.",
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
    template_version = PROMPT_TEMPLATE_VERSION
    if prompt_addendum is not None:
        text += "\n\nAdditional coding instructions:\n" + prompt_addendum
        template_version = "codex-harness-addendum-v1"
    canonical = json.dumps(
        {
            "template_version": template_version,
            "text": text,
            "task_digest": task_digest,
            "workspace_input_digest": workspace_input_digest,
            "context_digest": context_digest,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    prompt_hash = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return CodexHarnessPrompt(template_version, text, prompt_hash)
