"""Keyless, synthetic setup checks; historical bytes are independently pinned."""

from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path
from typing import Any

import pytest
from scripts import samescale_local_init as init

from harnesslab.episodes.hooks import encode
from harnesslab.external_evidence import service
from harnesslab.external_evidence.models import EvidencePolicy
from harnesslab.tasks.package import sha256_bytes
from tests.test_external_evidence import native_source

TASK_DIGEST = "sha256:" + "a" * 64


def setup(tmp_path: Path) -> tuple[Path, Path]:
    workspace = tmp_path / "reviewed"
    workspace.mkdir()
    (workspace / "app.py").write_text("VALUE = 42\n")
    return workspace, tmp_path / "private"


def command(workspace: Path, root: Path, action: str = "init") -> list[str]:
    return [
        action,
        str(workspace),
        "--state-root",
        str(root),
        "--task-reference",
        "minishop-standard-library@1.0.0",
        "--task-digest",
        TASK_DIGEST,
    ]


def run(capsys: pytest.CaptureFixture[str], args: list[str]) -> tuple[int, dict[str, Any]]:
    code = init.main(args)
    captured = capsys.readouterr()
    assert not captured.err
    return code, json.loads(captured.out)


def inventory(path: Path) -> dict[str, bytes]:
    return {p.relative_to(path).as_posix(): p.read_bytes() for p in path.rglob("*") if p.is_file()}


def test_preflight_is_read_only_and_digest_uses_service(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    workspace, root = setup(tmp_path)
    before = inventory(tmp_path)
    code, result = run(capsys, command(workspace, root, "preflight"))
    assert code == 0 and result["status"] == "READY"
    assert result["workspace_digest"] == service.content_digest(inventory(workspace))
    assert result["issues"] == [] and "operator_token" not in result
    assert inventory(tmp_path) == before and not root.exists()


def test_init_permissions_token_snapshot_and_real_code_only_ingestion(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, root = setup(tmp_path)
    (workspace / "nested/a/b").mkdir(parents=True)
    (workspace / "nested/a/b/notes.txt").write_text("仅本地文本\n")
    code, result = run(capsys, command(workspace, root))
    assert code == 0 and result["status"] == "INITIALIZED"
    token = result["operator_token"]
    assert len(token) >= 32
    assert inventory(root / "workspace") == inventory(workspace)
    for path in [root, *root.rglob("*")]:
        assert stat.S_IMODE(path.stat().st_mode) == (0o700 if path.is_dir() else 0o600)
        if path.is_file():
            assert token.encode() not in path.read_bytes()
    policy_path = root / "evidence-policy.json"
    raw = json.loads(policy_path.read_text())
    assert raw["sources"][0]["source_kind"] == "unverified"
    assert "harness" not in raw["sources"][0] and "path" not in raw["sources"][0]
    receipt = json.loads((root / "exclusions.json").read_text())
    assert receipt["excluded_paths"] == []
    assert {".git", ".env*", "node_modules", ".codex"} <= set(receipt["exclusion_rules"])
    monkeypatch.setenv("HARNESSLAB_EXTERNAL_EVIDENCE_POLICY", str(policy_path))
    policy = service.load_policy()
    record = service.ingest(policy, "minishop-final")["record"]
    assert record["original_acceptance"] == "NOT_VERIFIED" and record["trace"] == []
    assert record["completeness"]["coverage"] == "NO_RUN_RECORD"
    assert record["source_authenticity"] == "NOT_ATTESTED"
    assert record["comparison_eligible"] is False


@pytest.mark.parametrize("kind", ["empty", "count", "size", "total"])
def test_empty_and_over_limit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], kind: str
) -> None:
    workspace, root = setup(tmp_path)
    expected = {
        "empty": "EMPTY_WORKSPACE",
        "count": "FILE_LIMIT",
        "size": "FILE_TOO_LARGE",
        "total": "BYTE_LIMIT",
    }[kind]
    if kind == "empty":
        (workspace / "app.py").unlink()
    elif kind == "count":
        for n in range(500):
            (workspace / f"file{n}.txt").write_text("")
    elif kind == "size":
        (workspace / "large.txt").write_bytes(b"x" * 4_000_001)
    else:
        for n in range(2):
            (workspace / f"file{n}.txt").write_bytes(b"x" * 2_000_000)
    code, result = run(capsys, command(workspace, root))
    assert code == 2 and expected in {i["code"] for i in result["issues"]}
    assert not root.exists()


