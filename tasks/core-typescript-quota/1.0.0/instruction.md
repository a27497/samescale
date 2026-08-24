# Fix quota consumption lifecycle

Correct `Quota.consume`: positive requests succeed when enough units remain, including an exact
boundary, and state changes only on success. Zero or negative requests throw `RangeError`. Preserve
the public API and `contract.txt`.
