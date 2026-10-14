"""Existing HumanEval hidden-check semantics, emitted as the existing VerifierReport schema."""

import json
import subprocess
import sys
from pathlib import Path


def main():
    assets = Path(__file__).parent
    oracle = json.loads((assets / "task.json").read_text())
    workspace = Path(sys.argv[1])
    failure = "NONE"
    passed = False
    try:
        code = (workspace / "solution.py").read_text()
        compile(code, "solution.py", "exec")
    except (OSError, SyntaxError, UnicodeError):
        failure = "BUILD_FAILURE"
    else:
        program = (
            "import sys\nsys.path.append('/workspace')\ncandidate_ns = {}\n"
            + "exec(compile("
            + repr(code)
            + ", 'solution.py', 'exec'), candidate_ns)\n"
            + "test_ns = dict(candidate_ns)\nexec(compile("
            + repr(oracle["test"])
            + ", 'hidden_test.py', 'exec'), test_ns)\n"
            + "test_ns['check'](candidate_ns["
            + repr(oracle["entry_point"])
            + "])\n"
            + "print('SAMESCALE_CHECK_COMPLETED')\n"
        )
        try:
            child = subprocess.run(
                [sys.executable, "-I", "-c", program], capture_output=True, timeout=10
            )
            sys.stderr.buffer.write(child.stdout + child.stderr)
            passed = child.returncode == 0 and child.stdout.endswith(b"SAMESCALE_CHECK_COMPLETED\n")
            failure = "NONE" if passed else "HIDDEN_TEST_FAILURE"
        except subprocess.TimeoutExpired:
            failure = "TIMEOUT"
    print(
        json.dumps(
            {
                "schema_version": 1,
                "passed": passed,
                "score": float(passed),
                "checks": [
                    {
                        "name": "humaneval-hidden-check",
                        "passed": passed,
                        "score": float(passed),
                        "detail": failure,
                    }
                ],
                "summary": "Original fixed HumanEval hidden check, independently executed.",
            }
        )
    )


if __name__ == "__main__":
    main()
