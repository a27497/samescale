# Repair canonical pagination cursors

Implement `parseCursor` for the exact `<offset>@<anchor>` form. Offset must be a non-negative safe
integer in canonical decimal form (`0` or no leading zeroes). Anchor must be non-empty URL-safe
base64 text (`A-Z`, `a-z`, `0-9`, `_`, `-`). Throw `TypeError` for malformed cursors. Preserve
`contract.txt`.
