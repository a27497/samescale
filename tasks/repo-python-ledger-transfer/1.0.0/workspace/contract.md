# Public contract

`LedgerService.transfer(request_id, source, target, amount, fail_after_debit=False)` returns a
`TransferResult`. Request IDs are idempotency keys. All account and transfer-log writes are one
SQLite transaction; any exception rolls them all back.
