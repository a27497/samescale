# Repair discriminated request validation

Implement `validateRequest(input)`. A `read` request has exactly `kind` and a non-empty string
`key`; a `write` request additionally has an own `value` property (whose value may be `null`).
Reject arrays, inherited fields, extra keys, blank keys, and every other shape with `TypeError`.
Return a fresh request object and preserve `contract.txt`.
