# Repair collection batch partitioning

Implement `Slug.partition(values, size)` to preserve order and return consecutive batches of at
most `size`. Reject non-positive sizes. Both the outer list and every batch must be new mutable
lists, and later mutations of the input must not change them. Preserve `contract.txt`.
