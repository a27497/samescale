from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

PROTOCOL = "harnesslab-tier-b-subject-v1"


def run_worker(mode: str, workspace: Path) -> dict[str, Any]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "HOME", "TMP", "TEMP", "LANG"}
    }
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("subject_worker.py")), mode, str(workspace)],
        capture_output=True,
        text=True,
        timeout=35,
        env=environment,
        check=False,
    )
    if completed.returncode != 0:
        sys.stderr.write(completed.stderr)
        raise RuntimeError(f"verifier worker failed in {mode} mode")
    envelope = json.loads(completed.stdout)
    if (
        not isinstance(envelope, dict)
        or envelope.get("protocol") != PROTOCOL
        or not isinstance(envelope.get("report"), dict)
    ):
        raise RuntimeError("verifier worker protocol mismatch")
    return envelope["report"]


def main() -> int:
    candidate = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix="harnesslab-tier-b-health-") as temporary:
        health = Path(temporary) / "workspace"
        shutil.copytree(Path(__file__).with_name("health_workspace"), health)
        if not run_worker("health", health).get("passed"):
            raise RuntimeError("verifier self-health failed")
    print(json.dumps(run_worker("candidate", candidate), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
