"""Prepare one reviewed code-only snapshot; never start services or execute submitted code."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shlex
import shutil
import stat
from pathlib import Path
from typing import Any

from harnesslab.api.workbench_errors import WorkbenchAPIError
from harnesslab.external_evidence import service
from harnesslab.external_evidence.models import ApprovedSource, EvidencePolicy
from harnesslab.local_plans.tasks import read_owned_json
from harnesslab.productization.assets import distribution_root

BLOCKED = service.PRIVATE_PARTS | service.PRIVATE_NAMES | {"node_modules", ".venv", "__pycache__"}
BLOCKED.update({".pytest_cache", ".mypy_cache", ".ruff_cache", "venv"})
MAX_FILES, MAX_BYTES = 500, 4_000_000


def path_issues(path: Path, allow_mnt: bool) -> tuple[list[dict[str, str]], list[str]]:
    issues, warnings = [], []
    try:
        service.safe_root(path)
        if any(p.lower() in BLOCKED or p.lower() == "downloads" for p in path.parts):
            raise ValueError("private path")
    except (ValueError, WorkbenchAPIError, OSError):
        issues.append(issue("UNSAFE_ROOT", "Use a canonical, nonprivate, link-free path."))
    if path == Path("/mnt") or Path("/mnt") in path.parents:
        if allow_mnt:
            warnings.append("MNT_ALLOWED: mounted filesystems may weaken POSIX permissions.")
        else:
            issues.append(issue("MNT_REFUSED", "Use --allow-mnt to explicitly allow /mnt."))
    return issues, warnings


def scan(
    root: Path, allow_mnt: bool = False
) -> tuple[dict[str, bytes], list[dict[str, str]], list[str]]:
    issues, warnings = path_issues(root, allow_mnt)
    files: dict[str, bytes] = {}
    count = total = 0

    def reject(code: str, reason: str, name: str = "") -> None:
        issues.append({"code": code, "reason": reason, "path": name})

    def visit(directory: int, prefix: str) -> None:
        nonlocal count, total
        for name in sorted(os.listdir(directory)):
            relative = prefix + name
            try:
                service.safe_name(relative)
                if name.lower() in BLOCKED or name.lower() == "downloads":
                    raise ValueError("excluded name")
            except ValueError:
                reject(
                    "UNSAFE_NAME",
                    "Private, excluded or invalid filename; contents not read.",
                    "<redacted>"
                    if service.SECRET.search(relative.encode(errors="replace"))
                    else relative,
                )
                continue
            try:
                info = os.stat(name, dir_fd=directory, follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    child = os.open(
                        name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
                    )
                    try:
                        visit(child, relative + "/")
                    finally:
                        os.close(child)
                elif not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    reject("UNSAFE_FILE", "Require an ordinary file with one hard link.", relative)
                else:
                    count += 1
                    total += info.st_size
                    if info.st_size > MAX_BYTES:
                        reject("FILE_TOO_LARGE", "File exceeds 4,000,000 bytes.", relative)
                        continue
                    fd = os.open(
                        name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
                    )
                    with os.fdopen(fd, "rb") as stream:
                        actual = os.fstat(stream.fileno())
                        if (
                            not os.path.samestat(actual, info)
                            or actual.st_mode != info.st_mode
                            or actual.st_nlink != 1
                        ):
                            reject("FILE_CHANGED", "File changed during acquisition.", relative)
                            continue
                        data = stream.read(MAX_BYTES + 1)
                    if len(data) != info.st_size:
                        reject("FILE_CHANGED", "File size changed during acquisition.", relative)
                        continue
                    try:
                        service.safe_content(data)
                        if any((b < 32 and b not in (9, 10, 13)) or b == 127 for b in data):
                            raise ValueError("binary control bytes")
                    except ValueError:
                        reject(
                            "UNSAFE_CONTENT", "Non-UTF-8, binary or credential content.", relative
                        )
                        continue
                    if count <= MAX_FILES and total <= MAX_BYTES:
                        files[relative] = data
            except (OSError, UnicodeError):
                reject("UNREADABLE_FILE", "Cannot safely read this entry.", relative)

    if not issues:
        try:
            fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                visit(fd, "")
            finally:
                os.close(fd)
        except OSError:
            reject("UNREADABLE_ROOT", "Workspace must be an accessible directory.")
        if count == 0:
            reject("EMPTY_WORKSPACE", "Workspace must contain at least one ordinary file.")
        if count > MAX_FILES:
            reject("FILE_LIMIT", "Workspace exceeds 500 files.")
        if total > MAX_BYTES:
            reject("BYTE_LIMIT", "Workspace exceeds 4,000,000 bytes.")
    return files, issues, warnings


def write_private(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def encode(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode()


def issue(code: str, reason: str) -> dict[str, str]:
    return {"code": code, "reason": reason}


def refused(result: dict[str, Any], code: str, reason: str) -> dict[str, Any]:
    return {**result, "status": "REFUSED", "issues": [issue(code, reason)]}


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    workspace, root = args.workspace, args.state_root
    files, issues, warnings = scan(workspace, args.allow_mnt)
    output_issues, output_warnings = path_issues(root, args.allow_mnt)
    issues.extend(output_issues)
    warnings.extend(output_warnings)
    if root.exists():
        issues.append(issue("STATE_EXISTS", "Use a fresh directory; policy overwrite is refused."))
    if service.overlap(root, workspace) or service.overlap(root, distribution_root()):
        issues.append(issue("OVERLAP", "State must be outside Workspace and the repository."))
    try:
        source = ApprovedSource(
            source_id=args.source_id,
            format="code-only-v1",
            source_kind="unverified",
            workspace=root / "workspace",
            workspace_digest=service.content_digest(files),
            task_reference=args.task_reference,
            task_digest=args.task_digest,
        )
        policy = EvidencePolicy(
            store=root / "records",
            sources=(source,),
            verifier_image_id=args.verifier_image_id,
            runtime_root=root / "runtime",
            artifact_root=root / "artifacts",
        )
        service.safe_content(encode(source.binding))
    except ValueError:
        issues.append(issue("INVALID_BINDING", "Check source id and exact task/image digests."))
    result: dict[str, Any] = {
        "status": "REFUSED" if issues else "READY",
        "issues": issues,
        "warnings": warnings,
        "source_kind": "unverified",
        "accepted_files": len(files),
        "bytes": sum(map(len, files.values())),
    }
    if issues:
        return result
    result["workspace_digest"] = source.workspace_digest
    if args.command == "preflight":
        return result
    again, errors, _ = scan(workspace, args.allow_mnt)
    if errors or service.content_digest(again) != source.workspace_digest:
        return refused(result, "DIGEST_CHANGED", "Workspace changed before writing; review again.")
    created = False
    try:
        root.mkdir(mode=0o700)
        created = True
        for name in ("workspace", "records", "runtime", "artifacts"):
            (root / name).mkdir(mode=0o700)
        for name, data in files.items():
            destination = root / "workspace" / name
            parent = root / "workspace"
            for component in Path(name).parts[:-1]:
                parent /= component
                parent.mkdir(exist_ok=True, mode=0o700)
            write_private(destination, data)
        copied, errors, _ = scan(root / "workspace", args.allow_mnt)
        after, source_errors, _ = scan(workspace, args.allow_mnt)
        if (
            errors
            or source_errors
            or service.content_digest(copied) != source.workspace_digest
            or service.content_digest(after) != source.workspace_digest
        ):
            raise ValueError("snapshot changed")
        receipt = {
            "schema_version": 1,
            "workspace_digest": source.workspace_digest,
            "task_reference": args.task_reference,
            "task_digest": args.task_digest,
            "files": sorted(files),
            "bytes": result["bytes"],
            "warnings": warnings,
            "excluded_paths": [],
            "exclusion_rules": [*sorted(BLOCKED), ".env*", "Downloads"],
            "exclusion_behavior": "REFUSE_WITHOUT_READING_OR_SILENTLY_DROPPING",
            "source_kind": "unverified",
            "agent_executed": False,
            "verifier_executed": False,
        }
        write_private(root / "exclusions.json", encode(receipt))
        payload = encode(policy.model_dump(mode="json", exclude_none=True))
        write_private(root / "evidence-policy.json", payload)
        return {**result, "status": "INITIALIZED", "operator_token": secrets.token_urlsafe(32)}
    except (OSError, ValueError):
        if created:
            shutil.rmtree(root)
        return refused(result, "WRITE_OR_DIGEST_FAILURE", "Write failed; no policy retained.")


def print_serve(args: argparse.Namespace) -> str:
    issues, warnings = path_issues(args.state_root, args.allow_mnt)
    if issues:
        raise ValueError("unsafe policy root")
    path = args.state_root / "evidence-policy.json"
    if path.stat().st_mode & 0o077:
        raise ValueError("private policy required")
    EvidencePolicy.model_validate(read_owned_json(path))
    return "\n".join(
        [
            *("# " + warning for warning in warnings),
            "export HARNESSLAB_EXTERNAL_EVIDENCE_POLICY=" + shlex.quote(str(path)),
            "export HARNESSLAB_ENABLE_REAL_CODEX=false",
            "read -r -s -p 'Operator token: ' HARNESSLAB_LOCAL_CONFIGURATION_TOKEN",
            "export HARNESSLAB_LOCAL_CONFIGURATION_TOKEN",
            f"uv run --locked harnesslab serve --host 127.0.0.1 --port {args.port}",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("preflight", "init", "print-serve"):
        p = sub.add_parser(command)
        p.add_argument("--state-root", type=Path, required=True)
        p.add_argument("--allow-mnt", action="store_true")
        if command == "print-serve":
            p.add_argument("--port", type=int, default=58690)
        else:
            p.add_argument("workspace", type=Path)
            p.add_argument("--source-id", default="minishop-final")
            p.add_argument("--task-reference", required=True)
            p.add_argument("--task-digest", required=True)
            p.add_argument("--verifier-image-id")
    args = parser.parse_args(argv)
    try:
        if args.command == "print-serve":
            if not 1 <= args.port <= 65535:
                raise ValueError("invalid port")
            print(print_serve(args))
            return 0
        result = prepare(args)
    except (OSError, ValueError, WorkbenchAPIError):
        result = refused(
            {}, "UNSAFE_CONFIGURATION", "Check private paths, permissions and bindings."
        )
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 2 if result["status"] == "REFUSED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
