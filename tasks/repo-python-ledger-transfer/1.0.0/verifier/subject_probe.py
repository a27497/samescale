from __future__ import annotations

import sys
import tempfile
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path


def run_case(workspace: Path, check: Callable[[object, object, Path], bool]) -> bool:
    sys.path.insert(0, str(workspace))
    try:
        from ledger import LedgerRepository, LedgerService

        with tempfile.TemporaryDirectory(prefix="ledger-contract-") as temporary:
            database = Path(temporary) / "ledger.db"
            repository = LedgerRepository(database)
            repository.create_account("alice", 100)
            repository.create_account("bob", 20)
            try:
                return bool(check(repository, LedgerService(repository), database))
            finally:
                repository.close()
    finally:
        sys.path.pop(0)


def run(workspace: Path) -> dict[str, object]:
    def success(repository: object, service: object, _database: Path) -> bool:
        result = service.transfer("r1", "alice", "bob", 30)
        return (
            result.amount == 30
            and repository.balance("alice") == 70
            and repository.balance("bob") == 50
            and repository.transfer_count() == 1
        )

    def replay(repository: object, service: object, _database: Path) -> bool:
        service.transfer("r1", "alice", "bob", 30)
        result = service.transfer("r1", "alice", "bob", 30)
        mismatch = False
        try:
            service.transfer("r1", "alice", "bob", 31)
        except ValueError:
            mismatch = True
        return (
            result.replayed
            and mismatch
            and repository.balance("alice") == 70
            and repository.transfer_count() == 1
        )

    def rollback(repository: object, service: object, _database: Path) -> bool:
        with suppress(RuntimeError):
            service.transfer("broken", "alice", "bob", 30, fail_after_debit=True)
        return (
            repository.balance("alice") == 100
            and repository.balance("bob") == 20
            and repository.transfer_count() == 0
        )

    def durable(repository: object, service: object, database: Path) -> bool:
        service.transfer("r1", "alice", "bob", 30)
        repository.close()
        from ledger import LedgerRepository

        reopened = LedgerRepository(database)
        try:
            return (
                reopened.balance("alice") == 70
                and reopened.balance("bob") == 50
                and reopened.find_transfer("r1") is not None
            )
        finally:
            reopened.close()

    def validation(repository: object, service: object, _database: Path) -> bool:
        rejected = 0
        for arguments in (
            ("x", "alice", "alice", 1),
            ("y", "missing", "bob", 1),
            ("z", "alice", "bob", 0),
            ("q", "alice", "bob", 1000),
        ):
            try:
                service.transfer(*arguments)
            except (ValueError, LookupError):
                rejected += 1
        return (
            rejected == 4
            and repository.balance("alice") == 100
            and repository.transfer_count() == 0
        )

    cases = (
        ("atomic-success", success),
        ("idempotent-replay", replay),
        ("rollback-on-failure", rollback),
        ("durable-reopen", durable),
        ("validation-preserves-state", validation),
    )
    values = [(name, run_case(workspace, check)) for name, check in cases]
    checks = [
        {"name": name, "passed": passed, "score": 1.0 if passed else 0.0} for name, passed in values
    ]
    return {
        "schema_version": 1,
        "passed": all(passed for _, passed in values),
        "score": sum(item["score"] for item in checks) / len(checks),
        "checks": checks,
        "summary": "SQLite transfer repository contract",
    }
