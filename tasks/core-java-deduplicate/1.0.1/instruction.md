# Repair the length-prefixed record codec

Implement `Events.encode` and `Events.decode` using the exact `<length>#<payload>` format. Payloads
may be empty or contain `#`. Decode must reject a missing delimiter, a signed or non-decimal length,
and any payload whose Java character length differs from its prefix. Preserve `contract.txt`.
