from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from scripts.swe_verifier_canary import (
    MUTATIONS,
    REPORT,
    classify,
    complete_result,
    external,
    inventory,
    mutate,
    selected,
    sha,
)

from harnesslab.sandbox.models import IsolatedVerifierResult, VerifierLifecycleStage
from harnesslab.tasks.package import digest_tree


def test_fixed_population_is_exactly_all_eighteen_swe_passes() -> None:
    rows = selected(json.loads(REPORT.read_bytes()))
    rules = json.loads(MUTATIONS.read_bytes())
    assert len(rows) == 18
    assert [r["task_id"] for r in rows] == [r["task_id"] for r in rules["mutations"]]
    assert all(r["physical_agent_attempts"] == 1 for r in rows)
    assert rules["pilot_size"] == 5


def test_mutation_preserves_test_patch_and_changes_one_production_site(tmp_path: Path) -> None:
    original = (
        "diff --git a/pkg/value.py b/pkg/value.py\n"
        "--- a/pkg/value.py\n+++ b/pkg/value.py\n"
        "@@ -1 +1 @@\n-def value(): return 0\n+def value(): return 1\n"
    )
    tests = (
        "diff --git a/tests/test_value.py b/tests/test_value.py\n"
        "--- a/tests/test_value.py\n+++ b/tests/test_value.py\n"
        "@@ -1 +1 @@\n-assert value() == 0\n+assert value() == 1\n"
    )
    patch, delta = mutate(
        original + tests,
        "def value(): return 0\n",
        {"path": "pkg/value.py", "before": "return 1", "after": "return 2"},
        tmp_path,
    )
    assert patch.endswith(tests)
    assert "+def value(): return 2" in patch
    assert "-def value(): return 1" in delta
    assert (tmp_path / "pkg/value.py").read_text() == "def value(): return 1\n"


@pytest.mark.parametrize(
    "rule",
    [
        {"path": "../escape.py", "before": "x", "after": "y"},
        {"path": "tests/test_value.py", "before": "x", "after": "y"},
        {"path": "value.py", "before": "absent", "after": "y"},
        {"path": "value.py", "before": "return 1", "after": "return 1"},
        {"path": "value.py", "before": "return 1", "after": "return ("},
    ],
)
def test_unsafe_noop_missing_or_syntax_invalid_mutation_refuses(
    tmp_path: Path,
    rule: dict[str, str],
) -> None:
    patch = (
        "diff --git a/value.py b/value.py\n--- a/value.py\n+++ b/value.py\n"
        "@@ -1 +1 @@\n-def value(): return 0\n+def value(): return 1\n"
    )
    with pytest.raises((ValueError, SyntaxError)):
        mutate(patch, "def value(): return 0\n", rule, tmp_path)


def observation(workspace: Path) -> Any:
    report = {
        "schema_version": 1,
        "passed": True,
        "score": 1.0,
        "checks": [{"name": "required-a", "passed": True, "score": 1.0}],
        "summary": "fixture",
    }
    manifest = SimpleNamespace(
        exit_code=0,
        timed_out=False,
        cancelled=False,
        stdout_truncated=False,
        stderr_truncated=False,
        cleanup_verified=True,
        workspace_input_digest=digest_tree(workspace),
        workspace_output_digest=digest_tree(workspace),
        model_dump=lambda **_: {"fixture": True},
    )
    lifecycle = SimpleNamespace(
        failure_subtype=None,
        stages=[
            SimpleNamespace(stage=s, status=SimpleNamespace(value="COMPLETED"))
            for s in VerifierLifecycleStage
        ],
        model_dump=lambda **_: {"fixture": True},
    )
    return SimpleNamespace(
        run=SimpleNamespace(stdout=json.dumps(report), manifest=manifest), lifecycle=lifecycle
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("timed_out", True),
        ("cancelled", True),
        ("exit_code", 1),
        ("stdout_truncated", True),
        ("stderr_truncated", True),
        ("cleanup_verified", False),
        ("workspace_output_digest", "sha256:drift"),
    ],
)
def test_execution_failure_never_counts_as_detection(
    tmp_path: Path,
    field: str,
    value: Any,
) -> None:
    result = observation(tmp_path)
    setattr(result.run.manifest, field, value)
    with pytest.raises(ValueError, match="incomplete"):
        complete_result(cast(IsolatedVerifierResult, result), tmp_path, ["required-a"])
    assert classify("PASS", "INCONCLUSIVE") == "INCONCLUSIVE"


