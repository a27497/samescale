from __future__ import annotations

import argparse
import os
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
        "release/tier-a-verifier-robustness-v1.json",
        "release/tier-a-verifier-robustness-v2.json",
        "release/tier-a-verifier-robustness-v1-gap-reproduction.json",
        "release/model-chat-v3-keyless-plan.json",
        "release/model-chat-v3-canary.json",
        "release/model-chat-v3-continuation-policy.json",
        "release/core-real-evidence-plan.json",
        "release/core-real-smoke-plan.json",
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
    require_text(".github/workflows/full-ci.yml", "Java 21")
    require_text(".github/workflows/full-ci.yml", 'node-version: "24"')
    require_text(".github/workflows/full-ci.yml", "scripts/verify_gate_k.py")
    require_text(".github/workflows/full-ci.yml", "scripts/verify_tier_a_verifier_robustness_v2.py")
    require_text(".github/workflows/full-ci.yml", "scripts/freeze_model_chat_v3.py")
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


def verify_actions_reproduction() -> None:
    """Attest the clean checkout only after the isolated full Actions jobs succeed."""

    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("actual reproduction attestation is restricted to GitHub Actions")
    expected_sha = os.environ.get("GITHUB_SHA")
    if not expected_sha or re.fullmatch(r"[0-9a-f]{40}", expected_sha) is None:
        raise RuntimeError("GITHUB_SHA must be the exact 40-character checkout identity")
    actual_sha = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()
    if actual_sha != expected_sha:
        raise RuntimeError(
            f"Actions checkout mismatch: expected {expected_sha}, found {actual_sha}"
        )
    tracked_changes = subprocess.run(
        ("git", "status", "--porcelain", "--untracked-files=no"),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()
    if tracked_changes:
        raise RuntimeError("ordered gate execution mutated tracked checkout content")
    print(f"FRESH_SETUP_ACTIONS_SHA={actual_sha}")
    print("FRESH_SETUP_ACTUAL_REPRODUCTION=PASS")
    print("GATE_RECURSION=NONE")


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded HarnessLab fresh-clone preflight")
    parser.add_argument(
        "--check-runtime",
        action="store_true",
        help="also require the documented host tool versions; never installs anything",
    )
    parser.add_argument(
        "--actions-reproduction",
        action="store_true",
        help="attest the already-completed clean GitHub Actions Gates A-K checkout",
    )
    arguments = parser.parse_args()
    verify_repository_contract()
    if arguments.check_runtime:
        verify_runtime()
    if arguments.actions_reproduction:
        verify_actions_reproduction()
    print("FRESH_SETUP_PREFLIGHT_CONTRACT=PASS")
    if not arguments.actions_reproduction:
        print("FRESH_SETUP_ACTUAL_REPRODUCTION=NOT_RUN_USE_ACTIONS")
    print("PYTHON=3.12.14 UV=0.12.5 POSTGRESQL=18 JAVA=21 NODE=24 DOCKER=REQUIRED")
    print("REAL_EVIDENCE_CONFIGURATION=CREDENTIAL_REFERENCES_ONLY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
