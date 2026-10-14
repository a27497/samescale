"""Frozen mixed-set selection and keyless Docker admission; real dispatch uses the product gate."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import urllib.request
from pathlib import Path
from typing import Any
from uuid import uuid4

from harnesslab.api.workbench_errors import WorkbenchAPIError
from harnesslab.local_execution.subscription import deny_real_execution, real_execution_readiness
from scripts.coding_agent_eval import (
    check_inventory,
    digest,
    docker,
    freeze,
    load,
    run_capture,
    save,
)

REPO = Path(__file__).resolve().parents[1]
SPEC = REPO / "evaluation" / "coding-agent"
Json = dict[str, Any]


def selection(rows: list[Json], config: Json) -> tuple[list[Json], list[str]]:
    if len({row["instance_id"] for row in rows}) != len(rows):
        raise ValueError("duplicate SWE instance identities")

    def rank(row: Json) -> str:
        return digest(f"{config['selection_seed']}:{row['instance_id']}".encode())

    selected = []
    for repo in config["repositories"]:
        eligible = [
            row
            for row in rows
            if row["repo"] == repo
            and row["base_commit"]
            and row["patch"]
            and row["test_patch"]
            and row["problem_statement"]
            and json.loads(row["FAIL_TO_PASS"])
        ]
        if len(eligible) < config["per_repository"]:
            raise ValueError("insufficient eligible tasks; no silent replacement")
        selected.extend(sorted(eligible, key=rank)[: config["per_repository"]])
    selected.sort(key=rank)
    pilot: list[str] = []
    seen = set()
    for row in selected:
        if row["repo"] not in seen and len(pilot) < config["pilot_count"]:
            seen.add(row["repo"])
            pilot.append(row["instance_id"])
    if len(selected) != config["swe_count"] or len(pilot) != 3:
        raise ValueError("wrong selection cardinality")
    return selected, pilot


def gate() -> Json:
    try:
        deny_real_execution()
    except WorkbenchAPIError as exc:
        return {
            "status": "BLOCKED",
            "code": exc.code,
            "http_status": exc.status_code,
            "readiness": real_execution_readiness(),
            "model_calls": 0,
            "credential_access": "NONE",
            "live_gate_changed": False,
        }
    raise RuntimeError("unexpected real gate behavior; no alternate dispatch is implemented")


def prepare(root: Path, config: Json, upstream_python: Path, retained: Path) -> None:
    if root.is_relative_to(REPO) or (root / "selection.json").exists():
        raise ValueError("campaign selection must be new and outside Git")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    inputs = root / "inputs"
    inputs.mkdir(exist_ok=True)
    parquet = inputs / "verified.parquet"
    if not parquet.exists():
        url = (
            f"https://huggingface.co/datasets/{config['dataset']}/resolve/"
            f"{config['dataset_revision']}/data/test-00000-of-00001.parquet"
        )
        parquet.write_bytes(urllib.request.urlopen(url, timeout=60).read())
    if digest(parquet.read_bytes()) != config["dataset_parquet_sha256"]:
        raise ValueError("dataset revision/hash mismatch")
    json_path = inputs / "verified.json"
    if not json_path.exists():
        program = (
            "import json,sys,pyarrow.parquet as p; "
            "print(json.dumps(p.read_table(sys.argv[1]).to_pylist(),indent=2))"
        )
        value = subprocess.check_output([str(upstream_python), "-c", program, str(parquet)])
        json_path.write_bytes(value)
    if digest(json_path.read_bytes()) != config["dataset_json_sha256"]:
        raise ValueError("decoded dataset differs from frozen input")
    rows, pilot = selection(json.loads(json_path.read_text()), config)
    if [r["instance_id"] for r in rows] != [
        r["instance_id"] for r in config["tasks"]
    ] or pilot != config["pilot_task_ids"]:
        raise ValueError("selection differs from published config")
    if digest(retained.read_bytes()) != config["retained_humaneval_summary_sha256"]:
        raise ValueError("retained HumanEval summary changed")
    previous = load(retained)
    if [r["task_id"] for r in previous["rows"]] != config["humaneval_task_ids"][:3]:
        raise ValueError("control identities mismatch")
    save(root / "config.json", config)
    save(
        root / "selection.json",
        {
            "swe_ids": [r["instance_id"] for r in rows],
            "pilot_ids": pilot,
            "humaneval_ids": config["humaneval_task_ids"],
        },
    )
    save(root / "retained-humaneval.json", previous)
    hidden = root / "hidden"
    hidden.mkdir()
    for row in rows:
        save(hidden / (row["instance_id"] + ".json"), row)
    save(root / "gate.json", gate())
    save(
        root / "input-inventory.json",
        {
            str(p.relative_to(root)): digest(p.read_bytes())
            for p in sorted(root.rglob("*"))
            if p.is_file() and not p.is_relative_to(root / "tooling")
        },
    )


def check_inputs(root: Path) -> None:
    for relative, expected in load(root / "input-inventory.json").items():
        if digest((root / relative).read_bytes()) != expected:
            raise ValueError(f"frozen input changed: {relative}")


def control_success(base: Json, gold: Json, instance_id: str) -> bool:
    return bool(
        base["found"]
        and gold["found"]
        and base["parsed_tests"] > 0
        and gold["parsed_tests"] > 0
        and base["expected_f2p"] > 0
        and not base["missing_required_tests"]
        and not gold["missing_required_tests"]
        and base["all_f2p_fail"]
        and base["all_p2p_pass"]
        and gold["all_f2p_pass"]
        and gold["all_p2p_pass"]
        and gold["report"][instance_id]["resolved"]
    )


def bridge(python: Path, *args: str) -> Json:
    result = subprocess.run(
        [str(python), str(SPEC / "swe_bridge.py"), *args],
        capture_output=True,
        check=True,
        timeout=60,
    )
    return load_json_bytes(result.stdout)


def load_json_bytes(data: bytes) -> Json:
    result = json.loads(data)
    if not isinstance(result, dict):
        raise ValueError("upstream report must be an object")
    return result


def merged_shell_command(command: str) -> str:
    """Merge at the trusted command, retaining ordering between markers and test output."""
    return command + " 2>&1"


def preflight(
    root: Path,
    upstream_python: Path,
    label: str = "preflight",
    instance_id_filter: str | None = None,
) -> None:
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,60}", label):
        raise ValueError("unsafe preflight receipt label")
    check_inputs(root)
    config = load(root / "config.json")
    if instance_id_filter is not None and instance_id_filter not in config["pilot_task_ids"]:
        raise ValueError("a correction may only recheck an already-fixed pilot identity")
    results = []
    for task in config["tasks"]:
        instance_id = task["instance_id"]
        if instance_id not in config["pilot_task_ids"]:
            continue
        if instance_id_filter is not None and instance_id != instance_id_filter:
            continue
        case = root / label / instance_id
        case.mkdir(parents=True)  # Never overwrite a first-attempt environment result.
        result: Json = {
            "instance_id": instance_id,
            "environment": "FAIL",
            "self_report": "NOT_RUN",
            "independent_agent_acceptance": "NOT_RUN",
            "agent_seconds": None,
            "agent_usage": None,
            "agent_cost_usd": None,
            "model_calls": 0,
            "failure_type": "ENVIRONMENT_FAILURE",
        }
        try:
            pull = run_capture(
                ["docker", "pull", task["image"]],
                case / "pull",
                timeout=config["pull_timeout_seconds"],
            )
            save(case / "pull-process.json", pull)
            if pull["exit_code"] != 0 or pull["timed_out"]:
                raise RuntimeError("IMAGE_PULL_FAILED")
            image = (
                docker("image", "inspect", task["image"], "--format", "{{.Id}}")
                .stdout.decode()
                .strip()
            )
            save(case / "image.json", {"reference": task["image"], "image_id": image})
            row_path = root / "hidden" / (instance_id + ".json")
            row = load(row_path)
            spec = bridge(upstream_python, "spec", str(row_path))
            (case / "eval.sh").write_text(spec["eval_script"])
            (case / "gold.patch").write_text(row["patch"])
            controls = {}
            for variant in ("baseline", "gold"):
                name = "samescale-swe-control-" + uuid4().hex
                script = f"cd /testbed && git reset --hard {task['base_commit']} && "
                if variant == "gold":
                    script += "git apply /evaluation/gold.patch && "
                # Upstream xtrace emits start/end markers to stderr. Merge at the process,
                # preserving actual order for its official parser; never synthesize markers.
                script += merged_shell_command("bash /evaluation/eval.sh")
                command = [
                    "create",
                    "--name",
                    name,
                    "--network",
                    "none",
                    "--cap-drop",
                    "ALL",
                    "--security-opt",
                    "no-new-privileges=true",
                    "--memory",
                    "4g",
                    "--cpus",
                    "2",
                    "--pids-limit",
                    "512",
                    "--env",
                    "PIP_NO_INDEX=1",
                    "--env",
                    "PYTEST_ADDOPTS=-rA --color=no",
                    "--mount",
                    f"type=bind,src={case},dst=/evaluation,readonly",
                    image,
                    "/bin/bash",
                    "-c",
                    script,
                ]
                docker(*command)
                try:
                    save(
                        case / f"{variant}-container.json",
                        json.loads(docker("inspect", name).stdout)[0],
                    )
                    status = run_capture(
                        ["docker", "start", "--attach", name],
                        case / variant,
                        timeout=config["environment_control_timeout_seconds"],
                    )
                    save(case / f"{variant}-process.json", status)
                    if status["timed_out"]:
                        raise RuntimeError("CONTROL_TIMEOUT")
                    grade = bridge(
                        upstream_python,
                        "grade",
                        str(row_path),
                        str(case / f"{variant}.stdout"),
                        variant,
                    )
                    save(case / f"{variant}-grade.json", grade)
                    controls[variant] = grade
                finally:
                    docker("rm", "--force", name)
            if control_success(controls["baseline"], controls["gold"], instance_id):
                result["environment"] = "PASS"
                result["failure_type"] = "NONE"
            else:
                result["reason"] = "BASELINE_OR_GOLD_CONTROL_FAILED"
        except (subprocess.SubprocessError, OSError, ValueError, RuntimeError) as exc:
            if isinstance(exc, subprocess.CalledProcessError):
                (case / "upstream-error.stdout").write_bytes(exc.stdout or b"")
                (case / "upstream-error.stderr").write_bytes(exc.stderr or b"")
            result["reason"] = type(exc).__name__ + ":" + str(exc)[:200]
        save(case / "result.json", result)
        freeze(case)
        results.append(result)
        print(json.dumps(result), flush=True)
    failed = sum(r["environment"] != "PASS" for r in results)
    save(
        root / f"{label}-summary.json",
        {
            "planned_pilot_tasks": 3,
            "environment_attempts": len(results),
            "first_attempt_environment_failures": failed,
            "first_attempt_environment_failure_rate": failed / len(results),
            "swe_agent_attempts": 0,
            "swe_agent_results": "NOT_RUN_REAL_EXECUTION_BLOCKED",
            "swe_self_report_pass_rate": None,
            "swe_independent_pass_rate": None,
            "swe_gap_percentage_points": None,
            "mixed_full_cost_estimate_usd": None,
            "mixed_full_token_estimate": None,
            "model_calls": 0,
            "rows": results,
            "gate": gate(),
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("prepare", "preflight", "replay", "gate", "pilot", "full")
    )
    parser.add_argument("--root", type=Path)
    parser.add_argument("--upstream-python", type=Path)
    parser.add_argument("--retained-humaneval-summary", type=Path)
    parser.add_argument("--preflight-label", default="preflight")
    parser.add_argument("--instance-id")
    args = parser.parse_args()
    if args.command in {"pilot", "full"}:
        print(json.dumps(gate(), indent=2))
        raise SystemExit(3)
    if args.command == "gate":
        print(json.dumps(gate(), indent=2))
        return
    if args.command == "replay":
        if not args.root:
            parser.error("offline replay requires root, no tooling or credential")
        print(json.dumps(replay(args.root.resolve(), args.preflight_label), indent=2))
        return
    if not args.root or not args.upstream_python:
        parser.error("keyless preparation requires root and isolated upstream Python")
    if args.command == "prepare":
        if not args.retained_humaneval_summary:
            parser.error("prepare requires original frozen HumanEval summary")
        prepare(
            args.root.resolve(),
            load(SPEC / "mixed-config.json"),
            args.upstream_python.absolute(),
            args.retained_humaneval_summary.resolve(),
        )
    else:
        # Resolving a venv interpreter symlink bypasses its pyvenv.cfg and installed tooling.
        preflight(
            args.root.resolve(),
            args.upstream_python.absolute(),
            args.preflight_label,
            args.instance_id,
        )


def replay(root: Path, label: str) -> Json:
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,60}", label):
        raise ValueError("unsafe replay label")
    check_inputs(root)
    config = load(root / "config.json")
    summary = load(root / f"{label}-summary.json")
    rows = []
    for task in config["tasks"]:
        if task["instance_id"] not in config["pilot_task_ids"]:
            continue
        case = root / label / task["instance_id"]
        if not case.exists():
            continue
        check_inventory(case)
        result = load(case / "result.json")
        qualified = False
        if (case / "baseline-grade.json").exists() and (case / "gold-grade.json").exists():
            qualified = control_success(
                load(case / "baseline-grade.json"),
                load(case / "gold-grade.json"),
                task["instance_id"],
            )
        if (
            result["environment"] != ("PASS" if qualified else "FAIL")
            or result["self_report"] != "NOT_RUN"
            or result["model_calls"] != 0
        ):
            raise ValueError("saved result disagrees with keyless control evidence")
        rows.append(result)
    failed = sum(row["environment"] == "FAIL" for row in rows)
    if (
        summary["rows"] != rows
        or summary["first_attempt_environment_failures"] != failed
        or summary["first_attempt_environment_failure_rate"] != failed / len(rows)
    ):
        raise ValueError("saved summary disagrees with frozen controls")
    return summary


if __name__ == "__main__":
    main()
