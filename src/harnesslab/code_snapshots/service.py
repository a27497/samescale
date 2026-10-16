"""Bounded ZIP reviews and immutable, independently addressed source subsets.

No entry is extracted to a filesystem path. Reviews are stateless: confirmation
resends the ZIP and binds its recomputed manifest to an operator-keyed signature.
"""

from __future__ import annotations

import base64
import fcntl
import hashlib
import hmac
import io
import os
import re
import stat
import struct
import tempfile
import unicodedata
import zipfile
import zlib
from pathlib import Path
from typing import Any, Literal

from harnesslab.analyst.offline_replay import decode, require
from harnesslab.episodes.hooks import _write_once, encode
from harnesslab.external_evidence import service as evidence
from harnesslab.external_evidence.models import EvidencePolicy
from harnesslab.local_execution.policy import load_execution_policy
from harnesslab.local_plans import tasks
from harnesslab.productization.assets import distribution_root
from harnesslab.registry.models import canonical_digest
from harnesslab.tasks.package import sha256_bytes

MAX_UPLOAD = 8_000_000
MAX_ENTRIES = 10_000  # Includes directories and files excluded from the final subset.
MAX_SCAN_BYTES = 32_000_000
MAX_ENTRY_BYTES = 8_000_000
MAX_RATIO = 200
MAX_FILES = 500
MAX_BYTES = 4_000_000
MAX_STORED = 10_000_000
STORE_NAME = ".code-snapshots-v1"  # Existing record discovery ignores dot namespaces.
BINARY_SUFFIXES = {
    ".bin",
    ".pyc",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".webp",
    ".pdf",
    ".mp3",
    ".mp4",
    ".wasm",
    ".so",
    ".dll",
    ".exe",
    ".woff",
    ".woff2",
    ".ttf",
}
CONSENT = "SAVE_REVIEWED_SOURCE_SUBSET"
DeclaredTool = Literal["unknown", "deepseek-harness-desktop", "codex", "claude-code", "other"]
LIMITS = {
    "upload_bytes": MAX_UPLOAD,
    "scan_entries": MAX_ENTRIES,
    "scan_uncompressed_bytes": MAX_SCAN_BYTES,
    "scan_entry_bytes": MAX_ENTRY_BYTES,
    "compression_ratio": MAX_RATIO,
    "snapshot_files": MAX_FILES,
    "snapshot_bytes": MAX_BYTES,
}
EXCLUDED_PARTS = {
    ".venv": "DEPENDENCY_DIRECTORY",
    "venv": "DEPENDENCY_DIRECTORY",
    "node_modules": "DEPENDENCY_DIRECTORY",
    "__pycache__": "CACHE_DIRECTORY",
    ".pytest_cache": "CACHE_DIRECTORY",
    ".mypy_cache": "CACHE_DIRECTORY",
    ".ruff_cache": "CACHE_DIRECTORY",
    ".cache": "CACHE_DIRECTORY",
    "cache": "CACHE_DIRECTORY",
    "dist": "BUILD_OUTPUT",
    "build": "BUILD_OUTPUT",
    "artifacts": "GENERATED_ARTIFACT",
}


