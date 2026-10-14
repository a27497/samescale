"""Campaign-only patch task: frozen image + supplied delivery, hidden required checks.

Runs under the existing SameScale pinned, network-disabled, read-only Verifier.
No import contract or product resource limit is changed.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def main():
    assets = Path(__file__).parent
    spec = json.loads((assets / "acceptance.json").read_text())
    root = Path("/tmp/repository")
    root.mkdir()
    baseline = Path("/testbed")
    # Writable directory skeleton, immutable file symlinks; materialize edited files only.
    for current, dirs, names in os.walk(str(baseline)):
        dirs[:] = [x for x in dirs if x != ".git" and x != "__pycache__"]
        relative = Path(current).relative_to(baseline)
        destination = root / relative
        destination.mkdir(parents=True, exist_ok=True)
        for name in names:
            (destination / name).symlink_to(Path(current) / name)
    # Python resolves a symlinked script's directory; SymPy path_hack must use this candidate.
    if spec["repo"] == "sympy/sympy":
        for name in ("bin/test", "bin/get_sympy.py"):
            target = root / name
            data = target.read_bytes()
            target.unlink()
            target.write_bytes(data)
    # Recreate pristine test files before applying delivery; later restore trusted hidden versions.
    for name in spec["hidden_test_paths"]:
        target = root / name
        if target.is_symlink():
            data = target.read_bytes()
            target.unlink()
            target.write_bytes(data)
    subprocess.run(
        ["git", "apply", "--reverse", str(assets / "test.patch")], cwd=str(root), check=True
    )
    payload = Path(sys.argv[1]) / "solution.patch"
    text = payload.read_text()
    paths = set()
    for line in text.splitlines():
        if line.startswith(("--- a/", "+++ b/")):
            name = line[6:].split("\t", 1)[0]
            parts = Path(name).parts
            if not parts or any(p in (".", "..", ".git") for p in parts) or name.startswith("/"):
                raise ValueError("unsafe patch path")
            paths.add(name)
        elif line.startswith(("--- ", "+++ ")) and line[4:] != "/dev/null":
            raise ValueError("unsupported quoted patch path")
    for name in paths:
        target = root / name
        if target.is_symlink():
            data = target.read_bytes()
            target.unlink()
            target.write_bytes(data)
    if text:
        subprocess.run(
            ["git", "apply", "--whitespace=nowarn", str(payload)], cwd=str(root), check=True
        )
    # Official test patch has priority: Subject cannot edit the hidden acceptance tests.
    for name in spec["hidden_test_paths"]:
        target = root / name
        if target.exists() or target.is_symlink():
            target.unlink()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(baseline / name)
    env = dict(
        os.environ,
        HOME="/tmp",
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONPATH=str(root),
        PYTEST_ADDOPTS="-rA --color=no",
        PIP_NO_INDEX="1",
    )
    process = subprocess.run(
        spec["test_command"],
        cwd=str(root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=27,
    )
    log = process.stdout.decode("utf-8", errors="replace")
    # Preserve actual merged test output for host upstream-parser cross-check/offline review.
    sys.stderr.write(log)
    if process.returncode < 0:
        raise RuntimeError("test runner terminated by signal: " + str(process.returncode))
    statuses = {}
    if spec["repo"] == "sympy/sympy":
        for match in re.findall(r"(_*) (.*)\.py:(.*) (_*)", log):
            statuses[match[1] + ".py:" + match[2]] = "FAILED"
        for line in log.splitlines():
            line = line.strip()
            if line.startswith("test_"):
                for ending, status in [(" E", "ERROR"), (" F", "FAILED"), (" ok", "PASSED")]:
                    if line.endswith(ending):
                        statuses[line.split()[0]] = status
    else:
        # Same algorithm as upstream 4.1.0 parse_log_pytest_v2 (Astropy/Sphinx).
        escapes = "".join(chr(c) for c in range(1, 32))
        translator = str.maketrans("", "", escapes)
        for line in log.splitlines():
            line = re.sub(r"\[(\d+)m", "", line).translate(translator)
            states = ("PASSED", "FAILED", "SKIPPED", "ERROR", "XFAIL")
            if any(line.startswith(s) for s in states):
                if line.startswith("FAILED"):
                    line = line.replace(" - ", " ")
                fields = line.split()
                if len(fields) >= 2:
                    statuses[fields[1]] = fields[0]
            elif any(line.endswith(s) for s in states):
                fields = line.split()
                if len(fields) >= 2:
                    statuses[fields[0]] = fields[1]
    required = spec["fail_to_pass"] + spec["pass_to_pass"]
    missing = [name for name in required if name not in statuses]
    if missing:
        raise RuntimeError("missing required tests; no acceptance established: " + repr(missing))
    checks = [
        {
            "name": "required-" + hashlib.sha256(name.encode()).hexdigest()[:32],
            "passed": statuses[name] == "PASSED",
            "score": float(statuses[name] == "PASSED"),
        }
        for name in required
    ]
    passed = all(c["passed"] for c in checks)
    print(
        json.dumps(
            {
                "schema_version": 1,
                "passed": passed,
                "score": sum(c["score"] for c in checks) / len(checks),
                "checks": checks,
                "summary": (
                    "Fixed SWE-bench required tests; non-required suite failures retained in log."
                ),
            }
        )
    )


if __name__ == "__main__":
    main()
