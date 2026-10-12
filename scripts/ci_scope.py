"""Conservative CI routing; compare the whole branch to main, never just the last push."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SHARDS = 4


@dataclass(frozen=True)
class Scope:
    full: bool
    frontend: bool
    reason: str

    @property
    def matrix(self) -> dict[str, Any]:
        if self.full:
            return {
                "include": [{"index": i, "count": SHARDS, "mode": "full"} for i in range(SHARDS)]
            }
        return {"include": [{"index": 0, "count": 1, "mode": "boundary"}]}


def ordinary_doc(path: str) -> bool:
    if path in {"README.md", "CURRENT_MILESTONE.md", "PUBLIC_PRODUCT_CONTRACT.md"}:
        return True
    return (
        path.startswith("docs/")
        and PurePosixPath(path).suffix == ".md"
        and not path.startswith(("docs/evidence/", "docs/recruiter/"))
        and path != "docs/ANALYST.md"  # An input to the frozen badcase contracts.
    )


def classify(event: str, ref: str, paths: list[str] | None) -> Scope:
    if event != "push" or ref == "refs/heads/main" or not ref.startswith("refs/heads/"):
        return Scope(True, True, "PR/main/non-branch event requires the full suite")
    if not paths:
        return Scope(True, True, "Missing/empty comparison requires the full suite")
    frontend = False
    for path in paths:
        if path.startswith("frontend/"):
            frontend = True
        elif not ordinary_doc(path):
            return Scope(True, True, "Backend/shared/unknown input requires the full suite")
    return Scope(
        False, frontend, "Frontend/docs branch feedback; full suite remains mandatory on PR"
    )


def branch_paths(root: Path = ROOT) -> list[str] | None:
    try:
        base = (
            subprocess.check_output(
                ["git", "merge-base", "origin/main", "HEAD"], cwd=root, stderr=subprocess.DEVNULL
            )
            .decode()
            .strip()
        )
        raw = subprocess.check_output(
            ["git", "diff", "--name-only", "--no-renames", "-z", base, "HEAD"], cwd=root
        )
        return [part.decode("utf-8") for part in raw.split(b"\0") if part]
    except (subprocess.CalledProcessError, UnicodeError):
        return None  # Missing history/reference never enables a lightweight pass.


def check_results(needs: dict[str, Any], *, full: bool, frontend: bool) -> None:
    required = {"scope"}
    if full:
        required.update(("python-checks", "frontend", "backend"))
    elif frontend:
        required.update(("frontend", "backend"))  # Keep the existing DTO privacy boundary.
    for name in required:
        if needs.get(name, {}).get("result") != "success":
            raise ValueError(f"Required job did not succeed: {name}")


def main() -> int:
    if os.environ.get("CI_VERIFY_RESULTS") == "1":
        check_results(
            json.loads(os.environ["CI_NEEDS"]),
            full=os.environ["CI_FULL"] == "true",
            frontend=os.environ["CI_FRONTEND"] == "true",
        )
        print(
            "All checks required for this scope succeeded; partial feedback is not full acceptance"
        )
        return 0
    scope = classify(os.environ["GITHUB_EVENT_NAME"], os.environ["GITHUB_REF"], branch_paths())
    print(json.dumps({"full": scope.full, "frontend": scope.frontend, "reason": scope.reason}))
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write(f"full={str(scope.full).lower()}\nfrontend={str(scope.frontend).lower()}\n")
        output.write("matrix=" + json.dumps(scope.matrix, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
