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
ROBUSTNESS_V1_CORPUS = ROOT / "release/tier-a-verifier-robustness-v1.json"
ROBUSTNESS_CORPUS = ROOT / "release/tier-a-verifier-robustness-v2.json"
QUALIFICATION = "TIER_A_VERIFIER_ROBUSTNESS_V2"
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


def _assert_verifier_infra(result: VerifierExecutionResult, *, label: str) -> None:
    if (
        result.category is not OutcomeCategory.VERIFIER_ERROR
        or result.passed
        or result.exit_code in {None, 0}
    ):
        raise RuntimeError(
            f"{label}: expected verifier_error/nonzero, got "
            f"category={result.category.value} passed={result.passed} exit={result.exit_code}"
        )


def _verify_probe_fault(package: TaskPackage, source: str, *, label: str) -> None:
    with tempfile.TemporaryDirectory(prefix="harnesslab-verifier-negative-") as temporary:
        task_path = Path(temporary) / package.definition.id / package.definition.version
        task_path.parent.mkdir(parents=True)
        shutil.copytree(package.root, task_path)
        (task_path / "verifier/subject_probe.py").write_text(source, encoding="utf-8")
        broken = TaskPackage.load(task_path)
        materialized = broken.materialize()
        try:
            result = execute_verifier(broken, materialized)
        finally:
            materialized.cleanup()
    _assert_verifier_infra(result, label=label)


def _verify_worker_fault(package: TaskPackage, source: str, *, label: str) -> None:
    with tempfile.TemporaryDirectory(prefix="harnesslab-worker-negative-") as temporary:
        task_path = Path(temporary) / package.definition.id / package.definition.version
        task_path.parent.mkdir(parents=True)
        shutil.copytree(package.root, task_path)
        (task_path / "verifier/subject_worker.py").write_text(source, encoding="utf-8")
        broken = TaskPackage.load(task_path)
        materialized = broken.materialize()
        try:
            result = execute_verifier(broken, materialized)
        finally:
            materialized.cleanup()
    _assert_verifier_infra(result, label=label)


def _verify_verifier_timeout(package: TaskPackage) -> None:
    with tempfile.TemporaryDirectory(prefix="harnesslab-timeout-negative-") as temporary:
        task_path = Path(temporary) / package.definition.id / package.definition.version
        task_path.parent.mkdir(parents=True)
        shutil.copytree(package.root, task_path)
        verify_path = task_path / "verifier/verify.py"
        verify_path.write_text(
            verify_path.read_text(encoding="utf-8").replace(
                "def _worker_timeout(workspace: Path) -> int:\n",
                "def _worker_timeout(workspace: Path) -> int:\n    return 1\n",
            ),
            encoding="utf-8",
        )
        (task_path / "verifier/subject_probe.py").write_text(
            "def main() -> int:\n    while True:\n        pass\n",
            encoding="utf-8",
        )
        broken = TaskPackage.load(task_path)
        materialized = broken.materialize()
        try:
            result = execute_verifier(broken, materialized)
        finally:
            materialized.cleanup()
    _assert_verifier_infra(result, label="verifier-owned-timeout")


def _verify_subject_timeout(package: TaskPackage) -> None:
    materialized = package.materialize()
    try:
        target = _primary_subject_path(package, materialized.workspace)
        target.write_text(
            target.read_text(encoding="utf-8") + "\nwhile True:\n    pass\n",
            encoding="utf-8",
        )
        result = execute_verifier(package, materialized)
    finally:
        materialized.cleanup()
    _assert_subject_result(result, passed=False, label=f"{package.definition.id}:timeout")
    if "SUBJECT_EXECUTION_TIMEOUT" not in {check.detail for check in result.checks}:
        raise RuntimeError(f"{package.definition.id}: timeout lost subject provenance")


def _verify_mutated_probe(package: TaskPackage, old: str, new: str, *, label: str) -> None:
    with tempfile.TemporaryDirectory(prefix="harnesslab-harness-negative-") as temporary:
        task_path = Path(temporary) / package.definition.id / package.definition.version
        task_path.parent.mkdir(parents=True)
        shutil.copytree(package.root, task_path)
        probe = task_path / "verifier/subject_probe.py"
        source = probe.read_text(encoding="utf-8")
        if old not in source:
            raise RuntimeError(f"{label}: mutation anchor missing")
        probe.write_text(source.replace(old, new, 1), encoding="utf-8")
        broken = TaskPackage.load(task_path)
        materialized = broken.materialize()
        try:
            result = execute_verifier(broken, materialized)
        finally:
            materialized.cleanup()
    _assert_verifier_infra(result, label=label)


