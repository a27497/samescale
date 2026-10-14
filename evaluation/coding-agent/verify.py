"""Trusted verifier entrypoint. Never installed in the coding Agent container."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> None:
    source = Path("/candidate/solution.py")
    oracle = json.loads(Path("/oracle/task.json").read_text())
    try:
        code = source.read_text()
        compile(code, "solution.py", "exec")
    except (OSError, SyntaxError, UnicodeError) as exc:
        print(
            json.dumps(
                {
                    "verdict": "FAIL",
                    "failure_type": "BUILD_FAILURE",
                    "exception": type(exc).__name__,
                }
            )
        )
        return
    # Some upstream tests refer to the candidate's named function as well as `candidate`.
    # Copy those bindings before loading trusted tests, preserving upstream semantics.
    # The container has no network, credentials, or writable oracle/candidate mount.
    program = (
        "import sys\nsys.path.append('/candidate')\n"
        "candidate_ns = {}\n"
        f"exec(compile({code!r}, 'solution.py', 'exec'), candidate_ns)\n"
        "test_ns = dict(candidate_ns)\n"
        f"exec(compile({oracle['test']!r}, 'hidden_test.py', 'exec'), test_ns)\n"
        f"test_ns['check'](candidate_ns[{oracle['entry_point']!r}])\n"
        "print('SAMESCALE_CHECK_COMPLETED')\n"
    )
    try:
        child = subprocess.run(
            [sys.executable, "-I", "-c", program], capture_output=True, timeout=10, check=False
        )
    except subprocess.TimeoutExpired:
        print(json.dumps({"verdict": "FAIL", "failure_type": "TIMEOUT"}))
        return
    sys.stderr.buffer.write(child.stdout + child.stderr)
    passed = child.returncode == 0 and child.stdout.endswith(b"SAMESCALE_CHECK_COMPLETED\n")
    print(
        json.dumps(
            {
                "verdict": "PASS" if passed else "FAIL",
                "failure_type": "NONE" if passed else "HIDDEN_TEST_FAILURE",
                "child_exit_code": child.returncode,
                "check_completed": passed,
            }
        )
    )


if __name__ == "__main__":
    main()
