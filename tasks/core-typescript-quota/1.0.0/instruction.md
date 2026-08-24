# Repair capped exponential retry scheduling

Implement `retryDelays(attempts, baseMs, capMs)`. Return one delay before each retry (therefore
`attempts - 1` values): `baseMs`, doubling each time, saturated at `capMs` without overflow.
Arguments must be safe integers with attempts >= 1 and 1 <= baseMs <= capMs; otherwise throw
`RangeError`. Preserve `contract.txt`.
