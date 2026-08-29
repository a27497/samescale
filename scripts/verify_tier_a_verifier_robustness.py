from __future__ import annotations

import asyncio
import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from harnesslab.experiment.methodology import load_evaluation_methodology
from harnesslab.sandbox.models import SandboxStatus, VerifierFailureSubtype
from harnesslab.sandbox.runner import DockerSandbox, SandboxExecutionError
from harnesslab.tasks.models import OutcomeCategory, VerifierExecutionResult
from harnesslab.tasks.package import TaskPackage
from harnesslab.tasks.verifier import execute_verifier

ROOT = Path(__file__).resolve().parents[1]
METHODOLOGY = ROOT / "release/evaluation-methodology-v2.json"
HISTORICAL_CORPUS = ROOT / "release/core-corpus.json"
ROBUSTNESS_CORPUS = ROOT / "release/tier-a-verifier-robustness-v1.json"
QUALIFICATION = "TIER_A_VERIFIER_ROBUSTNESS_V1"
REPEATS = 5

QUOTA_DEFECT = """class LRUCache:
    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self._values: dict[str, object] = {}

    def get(self, key: str) -> object | None:
        if key not in self._values:
            return None
        value = self._values.pop(key)
        self._values[key] = value
        return value

    def put(self, key: str, value: object) -> None:
        if key in self._values:
            self._values.pop(key)
        elif len(self._values) >= self.capacity:
            self._values.popitem(last=False)
        self._values[key] = value

    def keys(self) -> list[str]:
        return list(self._values)
"""


def _load_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RuntimeError(f"{path.name} is not an object")
    return raw


def _assert_subject_result(result: VerifierExecutionResult, *, passed: bool, label: str) -> None:
    if (
        result.category is not OutcomeCategory.SUBJECT_RESULT
        or result.exit_code != 0
        or result.passed is not passed
    ):
        raise RuntimeError(
            f"{label}: expected subject_result passed={passed} exit=0, got "
            f"category={result.category.value} passed={result.passed} exit={result.exit_code}"
        )


def _primary_subject_path(package: TaskPackage, workspace: Path) -> Path:
    oracle_files = sorted(path for path in package.oracle_path.rglob("*") if path.is_file())
    if len(oracle_files) != 1:
        raise RuntimeError(f"{package.definition.id}: expected one primary oracle file")
    return workspace / oracle_files[0].relative_to(package.oracle_path)


def _inject_load_failure(package: TaskPackage, workspace: Path) -> None:
    language = package.definition.metadata["language"]
    target = _primary_subject_path(package, workspace)
    invalid = {
        "python": "def declared_subject_contract(:\n",
        "java": "this is not valid Java source\n",
        "typescript": "export const deliberatelyInvalid = ;\n",
    }[language]
    target.write_text(invalid, encoding="utf-8")


