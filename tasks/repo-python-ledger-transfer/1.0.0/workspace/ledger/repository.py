from __future__ import annotations

import sqlite3
from pathlib import Path

from ledger.models import TransferResult


class LedgerRepository:
    def __init__(self, database: Path) -> None:
        self.connection = sqlite3.connect(database)
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS accounts (id TEXT PRIMARY KEY, balance INTEGER NOT NULL)"
        )
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS transfers (
                request_id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                target TEXT NOT NULL,
                amount INTEGER NOT NULL
            )"""
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def create_account(self, account_id: str, balance: int) -> None:
        self.connection.execute(
            "INSERT INTO accounts(id, balance) VALUES (?, ?)", (account_id, balance)
        )
        self.connection.commit()

    def balance(self, account_id: str) -> int | None:
        row = self.connection.execute(
            "SELECT balance FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
        return None if row is None else int(row[0])

    def debit(self, account_id: str, amount: int) -> None:
        self.connection.execute(
            "UPDATE accounts SET balance = balance - ? WHERE id = ?", (amount, account_id)
        )
        self.connection.commit()

    def credit(self, account_id: str, amount: int) -> None:
        self.connection.execute(
            "UPDATE accounts SET balance = balance + ? WHERE id = ?", (amount, account_id)
        )
        self.connection.commit()

    def find_transfer(self, request_id: str) -> TransferResult | None:
        row = self.connection.execute(
            "SELECT source, target, amount FROM transfers WHERE request_id = ?", (request_id,)
        ).fetchone()
        if row is None:
            return None
        return TransferResult(request_id, str(row[0]), str(row[1]), int(row[2]), replayed=True)

    def record_transfer(self, result: TransferResult) -> None:
        self.connection.execute(
            "INSERT INTO transfers(request_id, source, target, amount) VALUES (?, ?, ?, ?)",
            (result.request_id, result.source, result.target, result.amount),
        )
        self.connection.commit()

    def transfer_count(self) -> int:
        row = self.connection.execute("SELECT COUNT(*) FROM transfers").fetchone()
        return int(row[0])
