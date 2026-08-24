# Preserve first-seen event order

Fix `deduplicate` so repeated identifiers are removed while the first-seen order is preserved.
Return a new array, keep the typed API unchanged, add no dependencies, and do not modify
`contract.txt`.