def _inject_runtime_failure(package: TaskPackage, workspace: Path) -> None:
    for oracle_source in sorted(path for path in package.oracle_path.rglob("*") if path.is_file()):
        target = workspace / oracle_source.relative_to(package.oracle_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(oracle_source, target)
    language = package.definition.metadata["language"]
    target = _primary_subject_path(package, workspace)
    source_text = target.read_text(encoding="utf-8")
    if language == "python":
        target.write_text(
            'raise RuntimeError("deliberate subject runtime failure")\n' + source_text,
            encoding="utf-8",
        )
    elif language == "typescript":
        target.write_text(
            'throw new Error("deliberate subject runtime failure");\n' + source_text,
            encoding="utf-8",
        )
    elif language == "java":
        match = re.search(r"\bclass\s+[A-Za-z_$][\w$]*[^\{]*\{", source_text)
        if match is None:
            raise RuntimeError(f"{package.definition.id}: Java class declaration not found")
        injection = (
            "\n    static { if (System.nanoTime() != Long.MIN_VALUE) "
            'throw new RuntimeException("deliberate subject runtime failure"); }\n'
        )
        target.write_text(
            source_text[: match.end()] + injection + source_text[match.end() :],
            encoding="utf-8",
        )
    else:
        raise RuntimeError(f"{package.definition.id}: unsupported language {language}")


def _run_materialized(package: TaskPackage, mode: str) -> VerifierExecutionResult:
    materialized = package.materialize()
    try:
        if mode == "oracle":
            package.apply_oracle(materialized)
        elif mode == "load-failure":
            _inject_load_failure(package, materialized.workspace)
        elif mode == "runtime-failure":
            _inject_runtime_failure(package, materialized.workspace)
        elif mode != "baseline":
            raise RuntimeError(f"unknown qualification mode: {mode}")
        return execute_verifier(package, materialized)
    finally:
        materialized.cleanup()


def _verify_negative_control(package: TaskPackage) -> None:
    with tempfile.TemporaryDirectory(prefix="harnesslab-verifier-negative-") as temporary:
        task_path = Path(temporary) / package.definition.id / package.definition.version
        task_path.parent.mkdir(parents=True)
        shutil.copytree(package.root, task_path)
        (task_path / "verifier/subject_probe.py").write_text(
            'def main() -> int:\n    raise RuntimeError("deliberate verifier-owned failure")\n',
            encoding="utf-8",
        )
        broken = TaskPackage.load(task_path)
        materialized = broken.materialize()
        try:
            result = execute_verifier(broken, materialized)
        finally:
            materialized.cleanup()
    if (
        result.category is not OutcomeCategory.VERIFIER_ERROR
        or result.passed
        or result.exit_code in {None, 0}
    ):
        raise RuntimeError(
            "negative control did not preserve verifier-owned nonzero/infra semantics"
        )


def _verify_quota_defect(package: TaskPackage) -> None:
    materialized = package.materialize()
    try:
        (materialized.workspace / "quota.py").write_text(QUOTA_DEFECT, encoding="utf-8")
        result = execute_verifier(package, materialized)
    finally:
        materialized.cleanup()
    _assert_subject_result(result, passed=False, label="core-python-quota-known-defect")
    details = {check.detail for check in result.checks}
    if "SUBJECT_EXCEPTION_TypeError" not in details:
        raise RuntimeError("core-python-quota known TypeError was not typed as subject failure")


async def _verify_isolated_boundaries(quota: TaskPackage, negative_control: TaskPackage) -> None:
    with tempfile.TemporaryDirectory(prefix="harnesslab-robustness-sandbox-") as temporary:
        root = Path(temporary)
        runner = DockerSandbox(
            runtime_root=root / "runtime",
            artifact_root=root / "artifacts",
        )
        for repeat in range(REPEATS):
            materialized = quota.materialize(root / f"quota-workspace-{repeat + 1}")
            try:
                (materialized.workspace / "quota.py").write_text(QUOTA_DEFECT, encoding="utf-8")
                result = await runner.run_hidden_verifier_workspace(
                    quota,
                    materialized.workspace,
                    timeout_seconds=20,
                    run_id=f"tier-a-quota-replay-{repeat + 1}",
                )
            finally:
                materialized.cleanup()
            if (
                result.run.manifest.status is not SandboxStatus.SUCCEEDED
                or result.run.manifest.exit_code != 0
                or result.passed
                or result.score != 0
                or result.lifecycle is None
                or result.lifecycle.failure_subtype is not None
            ):
                raise RuntimeError(
                    "core-python-quota isolated replay did not produce capability failure"
                )

        broken_path = root / negative_control.definition.id / negative_control.definition.version
        broken_path.parent.mkdir(parents=True)
        shutil.copytree(negative_control.root, broken_path)
        (broken_path / "verifier/subject_probe.py").write_text(
            'def main() -> int:\n    raise RuntimeError("deliberate verifier-owned failure")\n',
            encoding="utf-8",
        )
        broken = TaskPackage.load(broken_path)
        materialized = broken.materialize(root / "negative-workspace")
        try:
            try:
                await runner.run_hidden_verifier_workspace(
                    broken,
                    materialized.workspace,
                    timeout_seconds=20,
                    run_id="tier-a-verifier-self-failure",
                )
            except SandboxExecutionError as exc:
                if (
                    exc.diagnostics is None
                    or exc.diagnostics.failure_subtype
                    is not VerifierFailureSubtype.VERIFIER_PROCESS_NONZERO
                ):
                    raise RuntimeError(
                        "isolated negative control did not classify verifier nonzero as infra"
                    ) from exc
            else:
                raise RuntimeError("isolated negative control unexpectedly returned a report")
        finally:
            materialized.cleanup()


def main() -> int:
    methodology = load_evaluation_methodology(METHODOLOGY)
    tier_a = next(
        item for item in methodology.task_tiers if item.tier.value == "TIER_A_MICRO_CONTRACT"
    )
    historical = _load_json(HISTORICAL_CORPUS)
    robustness = _load_json(ROBUSTNESS_CORPUS)
    if robustness.get("qualification") != QUALIFICATION:
        raise RuntimeError("robustness corpus qualification identity mismatch")
    old_items = {item["task_id"]: item for item in historical["tasks"]}
    new_items = {item["task_id"]: item for item in robustness["tasks"]}
    authoritative_ids = tuple(tier_a.current_task_ids)
    if set(old_items) != set(authoritative_ids) or set(new_items) != set(authoritative_ids):
        raise RuntimeError("Tier-A corpus does not match the authoritative methodology")

    packages: dict[str, TaskPackage] = {}
    for task_id in authoritative_ids:
        old = TaskPackage.load(ROOT / old_items[task_id]["package_path"])
        new = TaskPackage.load(ROOT / new_items[task_id]["package_path"])
        if old.definition.version != "1.0.0" or new.definition.version != "1.0.1":
            raise RuntimeError(f"{task_id}: version map is not 1.0.0 -> 1.0.1")
        if (
            old.definition.content_digest != old_items[task_id]["task_digest"]
            or old.verifier_digest != old_items[task_id]["verifier_identity"]
        ):
            raise RuntimeError(f"{task_id}: historical 1.0.0 bytes changed")
        if (
            new.definition.content_digest != new_items[task_id]["task_digest"]
            or new.verifier_digest != new_items[task_id]["verifier_identity"]
        ):
            raise RuntimeError(f"{task_id}: robustness manifest identity drifted")
        packages[task_id] = new

    robustness_tests = 0
    for task_id in authoritative_ids:
        package = packages[task_id]
        for repeat in range(REPEATS):
            for mode, expected_passed in (
                ("oracle", True),
                ("baseline", False),
                ("load-failure", False),
                ("runtime-failure", False),
            ):
                result = _run_materialized(package, mode)
                _assert_subject_result(
                    result,
                    passed=expected_passed,
                    label=f"{task_id}:{mode}:{repeat + 1}",
                )
                robustness_tests += 1

    quota = packages["core-python-quota"]
    for _ in range(REPEATS):
        _verify_quota_defect(quota)
        robustness_tests += 1

    control = packages["micro-python-clamp"]
    for _ in range(REPEATS):
        _verify_negative_control(control)
        robustness_tests += 1

    asyncio.run(_verify_isolated_boundaries(quota, control))
    robustness_tests += REPEATS + 1

    print(f"ROBUSTNESS_GATE={QUALIFICATION}=PASS")
    print(f"AUTHORITATIVE_TIER_A_TASKS={len(authoritative_ids)}")
    print(f"ROBUSTNESS_TEST_COUNT={robustness_tests}")
    print("ROBUSTNESS_SKIPS=0")
    print("SUBJECT_FAILURE_INFRA=0")
    print(f"VERIFIER_SELF_FAILURE_INFRA={REPEATS}")
    print(f"CORE_PYTHON_QUOTA_REPLAY=ISOLATED_PASS_{REPEATS}_OF_{REPEATS}")
    print("VERIFIER_SELF_FAILURE_NEGATIVE_CONTROL=VERIFIER_PROCESS_NONZERO")
    print("OLD_TASK_VERSION_BYTES_CHANGED=0")
    print("REAL_PROVIDER_CALLS=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