def _verify_quota_defect(package: TaskPackage) -> None:
    materialized = package.materialize()
    try:
        (materialized.workspace / "quota.py").write_text(QUOTA_DEFECT, encoding="utf-8")
        result = execute_verifier(package, materialized)
    finally:
        materialized.cleanup()
    _assert_subject_result(result, passed=False, label="core-python-quota-known-defect")
    details = {check.detail for check in result.checks}
    if "SUBJECT_EXECUTION_FAILURE:TypeError" not in details:
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
                try:
                    result = await runner.run_hidden_verifier_workspace(
                        quota,
                        materialized.workspace,
                        timeout_seconds=30,
                        run_id=f"tier-a-quota-replay-{repeat + 1}",
                    )
                except SandboxExecutionError as exc:
                    raise RuntimeError(
                        f"quota sandbox replay failed: diagnostics={exc.diagnostics!r}"
                    ) from exc
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
            'def main() -> int:\n    raise TypeError("deliberate verifier-owned failure")\n',
            encoding="utf-8",
        )
        broken = TaskPackage.load(broken_path)
        materialized = broken.materialize(root / "negative-workspace")
        try:
            try:
                await runner.run_hidden_verifier_workspace(
                    broken,
                    materialized.workspace,
                    timeout_seconds=30,
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


def _verify_v1_gap_reproductions(package: TaskPackage) -> int:
    exception_sources = {
        "TypeError": 'def main() -> int:\n    raise TypeError("verifier owned")\n',
        "AttributeError": 'def main() -> int:\n    raise AttributeError("verifier owned")\n',
        "KeyError": 'def main() -> int:\n    raise KeyError("verifier owned")\n',
        "IndexError": 'def main() -> int:\n    raise IndexError("verifier owned")\n',
        "JSONDecodeError": (
            "import json\n\n"
            'def main() -> int:\n    raise json.JSONDecodeError("verifier owned", "x", 0)\n'
        ),
        "SyntaxError": 'def main() -> int:\n    raise SyntaxError("verifier owned")\n',
        "ImportError": 'def main() -> int:\n    raise ImportError("verifier owned")\n',
    }
    reproduced = 0
    for name, source in exception_sources.items():
        with tempfile.TemporaryDirectory(prefix="harnesslab-v1-type-gap-") as temporary:
            task_path = Path(temporary) / package.definition.id / package.definition.version
            task_path.parent.mkdir(parents=True)
            shutil.copytree(package.root, task_path)
            (task_path / "verifier/subject_probe.py").write_text(source, encoding="utf-8")
            broken = TaskPackage.load(task_path)
            materialized = broken.materialize()
            try:
                broken.apply_oracle(materialized)
                result = execute_verifier(broken, materialized)
            finally:
                materialized.cleanup()
        _assert_subject_result(result, passed=False, label=f"v1-type-gap:{name}")
        if f"SUBJECT_EXCEPTION_{name}" not in {check.detail for check in result.checks}:
            raise RuntimeError(f"V1 {name} confusion was not reproduced")
        reproduced += 1

    timeout_details: list[str] = []
    for verifier_owned in (False, True):
        with tempfile.TemporaryDirectory(prefix="harnesslab-v1-timeout-gap-") as temporary:
            task_path = Path(temporary) / package.definition.id / package.definition.version
            task_path.parent.mkdir(parents=True)
            shutil.copytree(package.root, task_path)
            verify_path = task_path / "verifier/verify.py"
            verify_path.write_text(
                verify_path.read_text(encoding="utf-8").replace(
                    "def _worker_timeout(workspace: Path) -> int:\n",
                    "def _worker_timeout(workspace: Path) -> int:\n    return 1\n",
                ),
                encoding="utf-8",
            )
            if verifier_owned:
                (task_path / "verifier/subject_probe.py").write_text(
                    "def main() -> int:\n    while True:\n        pass\n",
                    encoding="utf-8",
                )
            broken = TaskPackage.load(task_path)
            materialized = broken.materialize()
            try:
                if not verifier_owned:
                    target = _primary_subject_path(broken, materialized.workspace)
                    target.write_text(
                        target.read_text(encoding="utf-8") + "\nwhile True:\n    pass\n",
                        encoding="utf-8",
                    )
                result = execute_verifier(broken, materialized)
            finally:
                materialized.cleanup()
        _assert_subject_result(result, passed=False, label="v1-timeout-gap")
        details = {check.detail for check in result.checks}
        if "SUBJECT_WORKER_TIMEOUT" not in details:
            raise RuntimeError("V1 timeout ambiguity was not reproduced")
        timeout_details.append("SUBJECT_WORKER_TIMEOUT")
        reproduced += 1
    if len(set(timeout_details)) != 1:
        raise RuntimeError("V1 subject/verifier timeout outputs unexpectedly differed")
    return reproduced


def _verify_v2_fault_matrix(packages: dict[str, TaskPackage]) -> int:
    python_control = packages["micro-python-clamp"]
    probe_faults = {
        "RuntimeError": 'def main() -> int:\n    raise RuntimeError("verifier owned")\n',
        "TypeError": 'def main() -> int:\n    raise TypeError("verifier owned")\n',
        "AttributeError": 'def main() -> int:\n    raise AttributeError("verifier owned")\n',
        "KeyError": 'def main() -> int:\n    raise KeyError("verifier owned")\n',
        "IndexError": 'def main() -> int:\n    raise IndexError("verifier owned")\n',
        "JSONDecodeError": (
            "import json\n\n"
            'def main() -> int:\n    raise json.JSONDecodeError("verifier owned", "x", 0)\n'
        ),
        "SyntaxError": "def main(:\n",
        "ImportError": 'def main() -> int:\n    raise ImportError("verifier owned")\n',
    }
    count = 0
    for name, source in probe_faults.items():
        _verify_probe_fault(python_control, source, label=f"python-verifier-{name}")
        count += 1
    _verify_worker_fault(
        python_control,
        'print("{}")\n',
        label="malformed-worker-protocol",
    )
    count += 1
    _verify_worker_fault(
        python_control,
        'raise RuntimeError("verifier worker nonzero")\n',
        label="verifier-worker-nonzero",
    )
    count += 1
    _verify_verifier_timeout(python_control)
    count += 1

    java = packages["core-java-quota"]
    _verify_mutated_probe(
        java,
        "public final class HiddenVerifier {",
        "public final class HiddenVerifier { this is invalid",
        label="java-hidden-harness-syntax",
    )
    count += 1
    _verify_mutated_probe(
        java,
        "public static void main(String[] args) {",
        "public static void main(String[] args) {\n"
        '        if (true) throw new RuntimeException("verifier owned");',
        label="java-hidden-harness-runtime",
    )
    count += 1

    typescript = packages["core-typescript-quota"]
    _verify_mutated_probe(
        typescript,
        "const rejects = args =>",
        "const rejects = ; args =>",
        label="typescript-hidden-harness-syntax",
    )
    count += 1
    _verify_mutated_probe(
        typescript,
        "const rejects = args =>",
        'throw new Error("verifier owned");\nconst rejects = args =>',
        label="typescript-hidden-harness-runtime",
    )
    count += 1
    _verify_mutated_probe(
        typescript,
        "values = json.loads(run.stdout)",
        'values = json.loads("}{")',
        label="typescript-verifier-output-parse",
    )
    count += 1

    for package, language in ((java, "java"), (typescript, "typescript")):
        for mode in ("load-failure", "runtime-failure"):
            result = _run_materialized(package, mode)
            _assert_subject_result(
                result,
                passed=False,
                label=f"{language}-candidate-{mode}",
            )
            count += 1

    _verify_probe_fault(
        packages["core-python-quota"],
        'def main() -> int:\n    raise TypeError("verifier owned")\n',
        label="core-python-quota-verifier-TypeError",
    )
    return count + 1


def main() -> int:
    methodology = load_evaluation_methodology(METHODOLOGY)
    tier_a = next(
        item for item in methodology.task_tiers if item.tier.value == "TIER_A_MICRO_CONTRACT"
    )
    historical = _load_json(HISTORICAL_CORPUS)
    robustness_v1 = _load_json(ROBUSTNESS_V1_CORPUS)
    robustness = _load_json(ROBUSTNESS_CORPUS)
    if robustness.get("qualification") != QUALIFICATION:
        raise RuntimeError("robustness corpus qualification identity mismatch")
    old_items = {item["task_id"]: item for item in historical["tasks"]}
    v1_items = {item["task_id"]: item for item in robustness_v1["tasks"]}
    new_items = {item["task_id"]: item for item in robustness["tasks"]}
    authoritative_ids = tuple(tier_a.current_task_ids)
    if (
        set(old_items) != set(authoritative_ids)
        or set(v1_items) != set(authoritative_ids)
        or set(new_items) != set(authoritative_ids)
    ):
        raise RuntimeError("Tier-A corpus does not match the authoritative methodology")

    packages: dict[str, TaskPackage] = {}
    v1_packages: dict[str, TaskPackage] = {}
    for task_id in authoritative_ids:
        old = TaskPackage.load(ROOT / old_items[task_id]["package_path"])
        v1 = TaskPackage.load(ROOT / v1_items[task_id]["package_path"])
        new = TaskPackage.load(ROOT / new_items[task_id]["package_path"])
        if (
            old.definition.version != "1.0.0"
            or v1.definition.version != "1.0.1"
            or new.definition.version != "1.0.2"
        ):
            raise RuntimeError(f"{task_id}: version map is not 1.0.0 -> 1.0.1 -> 1.0.2")
        if (
            old.definition.content_digest != old_items[task_id]["task_digest"]
            or old.verifier_digest != old_items[task_id]["verifier_identity"]
        ):
            raise RuntimeError(f"{task_id}: historical 1.0.0 bytes changed")
        if (
            v1.definition.content_digest != v1_items[task_id]["task_digest"]
            or v1.verifier_digest != v1_items[task_id]["verifier_identity"]
        ):
            raise RuntimeError(f"{task_id}: historical 1.0.1 bytes changed")
        if (
            new.definition.content_digest != new_items[task_id]["task_digest"]
            or new.verifier_digest != new_items[task_id]["verifier_identity"]
        ):
            raise RuntimeError(f"{task_id}: robustness V2 manifest identity drifted")
        v1_packages[task_id] = v1
        packages[task_id] = new

    v1_reproductions = _verify_v1_gap_reproductions(v1_packages["core-python-quota"])
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

    for task_id in authoritative_ids:
        package = packages[task_id]
        if package.definition.metadata["language"] == "python":
            _verify_subject_timeout(package)
            robustness_tests += 1

    quota = packages["core-python-quota"]
    for _ in range(REPEATS):
        _verify_quota_defect(quota)
        robustness_tests += 1

    robustness_tests += _verify_v2_fault_matrix(packages)

    control = packages["micro-python-clamp"]
    asyncio.run(_verify_isolated_boundaries(quota, control))
    robustness_tests += REPEATS + 1

    print(f"ROBUSTNESS_GATE={QUALIFICATION}=PASS")
    print(f"AUTHORITATIVE_TIER_A_TASKS={len(authoritative_ids)}")
    print(f"V1_GAP_REPRODUCTION_TEST_COUNT={v1_reproductions}")
    print("V1_REPRODUCED_VERIFIER_TYPE_CONFUSION=YES")
    print("V1_REPRODUCED_TIMEOUT_AMBIGUITY=YES")
    print(f"ROBUSTNESS_TEST_COUNT={robustness_tests}")
    print("ROBUSTNESS_SKIPS=0")
    print("SUBJECT_FAILURE_INFRA=0")
    print("VERIFIER_FAULT_MATRIX=PASS")
    print("SUBJECT_TYPEERROR_RESULT=CAPABILITY_FAIL")
    print("VERIFIER_TYPEERROR_RESULT=INFRA")
    print("SUBJECT_TIMEOUT_RESULT=CAPABILITY_FAIL:SUBJECT_EXECUTION_TIMEOUT")
    print("VERIFIER_TIMEOUT_RESULT=INFRA:VERIFIER_TIMEOUT")
    print("JAVA_SUBJECT_COMPILE_FAILURE=CAPABILITY_FAIL")
    print("JAVA_VERIFIER_HARNESS_FAILURE=INFRA")
    print("TYPESCRIPT_SUBJECT_FAILURE=CAPABILITY_FAIL")
    print("TYPESCRIPT_VERIFIER_HARNESS_FAILURE=INFRA")
    print(f"CORE_PYTHON_QUOTA_REPLAY=ISOLATED_PASS_{REPEATS}_OF_{REPEATS}")
    print("VERIFIER_SELF_FAILURE_NEGATIVE_CONTROL=VERIFIER_PROCESS_NONZERO")
    print("OLD_1_0_0_BYTES_CHANGED=0")
    print("OLD_1_0_1_BYTES_CHANGED=0")
    print("REAL_PROVIDER_CALLS=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
