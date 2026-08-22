from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from harnesslab.contracts.common import Sha256Digest
from harnesslab.tasks.package import TaskPackageError, digest_tree, is_link_like

PROMPT_TEMPLATE_VERSION = "direct-patch-v1"
MAX_PROMPT_TREE_BYTES = 512_000
MAX_PROMPT_BYTES = 1_000_000
SYSTEM_INSTRUCTIONS = """You are completing a controlled software micro task.
You have no tools, shell, filesystem, network, verifier, or oracle access.
Return only one strict JSON object matching the direct-patch-v1 output contract.
Do not use Markdown or code fences. Do not include commentary outside the JSON object."""
OUTPUT_CONTRACT = (
    '{"schema_version":1,"operations":['
    '{"op":"write","path":"relative/posix/path","content":"complete UTF-8 file content"},'
    '{"op":"delete","path":"relative/posix/file"}]}'
)


class PromptContractError(ValueError):
    """Subject-visible inputs cannot be represented by direct-patch-v1."""


@dataclass(frozen=True)
class DirectPrompt:
    template_version: str
    instructions: str
    input: str
    prompt_hash: Sha256Digest
    workspace_digest: Sha256Digest
    context_digest: Sha256Digest | None


def _text_files(root: Path) -> list[Path]:
    if not root.is_dir():
        raise PromptContractError("subject-visible tree is unavailable")
    files: list[Path] = []
    for current, directory_names, file_names in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in [*directory_names, *file_names]:
            if is_link_like(current_path / name):
                raise PromptContractError("subject-visible tree contains a link or junction")
        for name in file_names:
            files.append(current_path / name)
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def _serialize_tree(root: Path, label: str) -> str:
    sections: list[str] = []
    total_bytes = 0
    for path in _text_files(root):
        relative = path.relative_to(root).as_posix()
        content_bytes = path.read_bytes()
        total_bytes += len(relative.encode("utf-8")) + len(content_bytes)
        if total_bytes > MAX_PROMPT_TREE_BYTES:
            raise PromptContractError(f"{label} exceeds the direct prompt size limit")
        try:
            content = content_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PromptContractError(f"{label} contains unsupported binary content") from exc
        normalized = content.replace("\r\n", "\n").replace("\r", "\n")
        sections.append(f"<<<FILE {relative}>>>\n{normalized}\n<<<END FILE>>>")
    if not sections:
        return "<<<EMPTY TREE>>>"
    return "\n".join(sections)


def _hash_prompt(instructions: str, input_text: str) -> str:
    canonical = json.dumps(
        {
            "template_version": PROMPT_TEMPLATE_VERSION,
            "instructions": instructions,
            "input": input_text,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def render_direct_prompt(
    *,
    task_instruction: str,
    workspace: Path,
    context: Path | None,
) -> DirectPrompt:
    try:
        workspace_digest = digest_tree(workspace)
        context_digest = digest_tree(context) if context is not None else None
    except TaskPackageError as exc:
        raise PromptContractError("subject-visible tree identity is unsafe") from exc
    workspace_text = _serialize_tree(workspace, "workspace")
    context_text = _serialize_tree(context, "context") if context is not None else "NOT PROVIDED"
    input_text = (
        f"PROMPT_TEMPLATE={PROMPT_TEMPLATE_VERSION}\n"
        "\n[TASK INSTRUCTION]\n"
        f"{task_instruction.replace(chr(13) + chr(10), chr(10)).replace(chr(13), chr(10))}\n"
        "\n[SUBJECT-VISIBLE WORKSPACE]\n"
        f"{workspace_text}\n"
        "\n[OPTIONAL SUBJECT-VISIBLE CONTEXT]\n"
        f"{context_text}\n"
        "\n[OUTPUT CONTRACT]\n"
        f"{OUTPUT_CONTRACT}\n"
    )
    if len(input_text.encode("utf-8")) > MAX_PROMPT_BYTES:
        raise PromptContractError("rendered direct prompt exceeds the total size limit")
    return DirectPrompt(
        template_version=PROMPT_TEMPLATE_VERSION,
        instructions=SYSTEM_INSTRUCTIONS,
        input=input_text,
        prompt_hash=_hash_prompt(SYSTEM_INSTRUCTIONS, input_text),
        workspace_digest=workspace_digest,
        context_digest=context_digest,
    )


def assert_prompt_matches_task_identity(prompt: DirectPrompt, workspace: Path) -> None:
    try:
        current = digest_tree(workspace)
    except TaskPackageError as exc:
        raise PromptContractError("workspace identity is unavailable") from exc
    if current != prompt.workspace_digest:
        raise PromptContractError("workspace changed after prompt rendering")
