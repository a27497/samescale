# Preserve first-seen event order

Fix `Events.deduplicate` so duplicate identifiers are removed without sorting; the first occurrence
defines output order. Return a new mutable list and keep the Java 21 API unchanged. Do not modify
`contract.txt`.
