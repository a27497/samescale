"""Operator-only, data-only restoration. Approval and verification remain separate."""

from __future__ import annotations

import base64
import ctypes
import errno
import os
import secrets
import shutil
import stat
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

from harnesslab.analyst.offline_replay import decode, require
from harnesslab.code_snapshots import service
from harnesslab.episodes.hooks import encode
from harnesslab.external_evidence import service as evidence
from harnesslab.external_evidence.models import ApprovedSource, EvidencePolicy
from harnesslab.local_plans import tasks
from harnesslab.registry.models import canonical_digest


@contextmanager
def directory(path: Path) -> Iterator[int]:
    """Anchor every component without following links, including ancestors."""
    require(path.is_absolute() and ".." not in path.parts, "absolute canonical path required")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def snapshot_files(
    policy: EvidencePolicy, identity: str
) -> tuple[dict[str, Any], dict[str, bytes]]:
    # Complete existing read contract first; the second read must bind the SAME
    # content address, so a substitution between reads cannot supply new bytes.
    reviewed = service.read(policy, identity)
    with directory(service.storage(policy) / identity) as root:
        fd = os.open("snapshot.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root)
        try:
            info = os.fstat(fd)
            require(
                stat.S_ISREG(info.st_mode)
                and info.st_nlink == 1
                and stat.S_IMODE(info.st_mode) == 0o400
                and info.st_size <= service.MAX_STORED,
                "unsafe snapshot file",
            )
            with os.fdopen(os.dup(fd), "rb") as stream:
                payload = stream.read(service.MAX_STORED + 1)
            after = os.fstat(fd)
            require(
                len(payload) == info.st_size
                and after.st_mtime_ns == info.st_mtime_ns
                and after.st_size == info.st_size,
                "snapshot changed during capture",
            )
        finally:
            os.close(fd)
    value = decode(payload)
    require(payload == encode(value), "snapshot serialization drift")
    require(canonical_digest(value) == "sha256:" + identity, "snapshot identity drift")
    files = {
        name: base64.b64decode(content, validate=True)
        for name, content in value["contents_base64"].items()
    }
    require(
        evidence.content_digest(files) == reviewed["manifest"]["content_digest"], "content drift"
    )
    return reviewed, files


def protected_roots(policy: EvidencePolicy) -> list[Path]:
    roots = service.protected_roots(policy)
    for key in ("HARNESSLAB_EXTERNAL_EVIDENCE_POLICY", "HARNESSLAB_LOCAL_TASK_POLICY"):
        if value := os.environ.get(key):
            roots.append(Path(value))
    if os.environ.get("HARNESSLAB_LOCAL_TASK_POLICY"):
        task_policy = tasks.load_policy()
        for admission in task_policy.admissions:
            roots.extend([admission.qualification_file, admission.validation_file])
    for path in roots:
        evidence.safe_root(path)
    return roots


def write_file(root: int, name: str, content: bytes) -> None:
    evidence.safe_name(name)
    fd = os.dup(root)
    try:
        parts = name.split("/")
        for part in parts[:-1]:
            with suppress(FileExistsError):
                os.mkdir(part, mode=0o700, dir_fd=fd)
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        target = os.open(
            parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd
        )
        with os.fdopen(target, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(fd)
    finally:
        os.close(fd)


def captured_tree(root: int) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    total = 0

    def walk(fd: int, prefix: str) -> None:
        nonlocal total
        for part in sorted(os.listdir(fd)):
            name = prefix + part
            evidence.safe_name(name)
            child = os.open(part, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            try:
                info = os.fstat(child)
                if stat.S_ISDIR(info.st_mode):
                    walk(child, name + "/")
                    os.fsync(child)
                else:
                    require(
                        stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
                        "unsafe restored file",
                    )
                    with os.fdopen(os.dup(child), "rb") as stream:
                        data = stream.read(service.MAX_BYTES + 1)
                    total += len(data)
                    require(
                        len(files) < service.MAX_FILES and total <= service.MAX_BYTES,
                        "restored limits drift",
                    )
                    files[name] = data
            finally:
                os.close(child)

    walk(root, "")
    return files


def publish(parent: int, stage: str, destination: str) -> None:
    """Linux/WSL atomic no-replace, including existing empty dirs and symlinks.

    An unsupported filesystem/kernel fails closed; there is no overwriting fallback.
    """
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        rename = libc.renameat2
    except AttributeError:
        raise OSError(errno.ENOSYS, "atomic no-replace publication unavailable") from None
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(parent, os.fsencode(stage), parent, os.fsencode(destination), 1) != 0:
        error = ctypes.get_errno()
        raise OSError(error, "atomic no-replace publication rejected")


def restore(
    policy: EvidencePolicy,
    identity: str,
    destination: Path,
    *,
    source_id: str,
    task_reference: str,
    task_digest: str,
) -> dict[str, Any]:
    reviewed, files = snapshot_files(policy, identity)
    evidence.safe_root(destination)
    require(
        not any(evidence.overlap(destination, r) for r in protected_roots(policy)),
        "protected target",
    )
    require(source_id not in {s.source_id for s in policy.sources}, "source id already approved")
    source = ApprovedSource(
        source_id=source_id,
        format="code-only-v1",
        source_kind="unverified",
        workspace=destination,
        workspace_digest=reviewed["manifest"]["content_digest"],
        task_reference=task_reference,
        task_digest=task_digest,
    )
    evidence.safe_content(encode(source.binding))
    result = {
        "kind": "code-snapshot-restore-v1",
        "snapshot_identity": identity,
        "content_digest": source.workspace_digest,
        "included": reviewed["manifest"]["included"],
        "excluded": reviewed["manifest"]["excluded"],
        "source_authenticity": "NOT_ATTESTED",
        "verification": "NOT_VERIFIED",
        "task_mapping": "OPERATOR_ASSERTED_NOT_ATTESTED",
        "approval": "MANUAL_POLICY_REVIEW_REQUIRED",
        "execution_authorized": False,
        "source_fragment": source.model_dump(mode="json", exclude_none=True),
    }
    # Validate/serialize everything before writing, including the fragment.
    encode(result)
    with directory(destination.parent) as parent:
        parent_info = os.fstat(parent)
        require(
            parent_info.st_uid == os.getuid() and not parent_info.st_mode & 0o022,
            "target parent must be owned and not shared-writable",
        )
        require(destination.name not in os.listdir(parent), "target must not exist")
        stage = ".code-snapshot-restore-" + secrets.token_hex(16)
        os.mkdir(stage, mode=0o700, dir_fd=parent)
        try:
            stage_fd = os.open(stage, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            try:
                for name, content in sorted(files.items()):
                    write_file(stage_fd, name, content)
                require(captured_tree(stage_fd) == files, "restored bytes drift")
                os.fsync(stage_fd)
            finally:
                os.close(stage_fd)
            # Refuse path substitutions between opening the parent and publication.
            evidence.safe_root(destination)
            current = destination.parent.stat()
            require(
                (current.st_dev, current.st_ino) == (parent_info.st_dev, parent_info.st_ino),
                "target parent substituted",
            )
            publish(parent, stage, destination.name)
        finally:
            # fd-relative rmtree does not follow substituted symlinks.
            shutil.rmtree(stage, dir_fd=parent, ignore_errors=True)
    return result