def test_zero_checks_missing_ids_and_contradiction_cannot_pass(tmp_path: Path) -> None:
    result = observation(tmp_path)
    assert (
        complete_result(cast(IsolatedVerifierResult, result), tmp_path, ["required-a"])["verdict"]
        == "PASS"
    )
    with pytest.raises(ValueError):
        complete_result(cast(IsolatedVerifierResult, result), tmp_path, ["wrong-id"])
    report = json.loads(result.run.stdout)
    report["checks"] = []
    result.run.stdout = json.dumps(report)
    with pytest.raises(ValueError):
        complete_result(cast(IsolatedVerifierResult, result), tmp_path, [])
    report["checks"] = [{"name": "required-a", "passed": False, "score": 0.0}]
    result.run.stdout = json.dumps(report)
    with pytest.raises(ValueError):
        complete_result(cast(IsolatedVerifierResult, result), tmp_path, ["required-a"])
    report["passed"], report["score"] = False, 0.0
    result.run.stdout = json.dumps(report)
    assert (
        complete_result(cast(IsolatedVerifierResult, result), tmp_path, ["required-a"])["verdict"]
        == "FAIL"
    )
    assert classify("PASS", "PASS") == "SURVIVED"
    assert classify("PASS", "FAIL") == "DETECTED"
    assert classify("FAIL", "FAIL") == "INCONCLUSIVE"


def test_inventory_includes_original_git_and_inventory_and_rejects_other_checkout(
    tmp_path: Path,
) -> None:
    root = tmp_path / "original"
    root.mkdir()
    (root / ".git").write_text("gitdir: preserved")
    (root / "inventory.json").write_text("preserved")
    first = inventory([root])
    (root / "inventory.json").chmod(0o600)
    assert first != inventory([root])
    with pytest.raises(ValueError, match="outside every Git"):
        external(root / "output")


@pytest.mark.asyncio
async def test_secondary_witness_preserves_primary_and_uses_separate_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import swe_canary_witness as secondary

    output = tmp_path / "output"
    case = output / "cases/task"
    package_path = "package/task/1.0.0"
    root = case / package_path
    (root / "verifier").mkdir(parents=True)
    (root / "verifier/verify.py").write_text("original verifier")
    spec = {
        "hidden_test_paths": ["tests/hidden.py"],
        "fail_to_pass": ["original"],
        "pass_to_pass": [],
        "test_command": ["original-command"],
    }
    (root / "verifier/acceptance.json").write_text(json.dumps(spec))
    (output / "plan.json").write_text("preregistered")
    for mode in ("control", "mutant"):
        (case / mode / "workspace").mkdir(parents=True)
        (case / mode / "workspace/solution.patch").write_text(mode)
    probe = tmp_path / "probe.py"
    probe.write_text("assert True")
    before = inventory([case])
    monkeypatch.setattr(
        secondary,
        "load_plan",
        lambda _: {
            "cases": [
                {
                    "task_id": "task",
                    "package_path": package_path,
                    "mutation_sha256": "fixed",
                    "image_id": "fixed-image",
                }
            ]
        },
    )
    monkeypatch.setattr(
        secondary, "project", lambda _: {"rows": [{"task_id": "task", "outcome": "SURVIVED"}]}
    )
    monkeypatch.setattr(
        "scripts.swe_canary_witness.TaskPackage.load",
        lambda _: SimpleNamespace(definition=SimpleNamespace(content_digest="secondary-digest")),
    )

    async def fake_verify(*args: Any) -> dict[str, str]:
        assert args[1] == "fixed-image"
        assert args[-1] == ["required-" + sha(b"canary-witness")[:32]]
        return {"verdict": "PASS" if args[2].parent.name == "control" else "FAIL"}

    monkeypatch.setattr(secondary, "verify", fake_verify)
    await secondary.witness(output, "task", probe)
    assert inventory([case]) == before
    copied_spec = json.loads(
        (output / "witnesses/task" / package_path / "verifier/acceptance.json").read_text()
    )
    assert copied_spec["hidden_test_paths"] == spec["hidden_test_paths"]
    value = json.loads((output / "witnesses/task/witness.json").read_text())
    assert value["non_equivalence_confirmed"] is True
    with pytest.raises(FileExistsError):
        await secondary.witness(output, "task", probe)
