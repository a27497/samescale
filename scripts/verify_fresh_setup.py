from __future__ import annotations

import argparse
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require_text(path: str, fragment: str) -> None:
    content = (ROOT / path).read_text(encoding="utf-8")
    if fragment not in content:
        raise RuntimeError(f"{path} does not freeze {fragment!r}")


def command_output(*command: str) -> str:
    if shutil.which(command[0]) is None:
        raise RuntimeError(f"required runtime is unavailable: {command[0]}")
    result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=30)
    return (result.stdout + result.stderr).strip()


def verify_repository_contract() -> None:
    required = (
        ".python-version",
        "uv.lock",
        "docker-compose.yml",
        "alembic.ini",
        "frontend/package.json",
        "frontend/package-lock.json",
        "release/core-corpus.json",
        "release/core-real-evidence-plan.json",
        "release/release-evidence.json",
        "docs/REAL_EVIDENCE_AUTHORIZATION.md",
    )
    missing = [path for path in required if not (ROOT / path).is_file()]
    if missing:
        raise RuntimeError(f"fresh-setup inputs are missing: {missing}")
    require_text(".python-version", "3.12.14")
    require_text("pyproject.toml", 'requires-python = "==3.12.14"')
    require_text("pyproject.toml", 'required-version = "==0.12.5"')
    require_text("docker-compose.yml", "postgres:18")
    require_text(".github/workflows/ci.yml", "Java 21")
    require_text(".github/workflows/ci.yml", 'node-version: "24"')
    require_text(".github/workflows/ci.yml", "scripts/verify_gate_k.py")
    require_text("README.md", "uv sync --locked")
    require_text("README.md", "alembic upgrade head")
    if not (ROOT / ".gitignore").is_file() or ".env" not in (ROOT / ".gitignore").read_text():
        raise RuntimeError(".env is not protected by .gitignore")


def verify_runtime() -> None:
    python = command_output("python", "--version")
    uv = command_output("uv", "--version")
    java = command_output("java", "-version")
    node = command_output("node", "--version")
    docker = command_output("docker", "--version")
    expected = (
        (python, r"Python 3\.12\.14", "Python 3.12.14"),
        (uv, r"uv 0\.12\.5(?:\s|$)", "uv 0.12.5"),
        (java, r'version "21(?:\.|\")', "Java 21"),
        (node, r"v24\.", "Node 24"),
        (docker, r"Docker version ", "Docker"),
    )
    for output, pattern, label in expected:
        if re.search(pattern, output) is None:
            raise RuntimeError(f"{label} runtime mismatch: {output}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded HarnessLab fresh-clone preflight")
    parser.add_argument(
        "--check-runtime",
        action="store_true",
        help="also require the documented host tool versions; never installs anything",
    )
    arguments = parser.parse_args()
    verify_repository_contract()
    if arguments.check_runtime:
        verify_runtime()
    print("FRESH_SETUP_CONTRACT=PASS")
    print("PYTHON=3.12.14 UV=0.12.5 POSTGRESQL=18 JAVA=21 NODE=24 DOCKER=REQUIRED")
    print("REAL_EVIDENCE_CONFIGURATION=CREDENTIAL_REFERENCES_ONLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
