"""Dependency-free policy checks also run before conditional CI jobs can be skipped."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.ci_scope import Scope, branch_paths, check_results, classify
from scripts.run_ci_regressions import ROOT, collected, full_groups, shard, verify_junit


class RoutingTests(unittest.TestCase):
    def test_pr_and_main_always_require_full_including_docs(self) -> None:
        for event, ref in (
            ("pull_request", "refs/pull/1/merge"),
            ("push", "refs/heads/main"),
            ("push", "refs/tags/v1"),
            ("merge_group", "refs/heads/queue"),
        ):
            self.assertEqual(classify(event, ref, ["README.md"]).full, True)

    def test_frontend_and_plain_docs_have_distinct_feedback(self) -> None:
        self.assertEqual(classify("push", "refs/heads/topic", ["docs/qa/note.md"]).frontend, False)
        scope = classify("push", "refs/heads/topic", ["frontend/src/App.vue", "README.md"])
        self.assertEqual((scope.full, scope.frontend), (False, True))

    def test_sensitive_unknown_empty_and_missing_inputs_require_full(self) -> None:
        for path in (
            "src/harnesslab/api/app.py",
            "tests/test_contracts.py",
            "scripts/a.py",
            "uv.lock",
            "pyproject.toml",
            ".github/workflows/ci.yml",
            "release/a.json",
            "docs/evidence/a.md",
            "docs/recruiter/template.html",
            "docs/ANALYST.md",
            "docs/contract.json",
            "new-root-input",
            "AGENTS.md",
        ):
            self.assertTrue(classify("push", "refs/heads/topic", ["README.md", path]).full, path)
        missing_paths: tuple[list[str] | None, ...] = (None, [])
        for paths in missing_paths:
            self.assertTrue(classify("push", "refs/heads/topic", paths).full)

    def test_matrix_is_all_four_full_shards_or_single_dto_boundary(self) -> None:
        self.assertEqual(
            Scope(True, True, "").matrix["include"],
            [{"index": i, "count": 4, "mode": "full"} for i in range(4)],
        )
        self.assertEqual(
            Scope(False, True, "").matrix["include"], [{"index": 0, "count": 1, "mode": "boundary"}]
        )

    def test_branch_comparison_keeps_earlier_backend_changes_and_rename_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            def git(*args: str) -> None:
                subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)

            git("init")
            git("config", "user.name", "CI fixture")
            git("config", "user.email", "ci@example.invalid")
            (root / "source.py").write_text("baseline")
            git("add", ".")
            git("commit", "-m", "baseline")
            git("update-ref", "refs/remotes/origin/main", "HEAD")
            (root / "source.py").write_text("changed")
            git("add", ".")
            git("commit", "-m", "backend")
            (root / "README.md").write_text("later docs")
            git("add", ".")
            git("commit", "-m", "docs")
            self.assertIn("source.py", branch_paths(root) or [])
            self.assertTrue(classify("push", "refs/heads/topic", branch_paths(root)).full)
            git("mv", "source.py", "renamed.md")
            git("commit", "-m", "rename")
            self.assertIn("source.py", branch_paths(root) or [])
            git("update-ref", "-d", "refs/remotes/origin/main")
            self.assertIsNone(branch_paths(root))

    def test_failure_cancellation_skip_and_missing_required_job_cannot_pass(self) -> None:
        needs = {
            name: {"result": "success"}
            for name in ("scope", "python-checks", "frontend", "backend")
        }
        check_results(needs, full=True, frontend=True)
        for name in needs:
            for result in ("failure", "cancelled", "skipped", None):
                with self.assertRaises(ValueError):
                    check_results({**needs, name: {"result": result}}, full=True, frontend=True)
        with self.assertRaises(ValueError):
            check_results({"scope": {"result": "success"}}, full=False, frontend=True)
        check_results({"scope": {"result": "success"}}, full=False, frontend=False)

    def test_shards_are_disjoint_exhaustive_and_deterministic(self) -> None:
        nodes = [
            f"{selector}::test_case[{i}]"
            for group in full_groups()
            for selector in group
            for i in range(3)
        ]
        groups = [shard(nodes, i, 4) for i in range(4)]
        self.assertEqual(sorted(node for group in groups for node in group), sorted(nodes))
        self.assertEqual(len({node for group in groups for node in group}), len(nodes))
        self.assertEqual(groups, [shard(nodes, i, 4) for i in range(4)])
        for nodes, index, count in (([], 0, 4), (["x", "x"], 0, 4), (["x"], 4, 4), (["x"], 0, 0)):
            with self.assertRaises(ValueError):
                shard(nodes, index, count)

    def test_module_shared_fixtures_are_not_rebuilt_in_multiple_shards(self) -> None:
        groups = full_groups()
        for selector in json.loads((ROOT / ".github/ci-core-selectors.json").read_text()):
            self.assertEqual(sum(selector in g for g in groups), 1)
        nodes = [
            "tests/test_kc_release_reconciliation.py::test_example[a]",
            "tests/test_kc_release_reconciliation.py::test_example[b]",
        ]
        self.assertEqual(shard(nodes, 0, 4), nodes)
        with self.assertRaises(ValueError):
            shard(["tests/unknown.py::test_example"], 0, 4)

    def test_collection_and_junit_fail_closed(self) -> None:
        self.assertEqual(
            collected("tests/a.py::test_x\n1 test collected in 0.1s"), ["tests/a.py::test_x"]
        )
        for text in (
            "no tests collected",
            "tests/a.py::test_x\n2 tests collected",
            "tests/a.py::test_x\ntests/a.py::test_x\n2 tests collected",
        ):
            with self.assertRaises(ValueError):
                collected(text)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "tests.xml"
            path.write_text('<testsuites><testcase name="x"/></testsuites>')
            verify_junit(path, 1)
            for tag in ("skipped", "failure", "error"):
                path.write_text(f'<testsuites><testcase name="x"><{tag}/></testcase></testsuites>')
                with self.assertRaises(ValueError):
                    verify_junit(path, 1)
            path.write_text("<testsuites/>")
            with self.assertRaises(ValueError):
                verify_junit(path, 0)

    def test_original_bounded_inventory_is_unchanged(self) -> None:
        selectors = json.loads((ROOT / ".github/ci-core-selectors.json").read_text())
        self.assertEqual(selectors[29:], ["tests/test_failure_diagnosis.py"])
        canonical = json.dumps(selectors[:29], separators=(",", ":")).encode()
        # Independent fingerprint of all 29 selectors taken from main@5bfb674 before edits.
        self.assertEqual(
            hashlib.sha256(canonical).hexdigest(),
            "cd5ba1383684d17ed18fe4cc85f81d7d105a5cb74dc5f8d1e73991e1bfce7423",
        )


if __name__ == "__main__":
    unittest.main()
