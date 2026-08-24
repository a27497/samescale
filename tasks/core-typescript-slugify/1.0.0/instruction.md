# Repair event subscription disposal

Implement `Subscription`: the constructor subscribes exactly once and forwards events while
active. `dispose()` is idempotent, calls the returned unsubscribe function exactly once, and stops
forwarding even if the source later invokes its retained callback. If subscribing throws, propagate
the error without invoking the handler. Preserve `contract.txt`.
