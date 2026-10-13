"""Require both exact-head main push CI runs; never trust a PR or an older green attempt."""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

REPOSITORY = "a27497/samescale"
API = f"https://api.github.com/repos/{REPOSITORY}"
REQUIRED = {
    "ci.yml": {"scope", "python-checks", "frontend", "gates"}
    | {f"core (full {i})" for i in range(4)},
    "offline-regression.yml": {"offline-regression"},
}
Json = dict[str, Any]
Fetcher = Callable[[str], Json]


class NotReady(RuntimeError):
    """No authority to deploy this commit; include no response bodies or credential details."""


def valid_sha(sha: str) -> bool:
    return re.fullmatch(r"[0-9a-f]{40}", sha) is not None


def fetch_json(path: str, token: str | None = None) -> Json:
    headers = {"User-Agent": "samescale-deploy", "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(API + path, headers=headers)
    with urllib.request.urlopen(request, timeout=25) as response:
        data = json.load(response)
    if not isinstance(data, dict):
        raise NotReady("Invalid GitHub response")
    return data


def require_ci(sha: str, fetch: Fetcher) -> list[int]:
    if not valid_sha(sha) or fetch("/git/ref/heads/main").get("object", {}).get("sha") != sha:
        raise NotReady("Requested commit is not the current main head")
    receipts = []
    query = urllib.parse.urlencode(
        {"branch": "main", "event": "push", "head_sha": sha, "per_page": 100}
    )
    for workflow, required_jobs in REQUIRED.items():
        runs = fetch(f"/actions/workflows/{workflow}/runs?{query}").get("workflow_runs", [])
        matching = [
            run
            for run in runs
            if run.get("head_sha") == sha
            and run.get("head_branch") == "main"
            and run.get("event") == "push"
            and run.get("head_repository", {}).get("full_name") == REPOSITORY
            and run.get("path") == f".github/workflows/{workflow}"
        ]
        if not matching:
            raise NotReady("Missing required main CI")
        latest = max(matching, key=lambda run: (run["id"], run.get("run_attempt", 1)))
        if latest.get("status") != "completed" or latest.get("conclusion") != "success":
            raise NotReady("Required CI is pending or unsuccessful")
        run_id = latest["id"]
        if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id < 1:
            raise NotReady("Invalid CI run identity")
        # Explicit attempt avoids accepting jobs from a previously green rerun.
        attempt = latest.get("run_attempt", 1)
        if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
            raise NotReady("Invalid CI attempt")
        jobs: list[Json] = []
        for page in range(1, 11):
            result = fetch(
                f"/actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100&page={page}"
            )
            jobs.extend(result.get("jobs", []))
            if len(jobs) >= result.get("total_count", sys.maxsize):
                break
        else:
            raise NotReady("Incomplete CI job collection")
        names = [job.get("name") for job in jobs]
        if (
            not required_jobs.issubset(names)
            or any(names.count(name) != 1 for name in required_jobs)
            or any(
                job.get("status") != "completed" or job.get("conclusion") != "success"
                for job in jobs
            )
        ):
            raise NotReady("Missing, skipped or unsuccessful CI jobs")
        receipts.append(run_id)
    # Close the query window; a newer main must not inherit these receipts.
    if fetch("/git/ref/heads/main").get("object", {}).get("sha") != sha:
        raise NotReady("Main changed during CI inspection")
    return receipts


def event_sha(event: Json) -> str:
    run = event.get("workflow_run", {})
    sha = run.get("head_sha", "")
    if (
        event.get("repository", {}).get("full_name") != REPOSITORY
        or run.get("head_repository", {}).get("full_name") != REPOSITORY
        or run.get("head_branch") != "main"
        or run.get("event") != "push"
        or run.get("conclusion") != "success"
        or not isinstance(sha, str)
        or not valid_sha(sha)
        or run.get("path") not in {f".github/workflows/{name}" for name in REQUIRED}
    ):
        raise NotReady("Not an eligible main CI completion")
    return sha


def main() -> int:
    try:
        sha = event_sha(json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text()))
        receipts = require_ci(sha, lambda path: fetch_json(path, os.environ.get("GH_TOKEN")))
    except NotReady as exc:
        print(f"Deployment deferred: {exc}")
        with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
            output.write("ready=false\n")
        return 0
    # Transport/permission/JSON errors fail the job; they never grant deploy authority.
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write(f"ready=true\nsha={sha}\n")
    print(f"CI_READY sha={sha} runs={','.join(str(run) for run in receipts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
