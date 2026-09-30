from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from harnesslab.evidence.protection import FrozenEvidenceGuard, snapshot_tree

ROOT = Path(__file__).resolve().parents[1]


def assert_disposable_database(value: str, environment: str) -> None:
    """Never let cleanup fixtures run against business, historical, or demo databases."""
    name = urlsplit(value).path.strip("/").lower()
    if any(part in name for part in ("public", "demo", "qa", "live", "historical", "production")):
        raise pytest.UsageError(
            "Refusing tests against a protected database; use an isolated disposable test database"
        )
    if environment != "test" and "test" not in name:
        raise pytest.UsageError(
            "Tests require HARNESSLAB_ENVIRONMENT=test and a disposable database"
        )


def pytest_sessionstart(session: pytest.Session) -> None:
    value = os.environ.get("DATABASE_URL")
    if value:
        assert_disposable_database(value, os.environ.get("HARNESSLAB_ENVIRONMENT", ""))


@pytest.fixture
def database_url() -> str:
    value = os.environ.get("DATABASE_URL")
    if not value:
        pytest.fail("DATABASE_URL is required for Gate A database tests")
    assert_disposable_database(value, os.environ.get("HARNESSLAB_ENVIRONMENT", ""))
    return value


@pytest.fixture(scope="session", autouse=True)
def frozen_evidence_guard() -> Iterator[None]:
    roots = [ROOT / "release", ROOT / "docs/evidence", ROOT / "docs/recruiter"]
    roots.extend(
        Path(value)
        for value in json.loads(os.environ.get("HARNESSLAB_PROTECTED_EVIDENCE_ROOTS", "[]"))
    )
    roots = [root.resolve() for root in roots if root.exists()]
    before = {str(root): snapshot_tree(root) for root in roots}
    guard = FrozenEvidenceGuard(tuple(roots))
    guard.install()
    try:
        yield
    finally:
        guard.active = False
        after = {str(root): snapshot_tree(root) for root in roots}
        result = {
            "before_file_count": sum(len(v) for v in before.values()),
            "after_file_count": sum(len(v) for v in after.values()),
            "before": before,
            "after": after,
            "equal": before == after,
        }
        output = os.environ.get("HARNESSLAB_INTEGRITY_TEST_REPORT")
        if output:
            Path(output).write_text(json.dumps(result, indent=2) + "\n")
        assert before == after, "frozen/public-demo evidence changed during the test suite"
