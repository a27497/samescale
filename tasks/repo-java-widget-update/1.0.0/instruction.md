# Implement optimistic widget updates

Finish the existing update flow across API, service, and repository. A successful update must
increment the stored version exactly once. A stale `expectedVersion` must return conflict without
mutating persistence. Missing widgets return not-found, and blank names return bad-request before
the repository is changed. Keep the existing public records and method signatures, preserve
unrelated widgets, and do not modify `contract.md`.

The snapshot is intentionally build-tool-free: use Java 21 and do not add network dependencies.
