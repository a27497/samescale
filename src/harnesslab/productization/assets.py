"""Trusted source/build resources, shared by the launcher and wheel build hook."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

MANIFEST = "samescale-build.json"


class AssetError(RuntimeError):
    exit_code = 2


class AssetBuildError(AssetError):
    exit_code = 1


def distribution_root() -> Path:
    source = Path(__file__).resolve().parents[3]
    if (source / "src/harnesslab/__init__.py").is_file():
        return source
    return Path(__file__).resolve().parent / "distribution"


def source_digest(root: Path) -> str:
    frontend = root / "frontend"
    paths = [
        frontend / name
        for name in (
            "index.html",
            "package.json",
            "package-lock.json",
            "tsconfig.json",
            "vite.config.ts",
        )
    ]
    paths.extend(path for path in (frontend / "src").rglob("*") if path.is_file())
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(frontend).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def validate_bundle(dist: Path) -> None:
    try:
        manifest = json.loads((dist / MANIFEST).read_text())
        files = manifest["files"]
        if not isinstance(files, dict) or "index.html" not in files or len(files) < 2:
            raise ValueError("incomplete manifest")
        for relative, digest in files.items():
            path = (dist / relative).resolve()
            if not path.is_relative_to(dist.resolve()) or not path.is_file():
                raise ValueError("missing asset")
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError("asset digest mismatch")
        if b'id="app"' not in (dist / "index.html").read_bytes():
            raise ValueError("missing application entry")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise AssetError(
            "UI assets are missing or invalid; rebuild or reinstall the product wheel."
        ) from exc


def build_workbench(root: Path) -> Path:
    """Compile only the trusted distribution's UI using its locked npm dependencies."""
    try:
        version = subprocess.run(["node", "--version"], capture_output=True, check=True, timeout=10)
        numbers = tuple(
            int(part) for part in version.stdout.decode().strip().removeprefix("v").split(".")
        )
        if not (24, 18, 1) <= numbers < (25, 0, 0):
            raise AssetError(
                "Building from source requires Node >=24.18.1 <25. Installed wheels do not."
            )
        for args in (["npm", "ci", "--no-audit", "--no-fund"], ["npm", "run", "build"]):
            subprocess.run(
                args, cwd=root / "frontend", capture_output=True, check=True, timeout=600
            )
    except FileNotFoundError:
        raise AssetError(
            "Source builds require Node >=24.18.1 <25 and npm. Install them and retry "
            "`samescale demo`, or install a built wheel."
        ) from None
    except (OSError, subprocess.SubprocessError, ValueError):
        raise AssetBuildError(
            "UI build failed. Source builds require Node >=24.18.1 <25, npm "
            "and package download access. "
            "Correct the prerequisite and retry; no server was started."
        ) from None
    dist = root / "frontend/dist"
    files = {
        path.relative_to(dist).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(dist.rglob("*"))
        if path.is_file() and path.name != MANIFEST
    }
    (dist / MANIFEST).write_text(
        json.dumps({"source_digest": source_digest(root), "files": files}, sort_keys=True)
    )
    validate_bundle(dist)
    return dist


def demo_bundle(*, build: bool = False) -> Path:
    root = distribution_root()
    dist = root / "frontend/dist"
    source = root == Path(__file__).resolve().parents[3]
    try:
        validate_bundle(dist)
        if source and json.loads((dist / MANIFEST).read_text())["source_digest"] != source_digest(
            root
        ):
            raise AssetError("UI source changed; run `samescale demo` to rebuild it.")
    except (AssetError, KeyError, OSError):
        if not (source and build):
            raise AssetError(
                "UI bundle unavailable. Run `samescale demo` in a source checkout, "
                "or reinstall a built wheel."
            ) from None
        print(
            "Preparing the UI from locked source dependencies (first start or source changed)…",
            flush=True,
        )
        return build_workbench(root)
    return dist
