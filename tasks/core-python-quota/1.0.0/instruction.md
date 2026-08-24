# Fix quota consumption lifecycle

Correct `Quota.consume`: a positive request succeeds when enough units remain, including an exact
boundary match, and decrements state only on success. Zero or negative requests must raise
`ValueError`. Preserve the public API and `contract.txt`.