class Rejected(ValueError):
    def __init__(self, reason: str, entry: int | None = None, path: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.entry = entry
        self.path = path


def check(ok: bool, reason: str, entry: int | None = None, path: str | None = None) -> None:
    if not ok:
        raise Rejected(reason, entry, path)


def entry_name(info: zipfile.ZipInfo, index: int) -> str:
    # orig_filename preserves embedded NULs which ZipInfo.filename truncates.
    original = info.orig_filename
    name = original[:-1] if original.endswith("/") else original
    check(
        bool(name)
        and not original.startswith("/")
        and "\\" not in original
        and ":" not in original
        and all(p not in {"", ".", ".."} for p in name.split("/"))
        and all(ord(c) >= 32 and ord(c) != 127 for c in original),
        "UNSAFE_PATH",
        index,
    )
    try:
        evidence.safe_name(name)
        # Upper-case .ENV variants also fail closed; existing rules stay untouched.
        check(not any(p.lower().startswith(".env") for p in name.split("/")), "PRIVATE_PATH")
    except (ValueError, Rejected):
        raise Rejected("PRIVATE_OR_UNSAFE_NAME", index) from None
    mode = info.external_attr >> 16
    kind = stat.S_IFMT(mode)
    check(
        kind in {0, stat.S_IFREG, stat.S_IFDIR}
        and (kind != stat.S_IFDIR or info.is_dir())
        and (kind != stat.S_IFREG or not info.is_dir())
        and (not info.external_attr & 0x10 or info.is_dir())
        and not info.external_attr & 0x08,
        "SYMLINK_OR_SPECIAL_FILE",
        index,
        name,
    )
    check(not info.flag_bits & (1 | 64), "ENCRYPTED_ENTRY", index, name)
    return name


def scan(
    data: bytes, declared_tool: DeclaredTool = "unknown"
) -> tuple[dict[str, Any], dict[str, bytes]]:
    check(len(data) <= MAX_UPLOAD, "UPLOAD_LIMIT")
    check(data.startswith(b"PK\x03\x04") or data.startswith(b"PK\x05\x06"), "CORRUPT_ARCHIVE")
    files: dict[str, bytes] = {}
    included: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    directories: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            check(len(entries) <= MAX_ENTRIES, "SCAN_ENTRY_LIMIT")
            names: dict[str, bool] = {}
            total = 0
            compressed = 0
            # Check every name before any content, including excluded dependencies.
            for index, info in enumerate(entries):
                name = entry_name(info, index)
                key = unicodedata.normalize("NFC", name).casefold()
                check(key not in names, "NAME_COLLISION", index, name)
                names[key] = info.is_dir()
                check(info.file_size <= MAX_ENTRY_BYTES, "SCAN_ENTRY_BYTE_LIMIT", index, name)
                total += info.file_size
                compressed += info.compress_size
                check(total <= MAX_SCAN_BYTES, "SCAN_BYTE_LIMIT", index, name)
                check(
                    info.file_size <= MAX_RATIO * max(info.compress_size, 1),
                    "COMPRESSION_RATIO_LIMIT",
                    index,
                    name,
                )
                check(
                    info.compress_type in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED},
                    "UNSUPPORTED_COMPRESSION",
                    index,
                    name,
                )
                if info.is_dir():
                    check(info.file_size == 0, "DIRECTORY_CONTENT", index, name)
            check(total <= MAX_RATIO * max(compressed, 1), "COMPRESSION_RATIO_LIMIT")
            # Also reject a file occupying a directory's implicit prefix.
            for name in names:
                parts = name.split("/")
                for i in range(1, len(parts)):
                    check(names.get("/".join(parts[:i]), True), "NAME_COLLISION")
            scanned = 0
            for index, info in enumerate(entries):
                name = info.filename.rstrip("/")
                # ZipExtFile trusts the central file_size and can truncate a forged
                # deflate stream. Independently consume the complete compressed data
                # with an output cap, and check local headers, actual size and CRC.
                with archive.open(info):
                    pass  # Validate local name, overlapping entries and ZIP structure.
                offset = info.header_offset
                header = struct.unpack_from("<4s5H3I2H", data, offset)
                check(
                    header[0] == b"PK\x03\x04"
                    and header[2] == info.flag_bits
                    and header[3] == info.compress_type,
                    "CORRUPT_ARCHIVE",
                    index,
                    name,
                )
                if not info.flag_bits & 8:
                    check(
                        header[6:9] == (info.CRC, info.compress_size, info.file_size),
                        "CORRUPT_ARCHIVE",
                        index,
                        name,
                    )
                start = offset + 30 + header[9] + header[10]
                end = start + info.compress_size
                compressed_data = data[start:end]
                cap = min(MAX_ENTRY_BYTES, MAX_SCAN_BYTES - scanned)
                if info.compress_type == zipfile.ZIP_DEFLATED:
                    inflater = zlib.decompressobj(-15)
                    content = inflater.decompress(compressed_data, cap + 1)
                    check(len(content) <= cap, "DECOMPRESSION_LIMIT", index, name)
                    check(
                        inflater.eof and not inflater.unused_data and not inflater.unconsumed_tail,
                        "CORRUPT_ARCHIVE",
                        index,
                        name,
                    )
                else:
                    content = compressed_data
                check(
                    len(content) == info.file_size and zlib.crc32(content) == info.CRC,
                    "CORRUPT_ARCHIVE",
                    index,
                    name,
                )
                if info.flag_bits & 8:
                    descriptor = end + (4 if data[end : end + 4] == b"PK\x07\x08" else 0)
                    check(
                        struct.unpack_from("<3I", data, descriptor)
                        == (info.CRC, info.compress_size, info.file_size),
                        "CORRUPT_ARCHIVE",
                        index,
                        name,
                    )
                scanned += len(content)
                check(scanned <= MAX_SCAN_BYTES, "SCAN_BYTE_LIMIT", index, name)
                if info.is_dir():
                    directories.append(name)
                    continue
                # Credential detection precedes binary/UTF-8/exclusion classification.
                check(not evidence.SECRET.search(content), "CREDENTIAL_CONTENT", index, name)
                check(
                    not content.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"))
                    and not name.lower().endswith((".zip", ".jar", ".whl")),
                    "NESTED_ARCHIVE",
                    index,
                    name,
                )
                reason = next(
                    (
                        EXCLUDED_PARTS[p.lower()]
                        for p in name.split("/")
                        if p.lower() in EXCLUDED_PARTS
                    ),
                    None,
                )
                try:
                    evidence.safe_content(content)
                except evidence.EvidenceInputError:
                    reason = reason or "BINARY_OR_NON_UTF8"
                if Path(name).suffix.lower() in BINARY_SUFFIXES or any(
                    byte < 32 and byte not in {9, 10, 13} for byte in content
                ):
                    reason = reason or "BINARY_OR_NON_UTF8"
                item = {"path": name, "bytes": len(content), "sha256": sha256_bytes(content)}
                if reason:
                    excluded.append({**item, "reason": reason})
                else:
                    files[name] = content
                    included.append(item)
            check(bool(files), "EMPTY_SOURCE_SUBSET")
            check(len(files) <= MAX_FILES, "SNAPSHOT_FILE_LIMIT")
            check(sum(map(len, files.values())) <= MAX_BYTES, "SNAPSHOT_BYTE_LIMIT")
    except (
        zipfile.BadZipFile,
        EOFError,
        RuntimeError,
        NotImplementedError,
        struct.error,
        zlib.error,
        OSError,
        ValueError,
    ) as exc:
        if isinstance(exc, Rejected):
            raise
        raise Rejected("CORRUPT_ARCHIVE") from None
    manifest = {
        "kind": "code-snapshot-review-v1",
        "archive_sha256": sha256_bytes(data),
        "archive_bytes": len(data),
        "declared_tool": declared_tool,
        "included": sorted(included, key=lambda item: item["path"]),
        "excluded": sorted(excluded, key=lambda item: item["path"]),
        "directories": sorted(directories),
        "content_digest": evidence.content_digest(files),
        "limits": LIMITS,
    }
    return manifest, files


