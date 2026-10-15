"""Run a reviewed public assertion probe separately from the frozen primary Canary."""

from __future__ import annotations

import argparse
import asyncio
import shutil
from pathlib import Path

from harnesslab.tasks.package import TaskPackage
from scripts.swe_verifier_canary import external, load_plan, project, read, sha, verify, write


async def witness(output: Path, identity: str, probe: Path) -> None:
    output = external(output)
    item = next(c for c in load_plan(output)["cases"] if c["task_id"] == identity)
    row = next(r for r in project(output)["rows"] if r["task_id"] == identity)
    if row["outcome"] != "SURVIVED":
        raise ValueError("witness requires an observed primary survivor")
    body = probe.read_bytes()
    case = output / "cases" / identity
    destination = output / "witnesses" / identity
    destination.mkdir(parents=True)
    package_root = destination / item["package_path"]
    shutil.copytree(case / item["package_path"], package_root)
    (package_root / "verifier/probe.py").write_bytes(body)
    spec_path = package_root / "verifier/acceptance.json"
    spec = read(spec_path)
    # Keep original code reconstruction/hidden restoration and runner unchanged.
    # AssertionError is a failed behavioral check; other errors remain INCONCLUSIVE.
    code = (
        "import runpy\n"
        "try:\n"
        "    runpy.run_path('/verifier/probe.py', run_name='__main__')\n"
        "except AssertionError:\n"
        "    print('FAILED canary-witness')\n"
        "else:\n"
        "    print('PASSED canary-witness')\n"
    )
    spec.update(
        test_command=["python", "-c", code], fail_to_pass=["canary-witness"], pass_to_pass=[]
    )
    # Only this newly created secondary package is changed, never the primary package.
    spec_path.unlink()
    write(spec_path, spec)
    package = TaskPackage.load(package_root)
    expected = ["required-" + sha(b"canary-witness")[:32]]
    results = {}
    write(
        destination / "binding.json",
        {
            "primary_plan_sha256": sha((output / "plan.json").read_bytes()),
            "primary_mutation_sha256": item["mutation_sha256"],
            "probe_sha256": sha(body),
            "secondary_task_digest": package.definition.content_digest,
            "primary_verdict_unchanged": True,
        },
    )
    for mode in ("control", "mutant"):
        workspace = destination / mode / "workspace"
        shutil.copytree(case / mode / "workspace", workspace)
        results[mode] = await verify(
            package, item["image_id"], workspace, destination / mode, expected
        )
        print(identity, "secondary", mode, results[mode]["verdict"], flush=True)
    write(
        destination / "witness.json",
        {
            "task_id": identity,
            "probe_sha256": sha(body),
            "control": results["control"]["verdict"],
            "mutant": results["mutant"]["verdict"],
            "non_equivalence_confirmed": results["control"]["verdict"] == "PASS"
            and results["mutant"]["verdict"] == "FAIL",
            "scope": "SECONDARY_PUBLIC_BEHAVIOR_WITNESS_NOT_ORIGINAL_VERIFIER",
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--probe", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(witness(args.output, args.task_id, args.probe))


if __name__ == "__main__":
    main()