@pytest.mark.parametrize(
    "content",
    [
        b"\xff",
        b"\x00",
        b"\x01",
        b"\x7f",
        b"api_key = 'sk-" + b"x" * 24 + b"'",
        b"-----BEGIN PRIVATE KEY-----",
    ],
)
def test_binary_non_utf8_and_credentials(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], content: bytes
) -> None:
    workspace, root = setup(tmp_path)
    (workspace / "bad.txt").write_bytes(content)
    code, result = run(capsys, command(workspace, root))
    assert code == 2 and "UNSAFE_CONTENT" in {i["code"] for i in result["issues"]}
    assert content not in init.encode(result) and not root.exists()


@pytest.mark.parametrize(
    "name",
    [
        ".git",
        ".env",
        ".env.local",
        "node_modules",
        ".codex",
        ".claude",
        "oracle",
        "verifier",
        "auth.json",
        "bad:name",
        "bad\\name",
        "bad\nname",
    ],
)
def test_private_and_invalid_names_are_rejected_without_reading(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    workspace, root = setup(tmp_path)
    private = workspace / name
    private.mkdir()
    (private / "never-open.txt").write_text("not read")
    original = os.listdir

    def guarded(fd: Any) -> list[str]:
        if isinstance(fd, int):
            assert Path(f"/proc/self/fd/{fd}").resolve() != private
        return original(fd)

    monkeypatch.setattr(os, "listdir", guarded)
    code, result = run(capsys, command(workspace, root, "preflight"))
    assert code == 2 and "UNSAFE_NAME" in {i["code"] for i in result["issues"]}
    assert not root.exists()


@pytest.mark.parametrize("kind", ["symlink", "directory-link", "hardlink", "fifo"])
def test_links_and_special_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], kind: str
) -> None:
    workspace, root = setup(tmp_path)
    if kind == "symlink":
        (workspace / "alias").symlink_to(workspace / "app.py")
    elif kind == "directory-link":
        (workspace / "alias").symlink_to(tmp_path, target_is_directory=True)
    elif kind == "hardlink":
        os.link(workspace / "app.py", workspace / "alias")
    else:
        os.mkfifo(workspace / "alias")
    code, result = run(capsys, command(workspace, root))
    assert code == 2 and "UNSAFE_FILE" in {i["code"] for i in result["issues"]}
    assert not root.exists()


