"""Fail closed HTTP gate; requires saved fixture identities and no credentials to browse."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx


def run_gate(base_url: str, expected_demo_id: str) -> dict[str, Any]:
    names = (
        "public demo experiment exists",
        "run readable",
        "artifact exists",
        "SHA256 correct",
        "verifier verdict readable",
        "Diagnosis opens",
        "Regression opens",
        "provenance explainable",
        "no broken reference",
        "no HTTP 409/404/500",
        "fixture/offline/historical/real distinguished",
        "no browsing credential needed",
    )
    checks: list[dict[str, Any]] = [
        {"check": name, "pass": False, "state": "NOT_VERIFIED"} for name in names
    ]
    error: dict[str, str] | None = None
    responses: list[dict[str, Any]] = []
    with httpx.Client(
        base_url=base_url.rstrip("/"), timeout=30, follow_redirects=True, trust_env=False
    ) as client:

        def fetch(path: str, payload: dict[str, Any] | None = None) -> httpx.Response:
            response = client.get(path) if payload is None else client.post(path, json=payload)
            responses.append({"path": path, "status": response.status_code})
            response.raise_for_status()
            return response

        def check(name: str, value: bool) -> None:
            index = names.index(name)
            checks[index] = {
                "check": name,
                "pass": bool(value),
                "state": "PASS" if value else "FAIL",
            }

        try:
            demo = fetch("/api/workbench/public-demo").json()
            check(
                "public demo experiment exists",
                demo["demo_id"] == expected_demo_id and demo["public_demo_ready"] is True,
            )
            baseline = demo["baseline_id"]
            candidate = demo["candidate_id"]
            experiment = fetch(f"/api/workbench/experiments/{baseline}").json()
            fetch(f"/api/workbench/experiments/{candidate}")
            runs = fetch(f"/api/workbench/experiments/{baseline}/runs?limit=100").json()["items"]
            run = fetch(f"/api/workbench/runs/{demo['failed_run_id']}").json()
            check(
                "run readable",
                run["experiment_id"] == baseline and run["run_id"] in {r["run_id"] for r in runs},
            )
            artifact = fetch(f"/api/workbench/runs/{run['run_id']}/public-artifact?download=true")
            check("artifact exists", bool(artifact.content))
            digest = "sha256:" + hashlib.sha256(artifact.content).hexdigest()
            check(
                "SHA256 correct",
                digest == artifact.headers.get("X-Evidence-SHA256")
                and bool(demo["manifest_digest"]),
            )
            check(
                "verifier verdict readable",
                run["verifier_passed"] is False and artifact.json()["passed"] is False,
            )
            diagnosis = fetch(f"/api/workbench/experiments/{baseline}/diagnosis").json()
            check("Diagnosis opens", diagnosis["experiment_id"] == baseline)
            comparison = fetch(
                "/api/workbench/regression/compare",
                {
                    "baseline_experiment_id": baseline,
                    "candidate_experiment_id": candidate,
                    "intent": "GENERAL",
                },
            ).json()
            check(
                "Regression opens",
                comparison["baseline_experiment_id"] == baseline
                and comparison["candidate_experiment_id"] == candidate,
            )
            check(
                "provenance explainable",
                demo["provenance"]
                == experiment["provenance"]
                == run["provenance"]
                == "FIXTURE_OFFLINE"
                and "no real Provider/model execution" in demo["limitation"],
            )
            trace = fetch(f"/api/workbench/runs/{run['run_id']}/trace").json()
            check(
                "no broken reference",
                trace["run_id"] == run["run_id"] and trace["status"] == "REPORTED",
            )
            for path in (
                "/demo",
                f"/experiments/{baseline}?tab=runs",
                f"/runs/{run['run_id']}",
                f"/diagnosis?experiment={baseline}",
                f"/regression?baseline={baseline}&candidate={candidate}",
            ):
                fetch(path)
            check("no HTTP 409/404/500", all(r["status"] == 200 for r in responses))
            check(
                "fixture/offline/historical/real distinguished",
                comparison["baseline_provenance"]
                == comparison["candidate_provenance"]
                == "FIXTURE_OFFLINE"
                and all(value.startswith(expected_demo_id + "-") for value in (baseline, candidate))
                and not set((baseline, candidate)) & set(demo["historical_integrity_failures"]),
            )
            check(
                "no browsing credential needed",
                "Authorization" not in client.headers and not client.cookies,
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            error = {"error_type": type(exc).__name__, "message": str(exc)[:300]}
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "base_url": base_url,
        "expected_demo_id": expected_demo_id,
        "PUBLIC_DEMO_READY": len(checks) == 12 and all(c["pass"] for c in checks),
        "checks": checks,
        "responses": responses,
        "error": error,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--expected-demo-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = run_gate(args.base_url, args.expected_demo_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {"PUBLIC_DEMO_READY": report["PUBLIC_DEMO_READY"], "checks": report["checks"]}, indent=2
        )
    )
    raise SystemExit(0 if report["PUBLIC_DEMO_READY"] else 1)
