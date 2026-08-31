# K-B3 V6 Alibaba real-preflight and canary control

The V6 canary control is separate from both historical V5 authority and the future 630-slot V6
Matrix. It can authorize only these top-level launches, in order:

1. Direct Qwen3.8 Max through Alibaba OpenAI-compatible Chat Completions.
2. Claude Code plus Qwen3.8 Max through Alibaba Anthropic-compatible Messages.
3. The preferred GLM-5.2 Alibaba Judge on the frozen `label-l0-pass` public case.

The structural limits are three primary launches and at most 18 provider requests: one Direct
request, up to 16 Claude/Qwen requests under `--max-turns 16`, and one Judge request. The Claude
launch also sets `CLAUDE_CODE_MAX_OUTPUT_TOKENS=2000`, bounding output per request. Retries,
semantic retries, and substitutions are zero, and Matrix acquisition is forbidden. A launch marker
is persisted before each primary launch. If a process ends after that marker but before terminal
per-call evidence, resume hard-stops because the launch may already have spent and the retry budget
is zero.

## Operator inputs

Copy `release/core-real-matrix-v6-operator-inputs.template.json` to a private or operator-owned
location and complete every field. Values are non-secret. `cache_or_batch_adjustments`,
`account_specific_promotions`, `tax_treatment`, and `fx_treatment` require an explicit statement;
`UNKNOWN`, `UNCONFIRMED`, `TBD`, `NOT_AVAILABLE`, and `N/A` remain blocked. Pricing is never
converted to zero. The frozen public rates apply to the Aliyun China-site China (Beijing) PAYG
account class and require `billing_currency` to be `CNY`.

The process environment must provide these values without writing them into an artifact:

- `HARNESSLAB_ALIBABA_BAILIAN_OPENAI_BASE_URL`
- `HARNESSLAB_ALIBABA_BAILIAN_ANTHROPIC_BASE_URL`
- `HARNESSLAB_ALIBABA_BAILIAN_API_KEY`
- `HARNESSLAB_ALIBABA_BAILIAN_QWEN38_MODEL_ID=qwen3.8-max`
- `HARNESSLAB_ALIBABA_BAILIAN_GLM52_MODEL_ID=glm-5.2`

Endpoint values must be canonical HTTPS Alibaba China (Beijing) workspace URLs with the frozen
OpenAI and Anthropic paths. Both must have the same hostname. Receipts retain only endpoint and
workspace SHA-256 fingerprints, configuration-reference names, and credential presence.

## Preflight and authorization

Run the local preflight without any provider call:

```console
harnesslab release v6-canary preflight \
  --operator-inputs /private/operator-v6-inputs.json \
  --receipt-root artifacts/core-real-matrix-v6-canary-control
```

The command checks frozen source/control digests, Alibaba endpoint classes and shared workspace,
credential presence, exact deployed model IDs, registry and Harness bindings, subject and Judge
workloads, all pricing/account confirmations, Docker, isolated egress, pinned images, and the fixed
8-vCPU/nominal-16-GB-class production-host floor (`16000000000` bytes). It writes a
content-addressed immutable receipt even when blocked and always reports zero provider,
Harness-provider, and Judge calls.

After a `READY` receipt, copy
`release/core-real-matrix-v6-canary-authorization-request.template.json` to an operator-owned
location and replace its identifiers, timestamp, and the two zero-digest placeholders. The strict
`V6CanaryAuthorizationRequest` must
bind the receipt digest and canary-plan digest, use scope
`CORE_REAL_MATRIX_V6_THREE_CALL_CANARY`, set `spend_authorized` and `allow_real_canary` to true,
bind limits of 3 primary launches, 18 provider requests, and 16 Claude Harness turns, and retain
the literal zero retry/substitution and false Matrix fields. Issue the receipt with:

```console
harnesslab release v6-canary authorize \
  --preflight-receipt /path/to/preflight-receipt.json \
  --authorization-request /private/v6-canary-authorization-request.json
```

V5 objects fail schema validation. The V6 canary receipt also fails the disjoint
`V6MatrixAuthorizationReceipt` schema. Matrix dispatch requires that separate scope, all 630
slots, pricing/spend authority, and Profile C execution identity
`sha256:85117b2577f3456e0df573ed2467d19dee64bebca748e178bd92017dea6133b7`.
Profile A and Profile B receipts fail closed. The canary remains independent and does not bind or
depend on throughput-profile authorization.

## Planning cost basis

At the frozen standard non-cache CNY rates, the planning-envelope projections are CNY `0.465216`
for Direct Qwen, CNY `0.465216` for the historical Claude/Qwen envelope, and CNY `0.072704` for the
GLM Judge, totaling CNY `1.003136`. This is
`PLANNING_ESTIMATE_NOT_HARD_BILLING_CEILING`: aggregate Claude input-token usage is not hard-capped
by the CLI. Executable safety instead comes from the 3-primary-launch / at-most-18-provider-request
structure, the 16-turn Claude cap, per-request output cap, timeouts, fixed workloads/models/routes,
and zero retries or substitutions. A future operator must still explicitly authorize spend; this
control does not impose or claim a hard CNY billing ceiling.

## Future execution

Only after explicit authorization, execution uses all three files and the dedicated flag:

```console
harnesslab release v6-canary execute \
  --allow-real-v6-canary \
  --operator-inputs /private/operator-v6-inputs.json \
  --preflight-receipt /path/to/preflight-receipt.json \
  --authorization-receipt /path/to/authorization-receipt.json
```

Execution recomputes the full local preflight and requires byte-equivalent receipt facts before
call one. Per-call evidence and the concise closeout are immutable. GLM-5.2 remains
`PROVISIONAL_PENDING_REAL_CANARY` unless all three primary launches, including exact observed Judge
model and strict public JSON parsing, succeed. This control-plane implementation does not itself
authorize or execute the canary.
