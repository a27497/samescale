# K-B3 V6 integration certification

This phase integrates the independently verified V6 throughput R2 and three-call canary-control
lanes without changing either lane's scientific semantics. Git history preserves both source
heads. The append-only receipt is
`release/core-real-matrix-v6-integration-certification.json`.

The authoritative formal Matrix path uses only `V6_PROFILE_C_C6_H3`, whose execution-profile
identity is
`sha256:85117b2577f3456e0df573ed2467d19dee64bebca748e178bd92017dea6133b7`.
Dispatch requires a valid `V6MatrixAuthorizationReceipt` for the frozen plan, all 630 slots,
pricing and spend authority, and that exact Profile C identity. Missing authorization, invalid
receipt digests, and Profile A or Profile B bindings fail before queue acquisition.

The preregistered canary remains a separate three-call control plane. Its authorization cannot be
used for Matrix dispatch, it does not require throughput-profile authorization, and it retains
zero retries, semantic retries, and substitutions. Judge remains
`PROVISIONAL_PENDING_REAL_CANARY`; this phase performs no provider, Harness-provider, Judge,
canary, or Matrix call.

The receipt's `certified_head_binding` value `CONTAINING_GIT_COMMIT` means the certified object is
the final Git commit containing the receipt bytes. The returned exact head and receipt SHA-256
together provide the non-circular binding: Git binds the receipt bytes into the commit, while the
receipt binds both verified lane heads and all frozen control identities.
