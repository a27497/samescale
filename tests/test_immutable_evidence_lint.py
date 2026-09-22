"""Frozen inputs retain their bytes without exempting maintained Python from Ruff."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = Path("docs/evidence/real-hook-trace-20260922/verifier-closeout/verification")
FROZEN = (
    BUNDLE / "final-workspace/verify_fixture.py",
    BUNDLE / "task-package/hook-inclusive-sum/1.0.0/workspace/verify_fixture.py",
    BUNDLE / "verifier-run/workspace/verify_fixture.py",
)
FIXTURE_DIGEST = "sha256:8b439065f296f2a810cd66fbb7300750cab34dd6d225758ba89289bd989a0dc3"
BUNDLE_DIGEST = "sha256:7eabbf0805c2e9fb3ec89ecc338850c31dffe2aea513928391f7e3195c5e2971"


def test_frozen_lint_inputs_keep_original_bundle_and_file_digests() -> None:
    raw = (ROOT / BUNDLE / "bundle.json").read_bytes()
    assert "sha256:" + hashlib.sha256(raw).hexdigest() == BUNDLE_DIGEST
    inventory = json.loads(raw)["files"]
    for path in FROZEN:
        assert "sha256:" + hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == FIXTURE_DIGEST
        assert inventory[path.relative_to(BUNDLE).as_posix()] == FIXTURE_DIGEST


def test_evidence_boundary_does_not_relax_lint_rules() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["ruff"]
    assert config["extend-exclude"] == ["docs/evidence/**"]
    assert config["src"] == ["src", "tests", "scripts"]
    assert config["lint"]["select"] == ["E", "F", "I", "UP", "B", "SIM", "RUF"]
    assert not config["lint"].get("ignore")
    assert not config["lint"].get("extend-ignore")


def test_ruff_discovery_excludes_evidence_and_checks_all_other_python(tmp_path: Path) -> None:
    # Use actual configuration and identical bytes in a disposable tree, never mutate evidence.
    (tmp_path / "pyproject.toml").write_bytes((ROOT / "pyproject.toml").read_bytes())
    fixture = (ROOT / FROZEN[0]).read_bytes()
    checked = (
        Path("src/probe.py"),
        Path("tests/probe.py"),
        Path("scripts/probe.py"),
        Path("tasks/probe.py"),
        Path("probe.py"),
        Path("docs/ordinary/probe.py"),
        Path("docs/evidence_other/probe.py"),
    )
    excluded = (*FROZEN, Path("docs/evidence/historical/probe.py"))
    for path in (*excluded, *checked):
        destination = tmp_path / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(fixture)
    run = subprocess.run(
        [sys.executable, "-m", "ruff", "check", ".", "--output-format", "json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    # This failure is intentional: the unfrozen copies must still trigger the original rule.
    assert run.returncode == 1, run.stderr
    findings = json.loads(run.stdout)
    assert len(findings) == len(checked)
    assert {item["code"] for item in findings} == {"I001"}
    assert {Path(item["filename"]).relative_to(tmp_path) for item in findings} == set(checked)

    # Explicit file input bypasses discovery exclusions: I001 remains enabled even here.
    explicit = subprocess.run(
        [sys.executable, "-m", "ruff", "check", str(FROZEN[0]), "--output-format", "json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert explicit.returncode == 1, explicit.stderr
    assert [item["code"] for item in json.loads(explicit.stdout)] == ["I001"]


def evidence_execution_dependencies(source: str) -> list[int]:
    """Bounded static guard for imports and evidence paths flowing into execution sinks.

    Read-only parsing/hashing is allowed. This supplements review; arbitrary runtime
    strings and operator-supplied paths cannot be proven safe by an AST scan.
    """
    tree = ast.parse(source)
    bindings: dict[str, ast.AST] = {}
    aliases: dict[str, str] = {}
    issues = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for imported in node.names:
                aliases[imported.asname or imported.name] = imported.name
                if imported.name.startswith("docs.evidence"):
                    issues.append(node.lineno)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.startswith("docs.evidence"):
                issues.append(node.lineno)
            for imported in node.names:
                aliases[imported.asname or imported.name] = module + "." + imported.name
                if module == "docs" and imported.name == "evidence":
                    issues.append(node.lineno)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    bindings[target.id] = node.value

    def text(node: ast.AST, seen: frozenset[str] = frozenset()) -> str:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in bindings and node.id not in seen:
                return text(bindings[node.id], seen | {node.id})
            return aliases.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            return text(node.value, seen) + "." + node.attr
        if isinstance(node, ast.BinOp):
            separator = "/" if isinstance(node.op, ast.Div) else ""
            return text(node.left, seen) + separator + text(node.right, seen)
        if isinstance(node, (ast.List, ast.Tuple)):
            return " ".join(text(item, seen) for item in node.elts)
        if isinstance(node, ast.Call):
            name = ast.unparse(node.func).rsplit(".", 1)[-1]
            if name in {"Path", "str", "read_text", "read_bytes", "resolve", "joinpath"}:
                owner = text(node.func.value, seen) if isinstance(node.func, ast.Attribute) else ""
                return "/".join([owner, *(text(arg, seen) for arg in node.args)])
        return ""

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = text(node.func).rsplit(".", 1)[-1]
        arguments = " ".join(text(arg) for arg in node.args)
        evidence = "docs/evidence" in arguments or "docs.evidence" in arguments
        loader = name in {
            "exec",
            "eval",
            "compile",
            "run_path",
            "import_module",
            "__import__",
            "spec_from_file_location",
            "SourceFileLoader",
        }
        process = name in {"run", "Popen", "check_call", "check_output", "system"}
        python_command = "python" in arguments or "sys.executable" in arguments
        path_injection = "sys.path" in text(node.func) and name in {"insert", "append", "extend"}
        if evidence and (loader or path_injection or (process and python_command)):
            issues.append(node.lineno)
    return sorted(set(issues))


@pytest.mark.parametrize(
    "source",
    [
        "import docs.evidence.example",
        "from docs.evidence import example",
        "from docs import evidence",
        "import runpy as runner\nrunner.run_path('docs/evidence/example.py')",
        "from importlib import import_module as load\nload('docs.evidence.example')",
        "from pathlib import Path\np = Path('docs') / 'evidence' / 'x.py'\n"
        "exec(compile(p.read_text(), str(p), 'exec'))",
        "import subprocess, sys\np = 'docs/evidence/x.py'\nsubprocess.run([sys.executable, p])",
        "import sys\nsys.path.insert(0, 'docs/evidence')",
    ],
)
def test_dependency_guard_rejects_executable_evidence(source: str) -> None:
    assert evidence_execution_dependencies(source)


def test_dependency_guard_allows_read_only_evidence() -> None:
    assert not evidence_execution_dependencies(
        "import json\nfrom pathlib import Path\n"
        "data = json.loads(Path('docs/evidence/report.json').read_text())\n"
        "source_bytes = Path('docs/evidence/fixture.py').read_bytes()"
    )


def test_maintained_python_has_no_evidence_execution_dependency() -> None:
    paths = set(ROOT.glob("*.py"))
    for directory in ("src", "tests", "scripts", "tasks", "docker", "alembic"):
        paths.update((ROOT / directory).rglob("*.py"))
    assert paths
    violations = {}
    for path in sorted(paths):
        if "__pycache__" in path.parts:
            continue
        lines = evidence_execution_dependencies(path.read_text())
        if lines:
            violations[path.relative_to(ROOT).as_posix()] = lines
    assert not violations, violations
