"""Local-only mutation audit of saved SWE PASS deliveries; never runs an Agent or API."""

from __future__ import annotations

import argparse
import ast
import asyncio
import csv
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from harnesslab.local_execution.sandbox import PinnedVerifierSandbox
from harnesslab.registry.models import canonical_digest
from harnesslab.sandbox.models import IsolatedVerifierResult, VerifierLifecycleStage
from harnesslab.sandbox.runner import SandboxExecutionError
from harnesslab.tasks.models import VerifierReport
from harnesslab.tasks.package import TaskPackage, digest_tree

REPO = Path(__file__).resolve().parents[1]
REPORT = REPO / "docs/evidence/swe-full-20261014/report.json"
MUTATIONS = REPO / "evaluation/canary/swe-repair-regressions.json"
REPORT_SHA = "d8250bf05625ac0c605f87108f67c6027be788f8a6094cf48813b591c9aa428b"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read(path: Path) -> Any:
    return json.loads(path.read_bytes())


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        stream.write(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n")


def external(path: Path) -> Path:
    path = path.resolve()
    # Reject every checkout, including a different worktree, not only this REPO.
    for parent in (path, *path.parents):
        if (parent / ".git").exists():
            raise ValueError("artifact path must be outside every Git checkout")
    return path


def inventory(roots: list[Path]) -> dict[str, Any]:
    """All file bytes/modes/link text, including .git and original inventory files."""
    result: dict[str, Any] = {}
    for root in roots:
        paths = [root] if root.is_file() else sorted(root.rglob("*"))
        for path in paths:
            key = str(path)
            if path.is_symlink():
                result[key] = {"link": os.readlink(path)}
            elif path.is_file():
                result[key] = {
                    "sha256": sha(path.read_bytes()),
                    "mode": path.stat().st_mode & 0o777,
                }
    return result


def selected(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row
        for row in report["rows"]
        if row["group"] == "SWE-bench"
        and row["environment"] == "PASS"
        and row["verifier"] == "PASS"
    ]


def mutate(patch: str, base: str, rule: dict[str, str], scratch: Path) -> tuple[str, str]:
    """Apply only the target file section; preserve every other delivery byte verbatim."""
    name = rule["path"]
    if Path(name).is_absolute() or ".." in Path(name).parts or not name.endswith(".py"):
        raise ValueError("unsafe production path")
    if any(p in {"tests", "test", "verifier", ".git"} for p in Path(name).parts):
        raise ValueError("mutation must target production code")
    blocks = re.split(r"(?=^diff --git )", patch, flags=re.M)
    matches = [i for i, b in enumerate(blocks) if b.startswith(f"diff --git a/{name} b/{name}\n")]
    if len(matches) != 1:
        raise ValueError("one original production diff required")
    target = scratch / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(base)
    subprocess.run(
        ["git", "apply", "--whitespace=nowarn", "-"],
        input=blocks[matches[0]].encode(),
        cwd=scratch,
        capture_output=True,
        check=True,
    )
    correct = target.read_text()
    if correct.count(rule["before"]) != 1 or rule["before"] == rule["after"]:
        raise ValueError("mutation anchor must occur exactly once and change code")
    broken = correct.replace(rule["before"], rule["after"], 1)
    # Parse only; never import/execute subject code on the host.
    ast.parse(broken)
    delta = "".join(
        difflib.unified_diff(
            correct.splitlines(keepends=True),
            broken.splitlines(keepends=True),
            fromfile="a/" + name,
            tofile="b/" + name,
        )
    )
    replacement = "".join(
        difflib.unified_diff(
            base.splitlines(keepends=True),
            broken.splitlines(keepends=True),
            fromfile="a/" + name,
            tofile="b/" + name,
        )
    )
    blocks[matches[0]] = f"diff --git a/{name} b/{name}\n" + replacement if replacement else ""
    return "".join(blocks), delta


def complete_result(
    result: IsolatedVerifierResult, workspace: Path, expected_names: list[str]
) -> dict[str, Any]:
    report = VerifierReport.model_validate_json(result.run.stdout)
    manifest = result.run.manifest
    checks = report.checks
    expected = len(expected_names)
    if (
        not checks
        or len(checks) != expected
        or [c.name for c in checks] != expected_names
        or report.passed != all(c.passed for c in checks)
        or report.score != sum(c.passed for c in checks) / expected
        or manifest.exit_code != 0
        or manifest.timed_out
        or manifest.cancelled
        or manifest.stdout_truncated
        or manifest.stderr_truncated
        or not manifest.cleanup_verified
        or result.lifecycle is None
        or result.lifecycle.failure_subtype is not None
        or {s.stage for s in result.lifecycle.stages} != set(VerifierLifecycleStage)
        or any(s.status.value != "COMPLETED" for s in result.lifecycle.stages)
        or manifest.workspace_input_digest != digest_tree(workspace)
        or manifest.workspace_output_digest != manifest.workspace_input_digest
    ):
        raise ValueError("incomplete or inconsistent acceptance")
    return {
        "verdict": "PASS" if report.passed else "FAIL",
        "checks": len(checks),
        "passed_checks": sum(c.passed for c in checks),
        "check_results": [c.model_dump(mode="json") for c in checks],
        "report_sha256": sha(result.run.stdout.encode()),
        "manifest_digest": canonical_digest(manifest.model_dump(mode="json")),
        "lifecycle_digest": canonical_digest(result.lifecycle.model_dump(mode="json")),
    }


async def verify(
    package: TaskPackage, image: str, workspace: Path, out: Path, expected_names: list[str]
) -> dict[str, Any]:
    sandbox = PinnedVerifierSandbox(
        image_id=image,
        run_id="canary-" + uuid4().hex,
        runtime_root=out / "runtime",
        artifact_root=out / "artifacts",
    )
    try:
        result = await sandbox.run_hidden_verifier_workspace(package, workspace, timeout_seconds=30)
        write(out / "observation.json", result.model_dump(mode="json"))
        value = complete_result(result, workspace, expected_names)
    except (ValueError, OSError, SandboxExecutionError) as exc:
        # Failed execution never counts as a killed mutation or a surviving mutation.
        diagnostics = getattr(exc, "diagnostics", None)
        value = {
            "verdict": "INCONCLUSIVE",
            "error_class": type(exc).__name__,
            "lifecycle": diagnostics.model_dump(mode="json") if diagnostics else None,
        }
    write(out / "result.json", value)
    return value


def prepare(evidence: Path, output: Path) -> None:
    output = external(output)
    evidence = external(evidence)
    if evidence == output or evidence in output.parents or output in evidence.parents:
        raise ValueError("output must not overlap original evidence")
    if sha(REPORT.read_bytes()) != REPORT_SHA:
        raise ValueError("source report drift")
    rules = read(MUTATIONS)
    rows = selected(read(REPORT))
    if [r["task_id"] for r in rows] != [r["task_id"] for r in rules["mutations"]]:
        raise ValueError("mutation plan must cover all original PASS SWE in report order")
    frozen = [
        evidence / name
        for name in (
            "swe-full-20261014",
            "swe-external-pilot-20261014",
            "swe-external-verifiers-20261014-v8",
            "swe-full-20261014-evidence.tar.gz",
            "swe-external-pilot-20261014-evidence.tar.gz",
        )
    ]
    if any(not p.exists() for p in frozen):
        raise ValueError("original frozen roots/archives unavailable")
    before = inventory(frozen)
    output.mkdir(mode=0o700, parents=True)
    write(output / "original-inventory.json", before)
    # Only read task packages. Never import, register, or qualify into original TaskStore.
    candidates = [
        p.parent
        for root in frozen[:3]
        for p in root.rglob("task.yaml")
        if "sources" in p.relative_to(root).parts
    ]
    cases = []
    for row, rule in zip(rows, rules["mutations"], strict=True):
        identity = row["task_id"]
        # Relocate the original shared external-state prefix for transferred archives.
        parts = Path(row["evidence_path"]).parts
        offset = parts.index("samescale-eval") + 1
        source = evidence.joinpath(*parts[offset:])
        receipt = read(source / "acceptance.json")
        unsigned = {k: v for k, v in receipt.items() if k != "receipt_digest"}
        if (
            receipt["acceptance"] != "VERIFIED_PASS"
            or receipt["checks"] <= 0
            or receipt["checks"] != receipt["passed_checks"]
            or canonical_digest(unsigned) != receipt["receipt_digest"]
            or receipt["receipt_digest"] != row["receipt_digest"]
        ):
            raise ValueError("original PASS receipt binding failed")
        package_root = next(
            (p for p in candidates if digest_tree(p) == receipt["task_digest"]), None
        )
        if package_root is None:
            raise ValueError("exact original package unavailable: " + identity)
        package = TaskPackage.load(package_root)
        if package.verifier_digest != receipt["verifier_digest"]:
            raise ValueError("original verifier drift")
        delivery = source / "delivery-v2"
        if digest_tree(delivery) != receipt["workspace_digest"]:
            raise ValueError("original final delivery drift")
        case = output / "cases" / identity
        package_relative = Path("package") / package.definition.id / package.definition.version
        shutil.copytree(package_root, case / package_relative)
        if (
            TaskPackage.load(case / package_relative).definition.content_digest
            != receipt["task_digest"]
        ):
            raise ValueError("copied package differs")
        shutil.copytree(delivery, case / "control/workspace")
        with tarfile.open(source / "base.tar") as archive:
            stream = archive.extractfile(rule["path"])
            if stream is None:
                raise ValueError("production baseline unavailable")
            base = stream.read().decode()
        with tempfile.TemporaryDirectory(dir=output, prefix="mutation-") as temp:
            patch, delta = mutate((delivery / "solution.patch").read_text(), base, rule, Path(temp))
        shutil.copytree(delivery, case / "mutant/workspace")
        (case / "mutant/workspace/solution.patch").write_text(patch)
        (case / "mutation.patch").write_text(delta)
        spec = read(package_root / "verifier/acceptance.json")
        expected_names = [
            "required-" + sha(n.encode())[:32] for n in spec["fail_to_pass"] + spec["pass_to_pass"]
        ]
        if len(expected_names) != receipt["checks"]:
            raise ValueError("required check count differs from original receipt")
        item = {
            "task_id": identity,
            "package_path": str(package_relative),
            "rule": rule,
            "original_receipt_digest": receipt["receipt_digest"],
            "original_receipt_sha256": sha((source / "acceptance.json").read_bytes()),
            "task_digest": receipt["task_digest"],
            "verifier_digest": receipt["verifier_digest"],
            "image_id": receipt["image_id"],
            "expected_checks": receipt["checks"],
            "expected_names": expected_names,
            "control_workspace_digest": digest_tree(case / "control/workspace"),
            "mutant_workspace_digest": digest_tree(case / "mutant/workspace"),
            "mutation_sha256": sha(delta.encode()),
            "original_source": str(source),
        }
        if item["control_workspace_digest"] == item["mutant_workspace_digest"]:
            raise ValueError("no mutation")
        write(case / "binding.json", item)
        cases.append(item)
    plan = {
        "schema_version": 1,
        "source_report_sha256": REPORT_SHA,
        "mutation_plan_sha256": sha(MUTATIONS.read_bytes()),
        "rules": rules,
        "frozen_roots": [str(p) for p in frozen],
        "cases": cases,
    }
    write(output / "plan.json", plan)
    write(output / "plan-pin.json", {"sha256": sha((output / "plan.json").read_bytes())})
    if inventory(frozen) != before:
        raise ValueError("original evidence changed during preparation")
    print(f"PREPARED {len(cases)}; pilot first 5; no verifier executed", flush=True)


def load_plan(output: Path) -> dict[str, Any]:
    value: dict[str, Any] = read(output / "plan.json")
    if sha((output / "plan.json").read_bytes()) != read(output / "plan-pin.json")["sha256"]:
        raise ValueError("preregistered plan changed")
    if value["source_report_sha256"] != REPORT_SHA:
        raise ValueError("source report binding changed")
    return value


def classify(control: str, mutant: str) -> str:
    if control != "PASS" or mutant not in {"PASS", "FAIL"}:
        return "INCONCLUSIVE"
    return "DETECTED" if mutant == "FAIL" else "SURVIVED"


def project(output: Path) -> dict[str, Any]:
    plan = load_plan(output)
    rows = []
    for i, item in enumerate(plan["cases"]):
        case = output / "cases" / item["task_id"]
        results = [
            read(case / mode / "result.json")
            if (case / mode / "result.json").exists()
            else {"verdict": "NOT_RUN"}
            for mode in ("control", "mutant")
        ]
        control, mutant = results
        rows.append(
            {
                "task_id": item["task_id"],
                "stage": "pilot" if i < 5 else "expansion",
                "injection_type": plan["rules"]["family"],
                "rationale": item["rule"]["rationale"],
                "original": "PASS",
                "control": control["verdict"],
                "mutant": mutant["verdict"],
                "control_passed_checks": control.get("passed_checks"),
                "mutant_passed_checks": mutant.get("passed_checks"),
                "checks": item["expected_checks"],
                "outcome": classify(control["verdict"], mutant["verdict"]),
                "missed": mutant["verdict"] == "PASS"
                if control["verdict"] == "PASS" and mutant["verdict"] in {"PASS", "FAIL"}
                else None,
                "original_receipt_digest": item["original_receipt_digest"],
                "mutation_sha256": item["mutation_sha256"],
            }
        )
    return {
        "schema_version": 1,
        "plan_sha256": sha((output / "plan.json").read_bytes()),
        "source_report_sha256": REPORT_SHA,
        "rows": rows,
        "counts": {
            key: sum(r["outcome"] == key for r in rows)
            for key in ("DETECTED", "SURVIVED", "INCONCLUSIVE")
        },
    }


async def run(output: Path, stage: str) -> None:
    output = external(output)
    plan = load_plan(output)
    before = read(output / "original-inventory.json")
    roots = [Path(p) for p in plan["frozen_roots"]]
    if inventory(roots) != before:
        raise ValueError("original evidence drift before execution")
    if stage == "expansion":
        gate = read(output / "pilot.json")
        if not gate["gate_passed"] or gate["report"] != project(output):
            # Project will differ once expansion has run; this check intentionally forbids repeats.
            raise ValueError("completed, unchanged pilot required before expansion")
    items = plan["cases"][:5] if stage == "pilot" else plan["cases"][5:]
    # Reserve the complete stage before execution; interruption cannot silently rerun a case.
    write(
        output / (stage + "-started.json"),
        {"plan_sha256": sha((output / "plan.json").read_bytes())},
    )
    for item in items:
        case = output / "cases" / item["task_id"]
        package = TaskPackage.load(case / item["package_path"])
        if (
            package.definition.content_digest != item["task_digest"]
            or package.verifier_digest != item["verifier_digest"]
        ):
            raise ValueError("frozen package drift")
        for mode in ("control", "mutant"):
            workspace = case / mode / "workspace"
            if digest_tree(workspace) != item[mode + "_workspace_digest"]:
                raise ValueError("candidate drift")
            value = await verify(
                package, item["image_id"], workspace, case / mode, item["expected_names"]
            )
            print(item["task_id"], mode, value["verdict"], flush=True)
            if mode == "control" and value["verdict"] != "PASS":
                break
    unchanged = inventory(roots) == before
    report = project(output)
    gate_passed = unchanged and all(
        r["outcome"] in {"DETECTED", "SURVIVED"} for r in report["rows"][:5]
    )
    write(
        output / (stage + ".json"),
        {"gate_passed": gate_passed, "originals_unchanged": unchanged, "report": report},
    )
    if not unchanged or not gate_passed:
        raise ValueError("integrity/procedural gate failed; no automatic retry")
    if stage == "expansion":
        write(output / "report.json", report)
        with (output / "results.csv").open("x") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(report["rows"][0]))
            writer.writeheader()
            writer.writerows(report["rows"])
    print(
        json.dumps({"stage": stage, "gate_passed": gate_passed, "counts": report["counts"]}),
        flush=True,
    )


