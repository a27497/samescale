# Preserve first-seen event order

Fix `events.deduplicate` so it removes repeated event identifiers while preserving the first-seen
order. Inputs are strings and must not be sorted. Keep the function signature unchanged and do not
modify `contract.txt`.
