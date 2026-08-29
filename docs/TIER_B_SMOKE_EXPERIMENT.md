# Tier-B keyless smoke experiment

This branch preregisters a six-slot readiness smoke for the qualified Tier-B repo-engineering
corpus. It does not authorize or execute provider acquisition.

## Frozen design

- Experiment: `tier-b-keyless-smoke-v1`
- Intent and mode: `MODEL_COMPARISON`, `QUICK`, one repeat
- Schedule: `BLOCKED_INTERLEAVED_SCHEDULING`, seed `20260831`
- Matrix: three Tier-B tasks by two Direct M-Lane model cells (`Qwen3.8 Max` and
  `DeepSeek V4 Pro`)
- Qualification: `tier-b-repo-engineering-v1`, digest
  `sha256:d3b9bb8512de9b6e847c0daf93b75049e6e99737e4bdcd47ad8c0dd217e01a88`
- Plan digest:
  `sha256:7c05ba81e67fba6df388c4511bf0ba7df5a84b07aaf5e27baa2a1b61e886186e`

The two cells share the existing Direct resource envelope: one provider request, one model turn,
zero tools, 4,000 maximum output tokens, 180-second provider timeout, and 240-second logical wall
limit. The envelope was not enlarged. The largest frozen workspace is under 5 KiB and the largest
rendered Direct prompt is under 7 KiB, well inside the current Direct prompt limits.

## Endpoint boundary

Endpoint binding is `PENDING_OPERATOR_ENDPOINT_RECONCILIATION`. The keyless freeze deliberately
contains only the protected environment reference and no endpoint URL or endpoint fingerprint.
The blocked endpoint preflight is expected and is the only blocked preflight class.

Do not enqueue or execute this plan until both conditions hold:

1. The B+C integration base has landed on `main`.
2. The operator endpoint has been reconciled, re-frozen through the registry machinery, and the
   resulting endpoint fingerprint has passed identity review.

Endpoint reconciliation will necessarily create a new immutable plan digest. Preserve this
keyless plan as the preregistered non-endpoint-control baseline; do not edit it in place.

## Failure and evidence semantics

Capability pass and capability fail are both acceptable smoke results. Capability failure is
terminal with no retry. Infrastructure failure preserves the immutable first attempt and does not
permit an immediate semantic retry. There is no score-based stop.

The preregistration binds task, snapshot, verifier, qualification, schedule, runtime, and resource
identities. Later evidence must expose the repository input snapshot, parsed changed-file identity,
workspace output identity, language, engineering shape, Tier-B identity, qualification digest,
capability-versus-infrastructure classification, and latency/usage when the provider reports them.
Scores, costs, and provider observations remain `NOT_AVAILABLE` in this keyless planning phase.

## Keyless verification

Run the qualification check and frozen-plan check through the pinned environment:

```console
uv run --locked python scripts/qualify_tier_b.py --check
uv run --locked python scripts/freeze_tier_b_smoke.py --check
```

The canonical artifacts are `release/tier-b-smoke-keyless-plan.json` and
`release/tier-b-smoke-preregistration.json`.
