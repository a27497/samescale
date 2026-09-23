"""Remove only empty D1 scratch directories after a stopped trial."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

BASE = Path("/home/dev/artifacts/samescale-d1-20260923")
TRIAL = BASE / "campaign-01"
OUTPUT = BASE / "post-stop-cleanup.json"
PRESERVED = ("receipt.json", "cleanup.json", "result.json", "sha256.json")


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    receipt = json.loads((TRIAL / "receipt.json").read_text())
    assert receipt["index"] == 1 and receipt["continue_allowed"] is False
    assert json.loads((TRIAL / "cleanup.json").read_text())["status"] == "FAIL"
    assert not OUTPUT.exists()
    before = {name: digest(TRIAL / name) for name in PRESERVED}
    runtime = TRIAL / "runtime"
    entries = sorted(runtime.rglob("*"), key=lambda path: len(path.parts), reverse=True)
    assert entries and all(path.is_dir() and not path.is_symlink() for path in entries)
    execution_id = receipt["execution_id"]
    assert len({path.relative_to(runtime).parts[0] for path in entries}) == 1
    assert all(path.relative_to(runtime).parts[0].startswith(execution_id) for path in entries)
    for path in entries:
        try:
            path.rmdir()
        except PermissionError:
            subprocess.run(["sudo", "-n", "rmdir", "--", str(path)], check=True, timeout=30)
    assert not any(runtime.iterdir())
    containers = subprocess.check_output(
        ["docker", "ps", "-a", "--format", "{{.Names}}"], text=True, timeout=30
    ).splitlines()
    networks = subprocess.check_output(
        ["docker", "network", "ls", "--format", "{{.Name}}"], text=True, timeout=30
    ).splitlines()
    assert not any(execution_id in name for name in containers + networks)
    after = {name: digest(TRIAL / name) for name in PRESERVED}
    assert before == after
    with OUTPUT.open("x") as stream:
        json.dump(
            {
                "status": "PASS",
                "original_trial": 1,
                "original_cleanup_status": "FAIL",
                "empty_scratch_directories_removed": len(entries),
                "files_deleted": 0,
                "containers_or_networks_remaining": 0,
                "preserved_sha256": after,
            },
            stream,
            indent=2,
        )
        stream.write("\n")
    print("D1_POST_STOP_EMPTY_SCRATCH_CLEANUP_PASS")


if __name__ == "__main__":
    main()
