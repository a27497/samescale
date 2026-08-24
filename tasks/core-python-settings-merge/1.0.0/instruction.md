# Repair managed session lifecycle

Fix `ManagedSession` so `send` delegates while open and raises `RuntimeError` after closing.
`close` must be idempotent and close the transport exactly once. The context manager must return
the session and close it on both normal and exceptional exit. Keep both modules and `contract.txt`.
