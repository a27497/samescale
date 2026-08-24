# Repair idempotent retry recording

Fix `events.RetryLedger.record_success`. The first result for a non-empty operation key is stored
and returns `True`; an identical retry returns `False` without changing state; a retry with a
different result raises `ValueError` and preserves the original. Keep `lookup` and `contract.txt`.
