from __future__ import annotations

from ledger.models import TransferResult
from ledger.repository import LedgerRepository


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
        if not request_id:
            raise ValueError("request_id is required")
        if amount <= 0:
            raise ValueError("amount must be positive")
        if source == target:
            raise ValueError("source and target must differ")
        with self.repository.transaction():
            previous = self.repository.find_transfer(request_id)
            if previous is not None:
                if (previous.source, previous.target, previous.amount) != (source, target, amount):
                    raise ValueError("request_id payload mismatch")
                return previous
            source_balance = self.repository.balance(source)
            if source_balance is None or self.repository.balance(target) is None:
                raise LookupError("account not found")
            if source_balance < amount:
                raise ValueError("insufficient funds")
            self.repository.debit(source, amount)
            if fail_after_debit:
                raise RuntimeError("simulated interruption")
            self.repository.credit(target, amount)
            result = TransferResult(request_id, source, target, amount)
            self.repository.record_transfer(result)
            return result
