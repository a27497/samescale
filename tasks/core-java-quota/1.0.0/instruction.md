# Fix quota consumption lifecycle

Correct `Quota.consume`: positive requests succeed when enough units remain, including the exact
boundary, and state changes only on success. Zero or negative requests throw
`IllegalArgumentException`. Keep the API and `contract.txt` unchanged.
