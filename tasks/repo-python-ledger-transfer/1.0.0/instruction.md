# Repair the ledger transfer workflow

The SQLite-backed ledger has a production regression: interrupted transfers can commit only the
debit, and repeated request IDs are not safely handled inside the same transaction.

Repair the repository and service so a transfer is atomic, durable after reopening the database,
and idempotent by `request_id`. A failed transfer must leave both balances and the transfer log
unchanged. Reject non-positive amounts, missing accounts, self-transfers, and insufficient funds.
Preserve the public API and do not modify `contract.md` or `tests/test_public.py`. The repository is
offline and must continue to use only the Python standard library.