def sign_review(manifest: dict[str, Any]) -> str:
    key = os.environ["HARNESSLAB_LOCAL_CONFIGURATION_TOKEN"].encode()
    return hmac.new(
        key, b"code-snapshot-review-v1\x00" + encode(manifest), hashlib.sha256
    ).hexdigest()


def preview(data: bytes, tool: DeclaredTool) -> dict[str, Any]:
    try:
        manifest, _ = scan(data, tool)
        return {
            "status": "REVIEW_REQUIRED",
            "manifest": manifest,
            "manifest_sha256": canonical_digest(manifest),
            "review_signature": sign_review(manifest),
        }
    except Rejected as exc:
        return {
            "status": "REJECTED",
            "rejections": [{"reason": exc.reason, "entry": exc.entry, "path": exc.path}],
            "limits": LIMITS,
        }


def storage(policy: EvidencePolicy) -> Path:
    evidence.validate_store(policy)
    return policy.store / STORE_NAME


def protected_roots(policy: EvidencePolicy) -> list[Path]:
    roots = [policy.store, distribution_root()]
    roots.extend(r for r in (policy.runtime_root, policy.artifact_root) if r is not None)
    for source in policy.sources:
        roots.append(source.workspace)
        if source.path is not None:
            roots.append(source.path)
    if os.environ.get("HARNESSLAB_LOCAL_TASK_POLICY"):
        task_policy = tasks.load_policy()
        roots.extend([task_policy.managed_store, *task_policy.source_roots.values()])
    if os.environ.get("HARNESSLAB_LOCAL_EXECUTION_POLICY"):
        execution_policy = load_execution_policy()
        roots.extend([execution_policy.runtime_root, execution_policy.artifact_root])
    if configured_custom_store := os.environ.get("HARNESSLAB_CUSTOM_EVAL_STORE"):
        custom_store = Path(configured_custom_store).resolve()
        evidence.safe_root(custom_store)
        roots.append(custom_store)
    return roots


