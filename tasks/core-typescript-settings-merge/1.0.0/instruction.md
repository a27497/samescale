# Repair recursive JSON secret redaction

Implement `redact(value)` to deeply copy JSON-compatible objects and arrays while replacing values
whose keys case-insensitively match the configured sensitive keys with `[REDACTED]`. Preserve array
holes as holes, do not mutate input, preserve primitive values, and reject circular structures with
`TypeError`. Keep both modules and `contract.txt`.
