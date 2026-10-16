"""Synthetic adversarial ZIPs; real MiniShop acceptance is recorded separately."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import stat
import struct
import subprocess
import zipfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient, AsyncHTTPTransport, HTTPTransport
from starlette.requests import Request

from harnesslab.api.app import create_app
from harnesslab.api.workbench_errors import WorkbenchAPIError
from harnesslab.code_snapshots import service
from harnesslab.code_snapshots.api import upload
from harnesslab.episodes.hooks import encode
from harnesslab.external_evidence import service as evidence
from harnesslab.external_evidence.models import EvidencePolicy
from harnesslab.registry.models import canonical_digest
from harnesslab.tasks.package import sha256_bytes
from tests.local_plan_helpers import HEADERS, TOKEN
from tests.test_external_evidence import historical_source

ORIGINAL_PROJECT = evidence.project

PREFIX = "/api/code-snapshots"
ZIP_HEADERS = {**HEADERS, "Content-Type": "application/zip"}


def zipped(items: list[tuple[str | zipfile.ZipInfo, bytes]], compression: int = 0) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=compression) as archive:
        for name, data in items:
            archive.writestr(name, data)
    return out.getvalue()


@pytest.fixture
def policy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> EvidencePolicy:
    value = EvidencePolicy(store=tmp_path / "records", sources=())
    path = tmp_path / "policy.json"
    path.write_bytes(encode(value.model_dump(mode="json")))
    path.chmod(0o600)
    monkeypatch.setenv("HARNESSLAB_EXTERNAL_EVIDENCE_POLICY", str(path))
    monkeypatch.setenv("HARNESSLAB_LOCAL_CONFIGURATION_TOKEN", TOKEN)
    monkeypatch.delenv("HARNESSLAB_LOCAL_TASK_POLICY", raising=False)
    monkeypatch.delenv("HARNESSLAB_LOCAL_EXECUTION_POLICY", raising=False)
    monkeypatch.delenv("HARNESSLAB_CUSTOM_EVAL_STORE", raising=False)
    monkeypatch.delenv("HARNESSLAB_PUBLIC_DEMO_MANIFEST", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError(
            "ZIP intake attempted Agent/Verifier/Provider/process/network execution"
        )

    async def async_forbidden(*args: object, **kwargs: object) -> None:
        forbidden()

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(HTTPTransport, "handle_request", forbidden)
    monkeypatch.setattr(AsyncHTTPTransport, "handle_async_request", async_forbidden)
    # Named runtime boundaries as well as transports; no imports from uploaded files.
    monkeypatch.setattr("harnesslab.external_evidence.verification.verify_workspace", forbidden)
    monkeypatch.setattr(evidence, "project", forbidden)
    monkeypatch.setattr("harnesslab.harness_lane.runner.CodexHarnessRunner.run", async_forbidden)
    monkeypatch.setattr("harnesslab.multi_harness.runner.MultiHarnessRunner.run", async_forbidden)
    monkeypatch.setattr(
        "harnesslab.model_lane.providers._HTTPProviderAdapter.invoke", async_forbidden
    )
    monkeypatch.setattr(
        "harnesslab.analyst.real_backend.RealAnalystBackend.decide", async_forbidden
    )
    return value


@pytest.fixture
async def client(policy: EvidencePolicy) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://localhost", headers=ZIP_HEADERS
    ) as value:
        yield value


def confirmation(review: dict[str, Any]) -> dict[str, str]:
    return {
        "x-snapshot-consent": service.CONSENT,
        "x-snapshot-archive-sha256": review["manifest"]["archive_sha256"],
        "x-snapshot-manifest-sha256": review["manifest_sha256"],
        "x-snapshot-review": review["review_signature"],
    }


@pytest.mark.parametrize(
    "name",
    [
        "../outside.py",
        "/absolute.py",
        "C:/drive.py",
        "C:\\drive.py",
        "folder\\file.py",
        "folder/../file.py",
        "folder//file.py",
        ".env",
        ".env.example",
        ".ENV",
        ".git/config",
        ".ssh/key",
        ".codex/session.json",
        "folder/verifier/test.py",
        "auth.json",
        "bad\x00name.py",
    ],
)
def test_hard_path_rejections(name: str) -> None:
    data = zipped([(name, b"source")])
    # zipfile's writer itself truncates NULs; patch both local and central names instead.
    if "\x00" in name:
        data = zipped([("badXname.py", b"source")]).replace(b"badXname.py", b"bad\x00name.py")
    result = service.preview(data, "unknown")
    assert result["status"] == "REJECTED"
    assert result["rejections"][0]["reason"] in {"UNSAFE_PATH", "PRIVATE_OR_UNSAFE_NAME"}


@pytest.mark.parametrize(
    "names",
    [
        ["same.py", "same.py"],
        ["App.py", "app.py"],
        ["caf\u00e9.py", "cafe\u0301.py"],
        ["source", "source/file.py"],
        ["D/", "d/"],
        ["Folder", "folder/child.py"],
    ],
)
def test_duplicate_case_nfc_and_prefix_collisions(names: list[str]) -> None:
    result = service.preview(zipped([(name, b"") for name in names]), "unknown")
    assert result["rejections"][0]["reason"] == "NAME_COLLISION"


@pytest.mark.parametrize(
    "kind", [stat.S_IFLNK, stat.S_IFIFO, stat.S_IFSOCK, stat.S_IFCHR, stat.S_IFBLK, stat.S_IFDIR]
)
def test_symlink_special_external_attributes(kind: int) -> None:
    entry = zipfile.ZipInfo("file.py")
    entry.create_system = 3
    entry.external_attr = (kind | 0o600) << 16
    assert (
        service.preview(zipped([(entry, b"source")]), "unknown")["rejections"][0]["reason"]
        == "SYMLINK_OR_SPECIAL_FILE"
    )
    windows_link = zipfile.ZipInfo("windows-link.py")
    windows_link.create_system = 0
    windows_link.external_attr = 0x400
    assert service.preview(zipped([(windows_link, b"target")]), "unknown")["status"] == "REJECTED"


def test_encrypted_entry() -> None:
    data = bytearray(zipped([("main.py", b"source")]))
    struct.pack_into("<H", data, 6, 1)
    central = data.index(b"PK\x01\x02")
    struct.pack_into("<H", data, central + 8, 1)
    assert service.preview(bytes(data), "unknown")["rejections"][0]["reason"] == "ENCRYPTED_ENTRY"


@pytest.mark.parametrize("where", ["main.py", ".venv/lib/dependency.py", "dist/file.bin"])
def test_credentials_reject_even_excludable_files(where: str) -> None:
    result = service.preview(
        zipped([("safe.py", b"source"), (where, b"api_key='abcdefghijklmno'")]), "unknown"
    )
    assert result["rejections"][0]["reason"] == "CREDENTIAL_CONTENT"
    assert "abcdefghijklmno" not in json.dumps(result)


@pytest.mark.parametrize(
    "content,name",
    [
        (b"\xff\xfe", "bad.txt"),
        (b"binary\x00", "file.bin"),
        (b"print('unused')", ".venv/library.py"),
        (b"cached", "__pycache__/cache.pyc"),
        (b"built", "build/file.js"),
        (b"generated", "artifacts/result.txt"),
    ],
)
async def test_exclusions_are_reviewed_and_retained(
    client: AsyncClient, policy: EvidencePolicy, content: bytes, name: str
) -> None:
    data = zipped([("main.py", b"print('source')"), (name, content)])
    preview = (await client.post(PREFIX + "/archive", content=data)).json()
    assert preview["status"] == "REVIEW_REQUIRED"
    manifest = preview["manifest"]
    assert len(manifest["included"]) == len(manifest["excluded"]) == 1
    assert manifest["excluded"][0]["path"] == name and manifest["excluded"][0]["reason"]
    assert not policy.store.exists()
    denied = await client.post(PREFIX + "/archive?action=confirm", content=data)
    assert denied.status_code == 409 and not policy.store.exists()
    saved = await client.post(
        PREFIX + "/archive?action=confirm", content=data, headers=confirmation(preview)
    )
    assert saved.status_code == 200, saved.text
    item = saved.json()
    assert item["manifest"] == manifest
    assert item["source_authenticity"] == "NOT_ATTESTED"
    assert item["run_record"] == "NO_RUN_RECORD" and item["verification"] == "NOT_VERIFIED"
    assert item["confirmation"]["excluded_subset_acknowledged"] is True
    stored = json.loads(
        (policy.store / service.STORE_NAME / item["identity"] / "snapshot.json").read_bytes()
    )
    assert stored["contents_base64"] == {"main.py": base64.b64encode(b"print('source')").decode()}
    assert (await client.get(PREFIX + "/" + item["identity"])).json() == item
    assert (await client.get("/api/external-evidence/records")).json() == {"items": []}
    assert (
        await client.get("/api/external-evidence/records/" + item["identity"])
    ).status_code == 409
    assert not list(policy.store.parent.glob(".code-snapshot-staging-*"))


@pytest.mark.parametrize(
    "case,reason",
    [
        ("files", "SNAPSHOT_FILE_LIMIT"),
        ("snapshot_bytes", "SNAPSHOT_BYTE_LIMIT"),
        ("entry_bytes", "SCAN_ENTRY_BYTE_LIMIT"),
        ("scan_bytes", "SCAN_BYTE_LIMIT"),
        ("ratio", "COMPRESSION_RATIO_LIMIT"),
        ("scan_entries", "SCAN_ENTRY_LIMIT"),
        ("upload", "UPLOAD_LIMIT"),
    ],
)
def test_distinct_limits(case: str, reason: str) -> None:
    data: bytes | bytearray
    if case == "files":
        data = zipped([(f"f{i}.py", b"source") for i in range(501)])
    elif case == "scan_entries":
        data = zipped([(f"d{i}/", b"") for i in range(10_001)])
    elif case == "ratio":
        data = zipped([("bomb.py", b"a" * 500_000)], zipfile.ZIP_DEFLATED)
    elif case == "upload":
        data = b"a" * (service.MAX_UPLOAD + 1)
    else:
        data = bytearray(zipped([(f"f{i}.py", b"source") for i in range(5)]))
        central = 0
        for _ in range(5):
            central = data.index(b"PK\x01\x02", central)
            size = {"snapshot_bytes": 800_001, "entry_bytes": 8_000_001, "scan_bytes": 7_000_000}[
                case
            ]
            # Metadata limits precede reading/allocating decompressed bytes.
            struct.pack_into("<I", data, central + 20, size)
            struct.pack_into("<I", data, central + 24, size)
            central += 4
        if case == "snapshot_bytes":
            data = zipped([(f"f{i}.py", b"a" * 800_001) for i in range(5)])
        data = bytes(data)
    assert service.preview(data, "unknown")["rejections"][0]["reason"] == reason


@pytest.mark.parametrize(
    "data",
    [
        b"not a zip",
        zipped([("main.py", b"source")])[:-20],
        zipped([("nested.zip", zipped([("main.py", b"source")]))]),
        zipped([("renamed.py", zipped([("main.py", b"source")]))]),
    ],
    ids=["invalid", "truncated", "nested_zip", "renamed_zip"],
)
def test_corrupt_truncated_and_nested_archives(data: bytes) -> None:
    assert service.preview(data, "unknown")["status"] == "REJECTED"


async def test_concurrent_confirmation_is_idempotent_and_write_once(
    client: AsyncClient, policy: EvidencePolicy
) -> None:
    data = zipped([("main.py", b"print('source')")])
    preview = (
        await client.post(PREFIX + "/archive?declared_tool=deepseek-harness-desktop", content=data)
    ).json()

    async def save() -> Any:
        return await client.post(
            PREFIX + "/archive?action=confirm&declared_tool=deepseek-harness-desktop",
            content=data,
            headers=confirmation(preview),
        )

    results = await asyncio.gather(*(save() for _ in range(6)))
    assert all(r.status_code == 200 for r in results)
    assert all(r.json() == results[0].json() for r in results)
    identity = results[0].json()["identity"]
    root = policy.store / service.STORE_NAME / identity
    before = (root / "snapshot.json").stat()
    assert (await save()).json() == results[0].json()
    assert before == (root / "snapshot.json").stat()
    assert stat.S_IMODE(before.st_mode) == 0o400
    assert list(root.iterdir()) == [root / "snapshot.json"]
    assert not list(policy.store.parent.glob(".code-snapshot-staging-*"))


@pytest.mark.parametrize("part", ["archive", "manifest", "signature", "tool", "content", "consent"])
async def test_confirmation_mismatches_never_persist(
    client: AsyncClient, policy: EvidencePolicy, part: str
) -> None:
    data = zipped([("main.py", b"source")])
    preview = (await client.post(PREFIX + "/archive", content=data)).json()
    headers = confirmation(preview)
    query = "?action=confirm"
    if part in {"archive", "manifest", "signature", "consent"}:
        key = {
            "archive": "x-snapshot-archive-sha256",
            "manifest": "x-snapshot-manifest-sha256",
            "signature": "x-snapshot-review",
            "consent": "x-snapshot-consent",
        }[part]
        headers[key] = "incorrect"
    elif part == "tool":
        query += "&declared_tool=codex"
    else:
        data = zipped([("main.py", b"changed source")])
    result = await client.post(PREFIX + "/archive" + query, content=data, headers=headers)
    assert result.status_code == 409
    assert not policy.store.exists()


@pytest.mark.parametrize(
    "kind",
    [
        "none",
        "wrong_token",
        "wrong_origin",
        "no_origin",
        "cross_site",
        "host",
        "public_demo",
        "wrong_type",
    ],
)
async def test_operator_guards_precede_policy_reads(
    policy: EvidencePolicy, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    headers = dict(ZIP_HEADERS)
    if kind == "none":
        headers.pop("Authorization")
    if kind == "wrong_token":
        headers["Authorization"] = "Bearer incorrect"
    if kind == "wrong_origin":
        headers["Origin"] = "http://evil.invalid"
    if kind == "no_origin":
        headers.pop("Origin")
    if kind == "cross_site":
        headers["sec-fetch-site"] = "cross-site"
    if kind == "host":
        headers["Host"] = "evil.invalid"
    if kind == "wrong_type":
        headers["Content-Type"] = "application/json"
    if kind == "public_demo":
        monkeypatch.setenv("HARNESSLAB_PUBLIC_DEMO_MANIFEST", "/never-read")

    def forbidden() -> None:
        raise AssertionError("Policy read before authentication")

    monkeypatch.setattr(evidence, "load_policy", forbidden)
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://localhost"
    ) as c:
        result = await c.post(PREFIX + "/archive", content=b"not-read", headers=headers)
        assert result.status_code == (415 if kind == "wrong_type" else 403)


async def test_default_json_guard_is_preserved(client: AsyncClient) -> None:
    for path in ("/api/external-evidence/records", "/api/local-plans/tasks/import"):
        result = await client.post(path, content=b"not-json")
        assert result.status_code == 415 and result.json()["error"]["code"] == "JSON_REQUIRED"


@pytest.mark.parametrize("length", ["8000001", "-1", "broken", "9" * 5000])
async def test_content_length_rejected_before_body(client: AsyncClient, length: str) -> None:
    result = await client.post(PREFIX + "/archive", content=b"", headers={"Content-Length": length})
    assert result.status_code in {400, 413}


async def test_length_mismatch_and_disconnect_cleanup(policy: EvidencePolicy) -> None:
    for message in (
        {"type": "http.request", "body": b"PK", "more_body": False},
        {"type": "http.disconnect"},
    ):

        async def receive(value: dict[str, Any] = message) -> dict[str, Any]:
            return value

        request = Request({"type": "http", "headers": [(b"content-length", b"200")]}, receive)
        with pytest.raises(WorkbenchAPIError) as exc:
            await upload(request)
        assert exc.value.code == "ZIP_UPLOAD_TRUNCATED"
    assert not policy.store.exists()
    assert not list(policy.store.parent.glob(".code-snapshot-staging-*"))


async def test_tampering_read_rejected_and_atomic_failure_cleans_stage(
    client: AsyncClient, policy: EvidencePolicy, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = zipped([("main.py", b"source")])
    preview = (await client.post(PREFIX + "/archive", content=data)).json()
    maximum_stored = service.MAX_STORED
    monkeypatch.setattr(service, "MAX_STORED", 1)
    oversized = await client.post(
        PREFIX + "/archive?action=confirm", content=data, headers=confirmation(preview)
    )
    assert oversized.status_code == 409
    assert oversized.json()["error"]["code"] == "ZIP_SNAPSHOT_METADATA_LIMIT"
    assert not policy.store.exists()
    monkeypatch.setattr(service, "MAX_STORED", maximum_stored)
    maximum_store = service.STORE_MAX_BYTES
    monkeypatch.setattr(service, "STORE_MAX_BYTES", 1)
    capacity = await client.post(
        PREFIX + "/archive?action=confirm", content=data, headers=confirmation(preview)
    )
    assert capacity.status_code == 409
    assert capacity.json()["error"]["code"] == "ZIP_SNAPSHOT_STORAGE_CAPACITY"
    assert (await client.get("/api/external-evidence/records")).json() == {"items": []}
    monkeypatch.setattr(service, "STORE_MAX_BYTES", maximum_store)
    original_rename = os.rename
    stages: list[Path] = []

    def interrupted(src: str | Path, dst: str | Path) -> None:
        stages.append(Path(src).parent)
        assert not evidence.overlap(Path(src).parent, policy.store)
        raise OSError("synthetic interrupted commit")

    monkeypatch.setattr(os, "rename", interrupted)
    result = await client.post(
        PREFIX + "/archive?action=confirm", content=data, headers=confirmation(preview)
    )
    assert result.status_code == 409 and stages and all(not p.exists() for p in stages)
    monkeypatch.setattr(os, "rename", original_rename)
    saved = (
        await client.post(
            PREFIX + "/archive?action=confirm", content=data, headers=confirmation(preview)
        )
    ).json()
    path = policy.store / service.STORE_NAME / saved["identity"] / "snapshot.json"
    original_payload = path.read_bytes()
    value = json.loads(original_payload)
    value["manifest"]["excluded"] = [{"path": "forged"}]
    path.chmod(0o600)
    path.write_bytes(encode(value))
    path.chmod(0o400)
    result = await client.get(PREFIX + "/" + saved["identity"])
    assert (
        result.status_code == 409 and result.json()["error"]["code"] == "SNAPSHOT_INTEGRITY_ERROR"
    )
    # Byte-only edits must also fail, even when the decoded object is unchanged.
    path.chmod(0o600)
    path.write_bytes(original_payload + b" ")
    path.chmod(0o400)
    result = await client.get(PREFIX + "/" + saved["identity"])
    assert (
        result.status_code == 409 and result.json()["error"]["code"] == "SNAPSHOT_INTEGRITY_ERROR"
    )


async def test_existing_identity_export_replay_and_receipt_unchanged(
    policy: EvidencePolicy, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(evidence, "project", ORIGINAL_PROJECT)
    old_policy = policy.model_copy(update={"sources": (historical_source(),)})
    before = evidence.ingest(old_policy, "approved-historical-real")
    identity = before["identity"]
    # A non-empty synthetic receipt proves byte preservation without running a Verifier.
    receipt_fixture = {
        "record_identity": "sha256:" + identity,
        "workspace_digest": before["record"]["workspace_digest"],
        "acceptance": "NOT_VERIFIED",
        "checks": 0,
        "passed_checks": 0,
        "reason": "SYNTHETIC_RECEIPT_NO_VERIFIER_EXECUTION",
    }
    receipt_fixture["receipt_digest"] = canonical_digest(receipt_fixture)
    receipt_path = policy.store / identity / "verification.json"
    receipt_path.write_bytes(encode(receipt_fixture))
    receipt_path.chmod(0o400)
    before = evidence.view(old_policy, identity)
    exported = evidence.export_record(old_policy, identity)
    replayed = evidence.replay_export(exported, sha256_bytes(exported))
    receipt = evidence.verification_receipt(old_policy, identity)
    assert receipt is not None
    original_files = {
        str(p): p.read_bytes() for p in (policy.store / identity).rglob("*") if p.is_file()
    }
    data = zipped([("main.py", b"source")])
    review = service.preview(data, "unknown")
    service.confirm(
        old_policy,
        data,
        "unknown",
        consent=service.CONSENT,
        archive_sha256=review["manifest"]["archive_sha256"],
        manifest_sha256=review["manifest_sha256"],
        signature=review["review_signature"],
    )
    assert evidence.view(old_policy, identity) == before
    assert evidence.export_record(old_policy, identity) == exported
    assert evidence.replay_export(exported, sha256_bytes(exported)) == replayed
    assert evidence.verification_receipt(old_policy, identity) == receipt
    assert {
        str(p): p.read_bytes() for p in (policy.store / identity).rglob("*") if p.is_file()
    } == original_files
    assert [r["identity"] for r in evidence.list_records(old_policy)] == [identity]


def test_forged_deflate_size_and_crc_cannot_hide_unscanned_suffix() -> None:
    # A forged central CRC/size for the prefix fooled ZipExtFile's truncation.
    data = bytearray(
        zipped([("main.py", b"safe prefix then api_key='abcdefghijklmno'")], zipfile.ZIP_DEFLATED)
    )
    central = data.index(b"PK\x01\x02")
    import zlib

    for offset, crc_offset, size_offset in ((0, 14, 22), (central, 16, 24)):
        struct.pack_into("<I", data, offset + crc_offset, zlib.crc32(b"safe prefix"))
        struct.pack_into("<I", data, offset + size_offset, len(b"safe prefix"))
    result = service.preview(bytes(data), "unknown")
    assert result["rejections"][0]["reason"] == "CORRUPT_ARCHIVE"


@pytest.mark.parametrize("kind", ["crc", "local_size", "deflate", "directory_flag", "dos_special"])
def test_corruption_and_special_metadata_never_crash(kind: str) -> None:
    data = bytearray(zipped([("main.py", b"source")], zipfile.ZIP_DEFLATED))
    central = data.index(b"PK\x01\x02")
    if kind == "crc":
        struct.pack_into("<I", data, 14, 123)
        struct.pack_into("<I", data, central + 16, 123)
    elif kind == "local_size":
        struct.pack_into("<I", data, 22, 99)
    elif kind == "deflate":
        data[37:40] = b"\xff\xff\xff"
    elif kind == "directory_flag":
        struct.pack_into("<I", data, central + 38, 0x10)
    else:
        struct.pack_into("<I", data, central + 38, 0x08)
    assert service.preview(bytes(data), "unknown")["status"] == "REJECTED"


def test_full_scan_and_final_subset_envelopes_are_distinct() -> None:
    data = zipped([("main.py", b"source"), *((f"cache/{i}.txt", b"cached") for i in range(2281))])
    manifest, files = service.scan(data)
    assert list(files) == ["main.py"] and len(manifest["excluded"]) == 2281
    assert len(manifest["included"]) + len(manifest["excluded"]) == 2282


@pytest.mark.parametrize("name,content", [("image.gif", b"GIF89a"), ("controls.txt", b"\x01\x02")])
def test_binary_formats_excluded_even_if_utf8_decodable(name: str, content: bytes) -> None:
    manifest, files = service.scan(zipped([("main.py", b"source"), (name, content)]))
    assert list(files) == ["main.py"]
    assert manifest["excluded"][0]["reason"] == "BINARY_OR_NON_UTF8"


def test_directory_entries_and_stream_descriptors_are_accounted_for() -> None:
    class NonSeeking(io.BytesIO):
        def seekable(self) -> bool:
            return False

        def seek(self, offset: int, whence: int = 0) -> int:
            raise OSError("non-seeking fixture")

    out = NonSeeking()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("src/", b"")
        archive.writestr("src/main.py", b"source")
    manifest, files = service.scan(out.getvalue())
    assert manifest["directories"] == ["src"] and list(files) == ["src/main.py"]


@pytest.mark.parametrize(
    "query",
    ["path=/tmp/code.zip", "workspace=/tmp/workspace", "declared_tool=codex&declared_tool=other"],
)
async def test_upload_refuses_filesystem_or_ambiguous_query_parameters(
    client: AsyncClient, query: str
) -> None:
    response = await client.post(PREFIX + "/archive?" + query, content=b"never-read")
    assert response.status_code == 422 and response.json()["error"]["code"] == "ZIP_REQUEST_INVALID"


async def test_unknown_length_upload_is_bounded_and_timeout_cleans_memory(
    policy: EvidencePolicy,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def too_large() -> dict[str, Any]:
        return {"type": "http.request", "body": b"x" * (service.MAX_UPLOAD + 1), "more_body": False}

    with pytest.raises(WorkbenchAPIError) as limit:
        await upload(Request({"type": "http", "headers": []}, too_large))
    assert limit.value.code == "ZIP_UPLOAD_LIMIT"
    original = asyncio.timeout
    monkeypatch.setattr(asyncio, "timeout", lambda _seconds: original(0.001))

    async def delayed() -> dict[str, Any]:
        await asyncio.sleep(1)
        return {"type": "http.request", "body": b"", "more_body": False}

    with pytest.raises(WorkbenchAPIError) as timeout:
        await upload(Request({"type": "http", "headers": []}, delayed))
    assert timeout.value.code == "ZIP_UPLOAD_TRUNCATED"
    assert not policy.store.exists()


def test_staging_must_be_outside_all_protected_roots(
    policy: EvidencePolicy, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Deliberately configure the parent's entirety as a protected task/workspace root.
    monkeypatch.setattr(service, "protected_roots", lambda _policy: [policy.store.parent])
    data = zipped([("main.py", b"source")])
    review = service.preview(data, "unknown")
    with pytest.raises(service.Rejected, match="STAGING_LOCATION_UNSAFE"):
        service.confirm(
            policy,
            data,
            "unknown",
            consent=service.CONSENT,
            archive_sha256=review["manifest"]["archive_sha256"],
            manifest_sha256=review["manifest_sha256"],
            signature=review["review_signature"],
        )
    assert not list(policy.store.parent.glob(".code-snapshot-staging-*"))
    assert list((policy.store / service.STORE_NAME).iterdir()) == [
        policy.store / service.STORE_NAME / ".lock"
    ]


async def test_media_type_override_cannot_escape_the_zip_route(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_database() -> None:
        raise AssertionError("Non-JSON request reached configuration/database code")

    from harnesslab.api import local_configuration

    monkeypatch.setattr(local_configuration, "workspace_catalog", no_database)
    for path in (
        "/api/local-configuration/models/fixture",
        "/api/local-configuration/harnesses/fixture",
    ):
        response = await client.put(path + "?content_type=application/zip", content=b"never-read")
        assert response.status_code == 415 and response.json()["error"]["code"] == "JSON_REQUIRED"
    schema = (await client.get("/openapi.json")).json()
    for route in schema["paths"].values():
        for operation in route.values():
            assert all(p["name"] != "content_type" for p in operation.get("parameters", []))


async def test_multiple_content_rejections_never_write_or_echo(
    client: AsyncClient, policy: EvidencePolicy
) -> None:
    content = b"api_key='synthetic-value-for-rejection'"
    data = zipped(
        [
            ("safe.py", b"source"),
            (".venv/dependency.py", content),
            ("app/config.py", content),
            ("nested.zip", content),
        ]
    )
    before = sorted(policy.store.parent.rglob("*"))
    response = await client.post(PREFIX + "/archive", content=data)
    result = response.json()
    assert response.status_code == 200 and result["status"] == "REJECTED"
    assert [(item["path"], item["reason"]) for item in result["rejections"]] == [
        (".venv/dependency.py", "CREDENTIAL_CONTENT"),
        ("app/config.py", "CREDENTIAL_CONTENT"),
        ("nested.zip", "CREDENTIAL_CONTENT"),
        ("nested.zip", "NESTED_ARCHIVE"),
    ]
    assert result["rejections_truncated"] is False
    assert set(result) == {
        "status",
        "rejections",
        "rejection_limit",
        "rejections_truncated",
        "limits",
    }
    assert "synthetic-value-for-rejection" not in response.text
    denied = await client.post(PREFIX + "/archive?action=confirm", content=data)
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "ZIP_CREDENTIAL_CONTENT"
    assert sorted(policy.store.parent.rglob("*")) == before
    assert not policy.store.exists()


@pytest.mark.parametrize("count", [50, 51, 80])
@pytest.mark.parametrize("stage", ["metadata", "content"])
async def test_rejection_summary_is_bounded_without_writes(
    client: AsyncClient, policy: EvidencePolicy, count: int, stage: str
) -> None:
    items: list[tuple[str | zipfile.ZipInfo, bytes]] = [
        (f"../bad{i}.py", b"source")
        if stage == "metadata"
        else (f"app/file{i}.py", b"api_key='synthetic-rejection-value'")
        for i in range(count)
    ]
    before = sorted(policy.store.parent.rglob("*"))
    data = zipped(items)
    result = (await client.post(PREFIX + "/archive", content=data)).json()
    assert result["status"] == "REJECTED"
    assert result["rejection_limit"] == service.MAX_REJECTIONS == 50
    assert len(result["rejections"]) == min(count, 50)
    assert result["rejections_truncated"] is (count > 50)
    assert [item["entry"] for item in result["rejections"]] == list(range(min(count, 50)))
    assert (
        all(item["path"] is None for item in result["rejections"])
        if stage == "metadata"
        else all(item["reason"] == "CREDENTIAL_CONTENT" for item in result["rejections"])
    )
    assert (await client.post(PREFIX + "/archive?action=confirm", content=data)).status_code == 409
    assert sorted(policy.store.parent.rglob("*")) == before
    assert not policy.store.exists()


def test_metadata_rejections_aggregate_without_reading_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    link = zipfile.ZipInfo("link.py")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o600) << 16
    data = zipped([("../bad.py", b"source"), (".env", b"source"), (link, b"target")])

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("unsafe metadata must stop all content reads")

    monkeypatch.setattr(zipfile.ZipFile, "open", forbidden)
    result = service.preview(data, "unknown")
    assert [item["reason"] for item in result["rejections"]] == [
        "UNSAFE_PATH",
        "PRIVATE_OR_UNSAFE_NAME",
        "SYMLINK_OR_SPECIAL_FILE",
    ]
    assert result["rejections_truncated"] is False


def test_corruption_stops_scan_and_retains_prior_rejections() -> None:
    data = bytearray(
        zipped(
            [
                ("config.py", b"api_key='synthetic-rejection-value'"),
                ("broken.py", b"source"),
                ("later.py", b"api_key='synthetic-rejection-value'"),
            ]
        )
    )
    # Change only the second local CRC. The central directory remains readable.
    second = data.index(b"PK\x03\x04", 4)
    struct.pack_into("<I", data, second + 14, 0)
    result = service.preview(bytes(data), "unknown")
    assert [item["reason"] for item in result["rejections"]] == [
        "CREDENTIAL_CONTENT",
        "CORRUPT_ARCHIVE",
    ]
    assert result["rejections_truncated"] is False
