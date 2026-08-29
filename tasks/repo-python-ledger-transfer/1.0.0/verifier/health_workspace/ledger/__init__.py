from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TransferResult:
    request_id: str
    source: str
    target: str
    amount: int
    replayed: bool = False


class LedgerRepository:
    def __init__(self, database: Path) -> None:
        self.connection = sqlite3.connect(database)
        self.connection.executescript(
            "CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY,balance INTEGER NOT NULL); CREATE TABLE IF NOT EXISTS transfers(request_id TEXT PRIMARY KEY,source TEXT,target TEXT,amount INTEGER);"
        )
        self.connection.commit()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.connection.rollback()
            raise
        else:
            self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def create_account(self, account_id: str, balance: int) -> None:
        self.connection.execute("INSERT INTO accounts VALUES(?,?)", (account_id, balance))
        self.connection.commit()

    def balance(self, account_id: str) -> int | None:
        row = self.connection.execute(
            "SELECT balance FROM accounts WHERE id=?", (account_id,)
        ).fetchone()
        return None if row is None else int(row[0])

    def debit(self, account_id: str, amount: int) -> None:
        self.connection.execute(
            "UPDATE accounts SET balance=balance-? WHERE id=?", (amount, account_id)
        )

    def credit(self, account_id: str, amount: int) -> None:
        self.connection.execute(
            "UPDATE accounts SET balance=balance+? WHERE id=?", (amount, account_id)
        )

    def find_transfer(self, request_id: str) -> TransferResult | None:
        row = self.connection.execute(
            "SELECT source,target,amount FROM transfers WHERE request_id=?", (request_id,)
        ).fetchone()
        return (
            None
            if row is None
            else TransferResult(request_id, str(row[0]), str(row[1]), int(row[2]), True)
        )

    def record_transfer(self, result: TransferResult) -> None:
        self.connection.execute(
            "INSERT INTO transfers VALUES(?,?,?,?)",
            (result.request_id, result.source, result.target, result.amount),
        )

    def transfer_count(self) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM transfers").fetchone()[0])


class LedgerService:
    def __init__(self, repository: LedgerRepository) -> None:
        self.repository = repository

    def transfer(
        self,
        request_id: str,
        source: str,
        target: str,
        amount: int,
        *,
        fail_after_debit: bool = False,
    ) -> TransferResult:
        if not request_id or amount <= 0 or source == target:
            raise ValueError("invalid transfer")
        with self.repository.transaction():
            previous = self.repository.find_transfer(request_id)
            if previous:
                if (previous.source, previous.target, previous.amount) != (source, target, amount):
                    raise ValueError("payload mismatch")
                return previous
            balance = self.repository.balance(source)
            if balance is None or self.repository.balance(target) is None:
                raise LookupError("missing")
            if balance < amount:
                raise ValueError("insufficient")
            self.repository.debit(source, amount)
            if fail_after_debit:
                raise RuntimeError("simulated")
            self.repository.credit(target, amount)
            result = TransferResult(request_id, source, target, amount)
            self.repository.record_transfer(result)
            return result