def test_preflight_reports_every_rejection(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    workspace, root = setup(tmp_path)
    (workspace / ".git").mkdir()
    (workspace / ".env").write_text("never read")
    (workspace / "bad.txt").write_bytes(b"\xff")
    (workspace / "link").symlink_to(workspace / "app.py")
    code, result = run(capsys, command(workspace, root, "preflight"))
    assert code == 2 and len(result["issues"]) == 4
    assert all(i["reason"] for i in result["issues"])


@pytest.mark.parametrize("call", [2, 3, 4])
def test_digest_drift_before_and_after_write_keeps_no_policy(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, call: int
) -> None:
    workspace, root = setup(tmp_path)
    digest = service.content_digest
    count = 0

    def changing(files: dict[str, bytes]) -> str:
        nonlocal count
        count += 1
        return "sha256:" + "b" * 64 if count == call else digest(files)

    monkeypatch.setattr(service, "content_digest", changing)
    code, result = run(capsys, command(workspace, root))
    assert code == 2 and not root.exists() and "operator_token" not in result


def test_repeated_init_refuses_without_overwriting_or_redisplaying_token(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    workspace, root = setup(tmp_path)
    _, first = run(capsys, command(workspace, root))
    before = inventory(root)
    code, second = run(capsys, command(workspace, root))
    assert code == 2 and "STATE_EXISTS" in {i["code"] for i in second["issues"]}
    assert first["operator_token"] not in json.dumps(second) and inventory(root) == before


def test_forbidden_roots_and_mnt_opt_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for path in (tmp_path, Path("/"), tmp_path / ".codex/source", tmp_path / ".claude/source"):
        files, issues, _ = init.scan(path)
        assert not files and issues
    assert init.path_issues(Path("/mnt/reviewed"), False)[0]
    issues, warnings = init.path_issues(Path("/mnt/reviewed"), True)
    assert issues == [] and warnings and "MNT_ALLOWED" in warnings[0]


def test_link_ancestor_and_overlapping_destination_refuse(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    workspace, root = setup(tmp_path)
    alias = tmp_path / "alias"
    alias.symlink_to(workspace, target_is_directory=True)
    assert run(capsys, command(alias, root))[0] == 2
    assert run(capsys, command(workspace, workspace / "state"))[0] == 2
    assert not root.exists() and not (workspace / "state").exists()


def test_print_serve_contains_no_token_and_never_starts_process(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, root = setup(tmp_path)
    _, result = run(capsys, command(workspace, root))
    before = inventory(root)
    import subprocess

    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("execution forbidden"))
    assert init.main(["print-serve", "--state-root", str(root)]) == 0
    output = capsys.readouterr().out
    assert result["operator_token"] not in output
    assert "--host 127.0.0.1" in output and "HARNESSLAB_ENABLE_REAL_CODEX=false" in output
    assert "read -r -s" in output and inventory(root) == before
    assert init.main(["print-serve", "--state-root", str(root), "--port", "0"]) == 2
    capsys.readouterr()


def test_no_harness_or_source_kind_override(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as error:
        init.main(["init", "--harness", "deepseek"])
    assert error.value.code == 2
    capsys.readouterr()


def test_script_size_and_legacy_export_replay_bytes_unchanged(tmp_path: Path) -> None:
    assert len(Path(init.__file__).read_text().splitlines()) <= 300
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/external-evidence-legacy.json").read_text()
    )
    policy = EvidencePolicy(
        store=tmp_path / "records", sources=(native_source(tmp_path / "source"),)
    )
    root = policy.store / fixture["identity"][7:]
    (root / "workspace").mkdir(parents=True)
    policy.store.chmod(0o700)
    (root / "record.json").write_bytes(encode(fixture["record"]))
    (root / "workspace/answer.py").write_text("ANSWER = 42\n")
    before = inventory(root)
    exported = service.export_record(policy, fixture["identity"][7:])
    # Frozen from main@889f301 before this script; expected values are never regenerated.
    assert (
        sha256_bytes(exported)
        == "sha256:abbcc4afc6b9f61875b8a6900588f917c23f43a917822027d91c79c929d6f4c0"
    )
    pin = sha256_bytes(exported)
    replay_a = encode(service.replay_export(exported, pin))
    replay_b = encode(service.replay_export(exported, pin))
    assert replay_a == replay_b
    assert (
        sha256_bytes(replay_a)
        == "sha256:a9e055c405d1364437df5a7174674fdbae6d4893e27273d52ec396a7465c5766"
    )
    assert inventory(root) == before


def test_fastapi_audit_public_identity_and_scope() -> None:
    root = Path(__file__).resolve().parents[1]
    summary = json.loads((root / "docs/qa/minishop-fastapi-sqlite-1.0.0.json").read_text())
    assert summary["task_reference"] == "minishop-fastapi-sqlite@1.0.0"
    assert summary["audit_kind"] == "post-delivery"
    assert summary["protected_paths"] == []
    assert summary["eligible_for_planning"] is True
    assert summary["requirement_sha256"] == (
        "sha256:31c93f958b80472ada981cc30f210d41d313bc23a7d27acc2ad4fd15f3070bdc"
    )
    for field in (
        "task_digest",
        "verifier_digest",
        "qualification_identity",
        "image_id",
        "baseline_adapter_sha256",
        "oracle_adapter_sha256",
    ):
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", summary[field])
    assert summary["baseline_adapter_sha256"] != summary["oracle_adapter_sha256"]
    assert summary["subject_adapter"] == "NOT_WRITTEN"
    assert summary["subject_snapshot"] == "NOT_ACCESSED_NOT_RUN"
    for kind in ("baseline", "oracle"):
        assert 0 < summary[f"{kind}_workspace_files"] <= 500
        assert 0 < summary[f"{kind}_workspace_bytes"] <= 4_000_000
    assert summary["source_file_count"] > summary["baseline_workspace_files"]
    assert {"browser_cart", "browser_checkout", "visual_responsive", "windows"} <= set(
        summary["not_covered"]
    )


@pytest.mark.parametrize("kind", ["baseline", "oracle"])
def test_fastapi_audit_three_repeats_have_complete_consistent_results(kind: str) -> None:
    root = Path(__file__).resolve().parents[1]
    summary = json.loads((root / "docs/qa/minishop-fastapi-sqlite-1.0.0.json").read_text())
    contract = (root / "docs/MINISHOP_FASTAPI_SQLITE.md").read_text()
    mapped = re.findall(r"^\| (C\d{2}) \|", contract, re.MULTILINE)
    assert len(mapped) == 26 and len(set(mapped)) == 26
    rows = [row for row in summary["runs"] if row["variant"] == kind]
    assert len(rows) == 3 and len({row["label"] for row in rows}) == 3
    vectors = []
    for row in rows:
        assert row["category"] == "SUBJECT_RESULT"
        assert 0 < row["whole_seconds"] <= 25
        assert len(row["checks"]) == 26
        assert [c["name"].split("_", 1)[0] for c in row["checks"]] == mapped
        vector = [c["passed"] for c in row["checks"]]
        assert all(type(value) is bool for value in vector)
        assert all(vector) is (kind == "oracle")
        assert row["passed_checks"] == sum(vector)
        vectors.append(vector)
    assert vectors[0] == vectors[1] == vectors[2]


def test_fastapi_audit_timings_partition_whole_runs() -> None:
    root = Path(__file__).resolve().parents[1]
    summary = json.loads((root / "docs/qa/minishop-fastapi-sqlite-1.0.0.json").read_text())
    for row in summary["runs"]:
        assert 0 < row["whole_seconds"] <= 25
        assert set(row["segments_seconds"]) == {
            "create_preflight",
            "attach",
            "start_attach",
            "cleanup",
            "other",
        }
        assert all(value >= 0 for value in row["segments_seconds"].values())
        assert abs(sum(row["segments_seconds"].values()) - row["whole_seconds"]) < 0.002
        body = row["body_seconds"]
        assert set(body) == {"server_start", "checks", "shutdown", "other", "total"}
        assert all(value >= 0 for value in body.values())
        assert abs(sum(v for k, v in body.items() if k != "total") - body["total"]) < 0.002
        assert body["total"] <= row["whole_seconds"]


def test_fastapi_audit_single_defect_controls_fail_as_business_results() -> None:
    root = Path(__file__).resolve().parents[1]
    summary = json.loads((root / "docs/qa/minishop-fastapi-sqlite-1.0.0.json").read_text())
    rows = [row for row in summary["runs"] if row["variant"].startswith("control-")]
    assert {row["variant"] for row in rows} == {
        "control-price",
        "control-partial",
        "control-retry",
    }
    assert len(rows) == 3
    for row in rows:
        assert row["category"] == "SUBJECT_RESULT"
        assert len(row["checks"]) == 26 and any(not c["passed"] for c in row["checks"])
        assert row["passed_checks"] == sum(c["passed"] for c in row["checks"])
        assert row["single_edit_occurrences"] == 1
