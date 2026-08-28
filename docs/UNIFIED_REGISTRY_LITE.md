# Unified Registry Lite

Unified Registry Lite is the backend-authoritative planning control plane for new
Methodology-v2 evaluations. It is intentionally smaller than full run-control productization:
it manages safe identities, derives compatibility, performs keyless preflight, and freezes
immutable experiment snapshots. It does not invoke a provider, Harness, Judge, smoke, or worker.

`ALIBABA_BAILIAN=CONFIGURED_KEYLESS`. This is not real-provider verification.

## Registry contracts

The Provider Registry seeds `gpt56-relay`, `opencode-go`, `deepseek-official`, and
`alibaba-bailian`. Responses contain safe provider identity, endpoint class, region, protocols,
billing mode, credential-reference name, status, capabilities, pricing-snapshot reference, and a
one-way runtime-endpoint fingerprint where required. They never contain credential values,
Authorization headers, raw provider responses, private reasoning, protected relay URLs, or an
Alibaba WorkspaceId URL.

The Model Registry is separate from Provider Registry. A `ModelDefinition` describes the logical
model; a `ProviderModelProfile` binds that model to a specific provider, requested model string,
protocol, safe route identity, credential reference, generation controls, and immutable profile
identity. Changing provider changes the treatment identity even when the logical model ID is the
same.

Alibaba model availability is never inferred. Operator-configured IDs come only from
`HARNESSLAB_ALIBABA_BAILIAN_MODEL_IDS`. Until that reference supplies valid explicit IDs, the
provider reports `CONFIGURED_MODEL_ID_REQUIRED` and no Alibaba model profile exists.

The Harness Registry derives its built-in identities from the canonical Direct, Codex, Claude
Code, and DeepSeek runtime/profile constants. It publishes version/image references, profile
identities, protocol support, tool surface, trace coverage, observed-model exposure, network/MCP
capability, workspace mutation, and runtime health. Vue does not recreate Harness configuration.

The Capability Registry evaluates every `ProviderModelProfile × HarnessProfile` pair and returns
`SUPPORTED`, `PARTIALLY_SUPPORTED`, or `UNSUPPORTED` with reason codes. Explicit protocol and
profile allowlists are required; unknown combinations fail closed. The facts include observed
model availability, `FULL_STREAM` versus `FINAL_OUTPUT_ONLY`, native tools, workspace mutation,
network requirements, reasoning controls, Harness-uplift eligibility, and Judge eligibility.

## Alibaba Bailian contract

The built-in Alibaba provider is fixed to:

- provider: `alibaba-bailian`
- region: `cn-beijing`
- endpoint class: `WORKSPACE_DEDICATED`
- protocols: OpenAI-compatible Chat Completions and Responses
- base URL reference: `HARNESSLAB_ALIBABA_BAILIAN_BASE_URL`
- credential reference: `HARNESSLAB_ALIBABA_BAILIAN_API_KEY`
- billing: `PAY_AS_YOU_GO`
- automation: allowed only under PAYG

The runtime URL must resolve keylessly to the `cn-beijing.maas.aliyuncs.com` workspace domain with
the `/compatible-mode/v1` path. Only a SHA-256 fingerprint is retained in a resolved treatment
identity. The raw URL and WorkspaceId never enter the API, snapshot, or tracked evidence. Chat
uses `/chat/completions`; Responses uses `/responses`. Local MockTransport tests prove request
shape, reference-only Bearer authentication, requested/observed model separation, and provider
identity without making an internet call.

`CODING_PLAN` and personal `TOKEN_PLAN` are invalid automated-evaluation billing selections.
Preflight blocks them with `AUTOMATION_NOT_ALLOWED_FOR_BILLING_PLAN`; it does not call Alibaba to
establish that policy.

## Settings and runtime status

Settings Lite is read-only for secrets. It shows default profile, mode, schedule seed,
concurrency, cost preference, provider enabled state, and credential status as `SET` or `MISSING`.
There is no browser secret-writing endpoint.

Provider availability is operator supplied through status references and is one of `AVAILABLE`,
`UNAVAILABLE`, `QUOTA_EXHAUSTED`, or `UNKNOWN`. No provider is probed automatically.
`UNAVAILABLE` and `QUOTA_EXHAUSTED` block affected new work; `UNKNOWN` remains a visible warning.
Status changes never rewrite an existing snapshot or experiment treatment identity.

## Experiment Builder and immutable snapshots

The Builder accepts only registered methodology, task, ProviderModelProfile, and HarnessProfile
IDs. It accepts no URL, filesystem path, shell command, CLI argv, Docker option, or Authorization
header. Methodology v2 fixes `QUICK=n1`, `INFORMAL=n3`, and `FORMAL_EXHAUSTIVE=n5`; the browser
cannot submit a repeat count. Comparison claims are backend-classified, budget contracts are
strict, task health runs five deterministic baseline/oracle repetitions, and schedules are built
by `BLOCKED_INTERLEAVED_SCHEDULING`.

The immutable snapshot contains the methodology ID/digest, exact task and treatment identities,
provider/model/Harness profiles, budget, credential references, safe routes, runtime endpoint
fingerprints, pricing references, schedule seed, blocks, and logical slots. A provider URL,
profile, model, or Harness change produces a new identity. Snapshot persistence is append-only and
idempotent; it inserts no `experiment`, `experiment_run`, or queue row. Live status changes return
the already-frozen snapshot instead of mutating it.

PostgreSQL migration `20260828_0005` adds only `registry_experiment_snapshot`. Built-in registry
definitions remain deterministic version-controlled backend contracts; browser/localStorage is
never configuration authority.

## Preflight

`POST /api/experiments/preflight` returns exactly `READY`, `READY_WITH_WARNINGS`, or `BLOCKED`.
Checks cover methodology identity, task health, profile validity, Harness compatibility,
credential presence, provider enablement/status, billing permission, protocol/route configuration,
budget completeness, comparison controls, blocked/interleaved schedule validity, logical slot
count, maximum wall-time bound, and pricing availability. Pricing without immutable price/input
evidence remains `COST_ESTIMATE=NOT_AVAILABLE`; planning metadata never retroactively prices
historical evidence.

## API inventory

- `GET /api/registry/providers`
- `GET /api/registry/models`
- `GET /api/registry/harnesses`
- `GET /api/registry/capabilities`
- `GET /api/registry/settings`
- `GET /api/registry/tasks`
- `GET /api/registry/methodologies`
- `POST /api/experiments/preflight`
- `POST /api/experiments/snapshot`
- `GET /api/experiments/snapshots/{snapshot_id}`

The Vue Workbench routes are `/models`, `/providers`, `/harnesses`, `/capabilities`, `/settings`,
and `/experiments/new`. Existing evidence, experiment, run, JudgeLab, and Regression pages remain
unchanged. There is no Registry execution endpoint.

## Historical boundary

`core-real-matrix-v3` remains historical schema-v1/Formal Exhaustive evidence with 630 logical
slots, 177 terminal observations, and 453 queued slots. Registry Lite neither imports it as a new
Methodology-v2 experiment nor rewrites its plan, database rows, representative view, or v1/v2/v3
release history. Existing Workbench evidence pages continue reading it through their original
contracts.
