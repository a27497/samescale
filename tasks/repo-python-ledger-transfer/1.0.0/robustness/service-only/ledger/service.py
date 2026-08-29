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
        with self.repository.transaction():
            previous = self.repository.find_transfer(request_id)
            if previous is not None:
                return previous
            self.repository.debit(source, amount)
            if fail_after_debit:
                raise RuntimeError("simulated interruption")
            self.repository.credit(target, amount)
            result = TransferResult(request_id, source, target, amount)
            self.repository.record_transfer(result)
            return result
