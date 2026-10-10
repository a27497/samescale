# ChatGPT subscription execution preparation — Phase 2.5

**Real execution remains closed.** This delivery implements and verifies offline preparation.
It makes no account-entitlement, available-quota or live-inference claim. No real credential bytes,
login directory, token refresh, account RPC, model/catalog request or paid inference was used.
`REAL_CODEX` is unconditionally denied before plan lookup/queue insertion. No environment toggle
opens it. API keys, API billing and USD hard caps are not subscription prerequisites.

## Authentication and frozen compatibility

The server development CLI is 0.160.1. A sanitized local `login status` check reports ChatGPT;
configuration selects built-in OpenAI / Responses without a custom profile or API-key environment.
This establishes local selection, not server access, route health, entitlement or quota. Authentication
store contents were not read by the check and login/logout was not invoked.

The product Runner remains frozen at 0.149.0, with the existing opt-in 0.153.4 profile. Existing local
images were inspected; both binaries reported their pinned version under network-none Docker.
Locally generated schemas for these versions and the development CLI declare externally managed
ChatGPT tokens, rate-limit reads and turn interruption. No such RPC was sent. The offline Worker
uses **0.149.0**, not the development binary; no image was built, pulled or upgraded.

[Official authentication documentation](https://learn.chatgpt.com/docs/auth) distinguishes ChatGPT
subscription access from API billing and documents sensitive cached authentication.
[App-server documentation](https://learn.chatgpt.com/docs/app-server) exposes externally managed auth,
quota observations and interruption; successful refresh can retry a request. These interfaces alone
prove neither credential isolation nor an enforceable request ceiling.
[Plan-usage preview limitations](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations)
exclude output-token and tool-call cap parameters. Treat version-specific support and the intended
subscription route as unverified until admitted; do not substitute an API-key route.

## Trusted control boundary

The existing real backend supplies credentials inside the Codex/Subject container. Shell environment
filtering does not protect them from every tool, `/proc`, native process access or runtime state.
The existing CONNECT proxy is TLS pass-through: it cannot inject subscription authentication or count
individual encrypted Responses requests. Mounting `~/.codex`, copying `auth.json`, injecting account
bearers into Subject environment, or passing tokens through app-server inside Subject are disallowed.

The offline implementation separates a trusted controller from Subject in different containers,
PID and mount namespaces. Both have network-none isolation; Subject shares only the controller's
network namespace to reach one loopback HTTP/SSE endpoint. Controller mounts contain fixed code,
non-secret policy and safe counter receipts. Subject receives only Workspace; Verifier receives
only readonly final Workspace and hidden verifier. Neither receives controller mounts, login assets,
Docker socket, keys, tokens or host auth environment. Actual Codex tool execution checks hidden-asset,
credential/environment/proc isolation and network syscall denial before writing the fixture solution.

Controller credentials are fresh **synthetic in-memory canaries**, never actual account tokens.
The transport is an in-process protocol double with no outbound network, credential loader, refresh,
login or purchase implementation. The controller does not log bodies/headers/raw exceptions.
No raw native reasoning is retained. Normalized Trace and independent Verifier reuse the H-Lane.
All protocol results remain `FAKE_CODEX / CUSTOM / synthetic / NOT_ATTESTED` with zero model calls.
They do not qualify the separate real engineering task or establish live authentication security.

## Controls and evidence

`SubscriptionLimits` freezes one physical attempt, one turn, wall timeout, maximum Responses requests,
zero automatic retries and no additional-credit purchase. Client confirmation must match the exact
operator policy as well as plan, slot, frozen budget and application identities. The existing queue,
row locking, lease, file lock, cleanup, cancellation and append-only result ledger are reused.
The controller debits and fsyncs before its protocol transport; request failure is never refunded.
A pre-existing controller journal refuses restart/reset. Responses must match the frozen model and
route; auth failure, exhausted quota, protocol errors or deadline close the controller. Frozen CLI
request/stream retries are configured to zero and actual inbound counts verify behavior.

| Limit or observation | Scope |
| --- | --- |
| Physical attempt and one CLI turn | Existing durable queue + a single ephemeral exec; never redispatched |
| Request count | Hard bound at the **offline controller**; not yet verified on a live route |
| Wall time | Actual controller deadline and Subject timeout; Verifier has its separate timeout |
| Token usage | Observation only; current real usage NOT_REPORTED; stub counts are synthetic |
| Quota | Snapshot availability only, no reservation or enforceable quota-spend ceiling |
| USD | No subscription USD prerequisite or invented hard cap |

Quota parsing handles the Codex bucket and primary/secondary windows; unknown, malformed, stale,
exhausted or wrong-bucket data fails closed. Available extra credits do not override an exhausted
subscription window. No live quota read occurred. Cancellation waits for owned Subject/controller/
Verifier cleanup. Crashes preserve safe counters and workspace/Trace; sealed evidence can be imported
without rerunning, incomplete attempts become INTERRUPTED, tampered receipts are rejected.

Subscription plan budgets are accepted without dollar fields. Until a frozen native subscription
configuration is admitted, preflight returns `BLOCKED / SUBSCRIPTION_RUNTIME_NOT_ADMITTED` before
API-key/provider checks. Existing Phase-1/2 budgets and historical serialization retain their shape.
A subscription request cannot accidentally save an API-billing plan or dispatch the legacy backend.

## Offline operator acceptance

Use only a **new disposable migrated PostgreSQL** and existing local pinned images. The current
services, demo databases and other worktrees are not setup or cleanup targets. No new migrations,
service topology, public execution endpoint or installation is introduced.

- `uv run --locked pytest -q tests/test_subscription_controls.py` includes the data-only contract
  checks and a disposable-DB denial check; supply DATABASE_URL/HARNESSLAB_ENVIRONMENT=test.
- `tests/test_subscription_protocol_docker.py` drives actual frozen CLI → loopback Responses double
  → real tool/workspace → independent Docker Verifier through the Phase-2 API and Worker. Tests also
  cover auth/quota/transport refusal, request cap, deadline, cancellation, crash and tampering.
- `tests/test_local_execution.py`, `tests/test_local_execution_docker.py` and `tests/test_local_plans.py`
  retain Fake-only, immutable evidence, idempotence and recovery compatibility.
- The protocol option is operator-only Fake policy (`protocol_stub=true`, explicit `protocol_limits`,
  `protocol_scenario`), not a UI/provider enablement switch. Subject image must equal the plan's exact
  frozen Codex image. API callers separately confirm `subscription_limits`; no credentials are passed.

`uv run --locked python scripts/prepare_subscription_task.py /tmp/NEW_ADMISSION_DIRECTORY` copies
`core-python-deduplicate@1.0.2`, verifies baseline-fail/oracle-pass twice with 5 actual hidden checks
per run, freezes Custom admission and reuses Phase-1 ingestion. Hidden assets stay outside Subject
materialization. It runs no Subject/model and modifies no Official qualification or original package.
The accepted package, qualification, validation and verifier artifacts are retained in the isolated
output. Its 90-second task timeout and 15-second verifier timeout remain task bounds; a future
subscription authorization must select its own stricter limit and exact task/configuration identity.
See [actual acceptance](qa/subscription-phase25-20261010/README.md).

## Before the first real evaluation — separate user authorization

Offline success does not open execution. A future, separately reviewed change must admit a frozen
subscription runtime/route and a real trusted HTTP auth boundary **outside Subject**, protect its
credential lifecycle from tools, verify egress and all request paths (including retries/refresh),
and obtain a fresh trustworthy subscription-quota observation without spending extra credits.
Unknown credentials/quota/control status must deny dispatch. Token/quota ceilings that cannot be
forced remain observations and cannot be labeled hard limits.

The user must separately authorize product credential access within that trusted boundary, any
necessary account/quota metadata reads, exact task/model/runtime/route, one physical attempt, a
specified timeout and request/turn count, cancellation and failure retention. No inference probe,
refresh-triggered retry, repair, second attempt, extra credits or Phase 3 is implied. Production
installation/migration/deployment, if needed, requires its own scope. **STOP after Phase-2.5 PR/CI.**
