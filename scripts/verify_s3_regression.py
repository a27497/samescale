"""S3 offline contract; invoke through ci_s3.sh locally and in GitHub Actions."""

from __future__ import annotations

import argparse
import fcntl
import io
import json
import socket
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

from harnesslab.analyst.offline_replay import ReplayError, read_pinned, require, safe_path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence/s2-offline-replay-20260921"
ARCHIVE_DIGEST = "sha256:ee7748478fa7366d17454d1c5936a33466c580c2a3baf9ccdc5c302705345abd"
INPUTS_DIGEST = "sha256:d77d964fe60158da4e22ee7e60df0cfb54178a99c957298d861d977f925d0395"
# S2's independently recorded, byte-identical outputs. Never regenerate on CI failure.
GOLDEN = {
    "claude.json": "sha256:fee070ee5d18df386005e5a006fa6084c45504ba3c7c4a6345b24175f9b8fe1d",
    "codex.json": "sha256:e7fefdfb5cf17de2c8f06220f9c66aabe498e5e52175f2401796d1ea200c2cfe",
    "diagnosis.md": "sha256:cce662542d885d65de95771f1e3d3f75a0a5997bc162ed998a7c906c090f24d1",
    "offline-boundary.json": (
        "sha256:1e5b18de89bb1c586931174681538dcdb668a1f5453c36e3c6472070552dd097"
    ),
    "trace-diff.json": "sha256:968a1b8409a496dd1693e9b80413f940fc196937053675c35a761aed2af7bbef",
}
SUITES = ("tests/test_s2_offline_replay.py", "tests/test_s3_ci_regression.py")
REQUIRED_TESTS = (
    "test_real_runs_are_reconstructed_without_execution",
    "test_integrity_drift_fails_closed",
    "test_semantic_contradictions_fail_even_with_reanchored_inventory",
    "test_cli_offline_guard_rejects_network_and_processes",
    "test_golden_rejects_semantic_regressions",
    "test_parser_mutation_fails_closed",
    "test_schema_and_taxonomy_drift_fail_closed",
    "test_workflow_uses_offline_entry_without_execution_credentials",
)


def check_outputs(output: Path) -> None:
    require({p.name for p in output.iterdir()} == set(GOLDEN), "replay output inventory drift")
    for name, digest in GOLDEN.items():
        read_pinned(output / name, digest)


def extract_archive(archive: Path, destination: Path) -> None:
    data = read_pinned(archive, ARCHIVE_DIGEST)
    destination.mkdir()
    with zipfile.ZipFile(io.BytesIO(data)) as zipped:
        names = zipped.namelist()
        require(len(names) == len(set(names)), "duplicate archive member")
        for name in names:
            path = safe_path(destination, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(zipped.read(name))
    read_pinned(destination / "inputs.json", INPUTS_DIGEST)


def check_junit(path: Path) -> int:
    cases = ET.parse(path).getroot().findall(".//testcase")
    require(len(cases) >= 44, "missing critical tests / zero collection")
    require(all(not list(case) for case in cases), "failed, errored or skipped critical regression")
    names = {case.attrib["name"].split("[", 1)[0] for case in cases}
    require(set(REQUIRED_TESTS) <= names, "missing critical regression family")
    return len(cases)


def check_network() -> dict[str, Any]:
    # An unshare --net namespace starts with only a down loopback interface.
    interfaces = {name for _, name in socket.if_nameindex()}
    routes = Path("/proc/net/route").read_text().splitlines()
    require(
        interfaces == {"lo"}
        and not any(line.strip() and not line.startswith("Iface") for line in routes),
        "network isolation unavailable",
    )
    # Query this namespace's kernel flags; sysfs may still describe the host namespace.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        flags = fcntl.ioctl(probe.fileno(), 0x8913, struct.pack("256s", b"lo"))
    require(not (struct.unpack_from("H", flags, 16)[0] & 1), "loopback active")
    return {"interfaces": sorted(interfaces), "ipv4_routes": 0, "loopback": "down"}


def run(command: list[str], output: Path, name: str) -> None:
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    (output / f"{name}.txt").write_text(result.stdout + result.stderr)
    require(result.returncode == 0, f"{name} failed (exit {result.returncode})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    output = parser.parse_args().output.resolve()
    receipt: dict[str, Any] = {"schema_version": 1, "status": "FAIL_CLOSED"}
    try:
        require(output.is_dir() and not (output / "result.json").exists(), "new output required")
        receipt["network_namespace"] = check_network()
        # Check both the committed baseline and fresh outputs against external anchors.
        for name, digest in GOLDEN.items():
            read_pinned(EVIDENCE / name, digest)
        extract_archive(EVIDENCE / "representative-bundles.zip", output / "inputs")
        for attempt in ("replay-a", "replay-b"):
            run(
                [
                    sys.executable,
                    "scripts/replay_s2.py",
                    "--inputs",
                    str(output / "inputs/inputs.json"),
                    "--sha256",
                    INPUTS_DIGEST,
                    "--output",
                    str(output / attempt),
                ],
                output,
                attempt,
            )
            check_outputs(output / attempt)
        run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-p",
                "pytest_asyncio.plugin",
                "-p",
                "no:cacheprovider",
                "-q",
                *SUITES,
                f"--junitxml={output / 'pytest.xml'}",
            ],
            output,
            "pytest",
        )
        receipt.update(
            tests_passed=check_junit(output / "pytest.xml"),
            status="PASS",
            archive_digest=ARCHIVE_DIGEST,
            inputs_digest=INPUTS_DIGEST,
            identical_outputs=GOLDEN,
            replayed_runs=2,
            replay_passes=2,
            external_calls=0,
            provider_calls=0,
            model_calls=0,
            claude_calls=0,
            judge_calls=0,
            subject_executed=False,
            verifier_executed=False,
        )
    except (ReplayError, OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as exc:
        receipt["error"] = str(exc)
    (output / "result.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))
    return 0 if receipt["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
