from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def main() -> int:
    workspace = Path(sys.argv[1])
    sys.path.insert(0, str(workspace))
    spec = importlib.util.spec_from_file_location("subject_settings", workspace / "settings.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load settings.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from defaults import CloseTracker

    tracker = CloseTracker()
    session = module.ManagedSession(tracker)
    delegated = session.send("alpha") == "sent:alpha" and tracker.sent == ["alpha"]
    session.close()
    session.close()
    idempotent = tracker.close_calls == 1
    rejected = False
    try:
        session.send("late")
    except RuntimeError:
        rejected = True
    context_tracker = CloseTracker()
    context_session = module.ManagedSession(context_tracker)
    returned = False
    try:
        with context_session as entered:
            returned = entered is context_session
            raise LookupError("exercise exceptional exit")
    except LookupError:
        pass
    cases = (
        ("send-delegates", delegated),
        ("close-idempotent", idempotent),
        ("send-after-close", rejected),
        ("context-returns-self", returned),
        ("exceptional-exit-closes", context_tracker.close_calls == 1 and context_session.closed),
    )
    checks = [
        {"name": name, "passed": passed, "score": 1.0 if passed else 0.0} for name, passed in cases
    ]
    print(
        json.dumps(
            {
                "schema_version": 1,
                "passed": all(value for _, value in cases),
                "score": sum(item["score"] for item in checks) / len(checks),
                "checks": checks,
                "summary": "managed session lifecycle cases",
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