def replay(output: Path) -> None:
    output = external(output)
    plan = load_plan(output)
    if inventory([Path(p) for p in plan["frozen_roots"]]) != read(
        output / "original-inventory.json"
    ):
        raise ValueError("original evidence changed")
    for item in plan["cases"]:
        case = output / "cases" / item["task_id"]
        package = TaskPackage.load(case / item["package_path"])
        if package.definition.content_digest != item["task_digest"]:
            raise ValueError("package drift")
        if sha((case / "mutation.patch").read_bytes()) != item["mutation_sha256"]:
            raise ValueError("mutation drift")
        for mode in ("control", "mutant"):
            directory = case / mode
            if digest_tree(directory / "workspace") != item[mode + "_workspace_digest"]:
                raise ValueError("workspace drift")
            value = read(directory / "result.json")
            if value["verdict"] in {"PASS", "FAIL"}:
                observed = IsolatedVerifierResult.model_validate(
                    read(directory / "observation.json")
                )
                if (
                    complete_result(observed, directory / "workspace", item["expected_names"])
                    != value
                ):
                    raise ValueError("saved observation differs")
    if project(output) != read(output / "report.json"):
        raise ValueError("derived report differs")
    print("REPLAY PASS; original bytes/modes/links unchanged; no Docker/model execution")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "pilot", "expansion", "replay"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence-base", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        if args.evidence_base is None:
            parser.error("prepare requires --evidence-base")
        prepare(args.evidence_base, args.output)
    elif args.command == "replay":
        replay(args.output)
    else:
        asyncio.run(run(args.output, args.command))


if __name__ == "__main__":
    main()