def read(policy: EvidencePolicy, identity: str) -> dict[str, Any]:
    require(bool(re.fullmatch(r"[a-f0-9]{64}", identity)), "invalid snapshot identity")
    root = storage(policy) / identity
    tasks.bounded_files(root, max_files=1, max_bytes=MAX_STORED)
    path = root / "snapshot.json"
    info = path.stat()
    require(info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == 0o400, "unsafe snapshot rights")
    value = decode(path.read_bytes())
    require(canonical_digest(value) == "sha256:" + identity, "snapshot identity drift")
    require(value["kind"] == "code-snapshot-v1", "snapshot kind drift")
    require(
        value["source_authenticity"] == "NOT_ATTESTED"
        and value["run_record"] == "NO_RUN_RECORD"
        and value["verification"] == "NOT_VERIFIED",
        "snapshot authority drift",
    )
    manifest = value["manifest"]
    files = {
        name: base64.b64decode(content, validate=True)
        for name, content in value["contents_base64"].items()
    }
    require(
        0 < len(files) <= MAX_FILES and sum(map(len, files.values())) <= MAX_BYTES,
        "snapshot limits drift",
    )
    for name, data in files.items():
        evidence.safe_name(name)
        evidence.safe_content(data)
    require(evidence.content_digest(files) == manifest["content_digest"], "content drift")
    require(
        manifest["included"]
        == [
            {"path": name, "bytes": len(content), "sha256": sha256_bytes(content)}
            for name, content in sorted(files.items())
        ],
        "inventory drift",
    )
    require(
        value["confirmation"]
        == {
            "consent": CONSENT,
            "archive_sha256": manifest["archive_sha256"],
            "manifest_sha256": canonical_digest(manifest),
            "review_signature": value["confirmation"]["review_signature"],
            "excluded_subset_acknowledged": True,
        },
        "confirmation drift",
    )
    return {"identity": identity, **{k: v for k, v in value.items() if k != "contents_base64"}}


def confirm(
    policy: EvidencePolicy,
    data: bytes,
    tool: DeclaredTool,
    *,
    consent: str,
    archive_sha256: str,
    manifest_sha256: str,
    signature: str,
) -> dict[str, Any]:
    manifest, files = scan(data, tool)
    check(consent == CONSENT, "EXPLICIT_CONFIRMATION_REQUIRED")
    check(
        archive_sha256 == manifest["archive_sha256"]
        and manifest_sha256 == canonical_digest(manifest)
        and hmac.compare_digest(signature.encode(), sign_review(manifest).encode()),
        "REVIEW_MISMATCH",
    )
    value = {
        "kind": "code-snapshot-v1",
        "source_authenticity": "NOT_ATTESTED",
        "run_record": "NO_RUN_RECORD",
        "verification": "NOT_VERIFIED",
        "manifest": manifest,
        "confirmation": {
            "consent": CONSENT,
            "archive_sha256": archive_sha256,
            "manifest_sha256": manifest_sha256,
            "review_signature": signature,
            "excluded_subset_acknowledged": True,
        },
        "contents_base64": {
            name: base64.b64encode(content).decode() for name, content in sorted(files.items())
        },
    }
    identity = canonical_digest(value)[7:]
    target = storage(policy)
    # Sibling staging keeps transient content outside records/snapshots/workspaces;
    # same-parent placement allows atomic rename on the store's filesystem.
    policy.store.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    roots = protected_roots(policy)
    evidence.safe_root(policy.store.parent)
    policy.store.mkdir(exist_ok=True, mode=0o700)
    target.mkdir(exist_ok=True, mode=0o700)
    with (target / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        destination = target / identity
        if not destination.exists():
            with tempfile.TemporaryDirectory(
                dir=policy.store.parent, prefix=".code-snapshot-staging-"
            ) as temporary:
                stage = Path(temporary)
                evidence.safe_root(stage)
                check(not any(evidence.overlap(stage, r) for r in roots), "STAGING_LOCATION_UNSAFE")
                staged = stage / "snapshot"
                staged.mkdir(mode=0o700)
                _write_once(staged / "snapshot.json", encode(value))
                (staged / "snapshot.json").chmod(0o400)
                os.rename(staged, destination)
    return read(policy, identity)
