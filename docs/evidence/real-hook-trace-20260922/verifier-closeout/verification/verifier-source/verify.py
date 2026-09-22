import contextlib
import io
import json
import sys
from pathlib import Path

# Independent oracle: no subject test runner, captured command, model or stdout parsing.
CASES = (
    ("empty_interval", 3, 1, 0),
    ("inclusive_boundary", 1, 3, 6),
    ("singleton", 4, 4, 4),
    ("negative_endpoints", -2, 2, 0),
)
checks = []
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    namespace = {}
    exec(
        compile((Path(sys.argv[1]) / "calculator.py").read_bytes(), "calculator.py", "exec"),
        namespace,
    )
    for name, start, end, expected in CASES:
        observed = namespace["inclusive_sum"](start, end)
        passed = type(observed) is int and observed == expected
        checks.append({"name": name, "passed": passed, "score": float(passed), "detail": None})
print(
    json.dumps(
        {
            "schema_version": 1,
            "passed": all(c["passed"] for c in checks),
            "score": sum(c["passed"] for c in checks) / len(checks),
            "checks": checks,
            "summary": "Independent inclusive interval contract checks",
        },
        sort_keys=True,
    )
)
