# Private local execution — MVP Phase 2

Phase 2.5 adds [ChatGPT subscription preparation](SUBSCRIPTION_EXECUTION.md), offline protocol
acceptance and independent real-task admission. Real execution stays closed; subscription
execution does not require an API key, API billing or a USD hard cap. Original Phase-2 Fake
evidence remains unchanged.

Phase 1 saves an immutable plan. A separate local-operator action authorizes **one physical
attempt**; it does not alter `SavedPlan.execution_authorized=false`. The new authorization,
attempt association and result are separate append-only records. `harnesslab local-worker`
consumes this new single-slot queue using the existing `execution_lease` table and Codex H-Lane
Runner; legacy dual-Cell experiments continue through their existing executor.

## Supported boundary

**Only `FAKE_CODEX` is executable.** It runs fixed trusted Python fixture code in a real Docker
container, through the existing Codex JSONL adapter. It writes the real isolated final Workspace,
then the existing H-Lane orchestrator runs the task's hidden verifier in another container.
No real Codex executable, user Codex login, Provider, model or Judge is called. These are
`CUSTOM / synthetic / NOT_ATTESTED` Episodes, never real model results or Official qualification.

A `REAL_CODEX` authorization request returns `403 / REAL_EXECUTION_BLOCKED`: the trusted subscription credential boundary, live route/quota and request interception are
not independently verified. The Phase-2.5 code gate has no environment bypass. Token/quota
observations are not hard caps; USD hard caps are not subscription prerequisites. The real Docker Codex backend remains compatible but
cannot be dispatched by this Worker. Live runtime/version/protocol, Provider egress/credentials,
real task admission and production operation are **NOT_VERIFIED**. Grok remains **NOT_CONFIRMED**.

## Operator setup (do not change existing production services)

1. Use a private loopback API and a separate Worker process. Neither is a public execution service.
   Give **only the Worker** Docker privilege. The API must have no Docker socket, Docker group,
   privileged container, host root/checkout mount or remote Docker endpoint. Set
   `HARNESSLAB_LOCAL_TASK_POLICY` and `HARNESSLAB_LOCAL_CONFIGURATION_TOKEN` as in
   [local planning](LOCAL_PLANNING.md). Keep credential references separate from credential values.
2. Apply Alembic `20261009_0012` to a new disposable/development DB before testing. This task did
   not migrate an existing DB. In a future operator installation, migration requires a separately
   authorized backup/change procedure. Authorization/result tables reject UPDATE and DELETE;
   queue state remains mutable in `execution_lease` under ownership checks.
3. Create an owner-only JSON file outside source/store/evidence/worker roots. Set
   `HARNESSLAB_LOCAL_EXECUTION_POLICY` to its canonical path. Example (IDs are placeholders):

   ```json
   {
     "schema_version": 1,
     "mode": "FAKE_CODEX",
     "artifact_root": "/private/samescale-execution/artifacts",
     "runtime_root": "/private/samescale-execution/runtime",
     "subject_image_identity": "sha256:<exact-existing-local-test-image-id>",
     "verifier_image_identity": "sha256:<exact-existing-local-verifier-image-id>",
     "fixture_task_identities": ["sha256:<admitted-isolated-clamp-fixture-task-digest>"],
     "scenario": "solve",
     "authorization_ttl_seconds": 300,
     "lease_seconds": 15
   }
   ```

   The Fake fixture currently supports only an operator-approved `micro-python-clamp` package
   without context. Scenarios are fixed server-owned code (`solve`, `wrong_workspace`, `timeout`,
   `slow`, `verifier_timeout`); the client cannot supply code, a scenario, argv, credentials or paths.
   Subject and verifier images must already exist locally; this path never builds, pulls or upgrades
   an image. Existing Codex image metadata is rechecked, but its executable is **not probed**.
4. Open `/plans/:planId`. Recreate stale plans when application/task/configuration identity changes.
   Independently confirm the frozen plan budget and one Fake attempt with zero model cost. The API
   inserts authorization + one queue slot atomically. It does not launch containers.
5. In the separately privileged local environment run `uv run --locked harnesslab local-worker once`
   for bounded consumption, or `uv run --locked harnesslab local-worker serve` to poll. Start neither
   against public Demo nor an existing business database during acceptance. No Worker is installed,
   automatically started, exposed on a port or deployed by this change.

Execution-enabled planning APIs read the operator's approved image ID without Docker. Their
`runtime_probe=OPERATOR_IMAGE_ID_WORKER_RECHECK_REQUIRED` is weaker than actual local metadata
inspection. The Worker checks all three current local image IDs before dispatch. Phase-1-only
mode retains its existing local metadata check; unavailable images never get pulled by this Worker.

## Durable contract and lifecycle

| Boundary | Contract |
| --- | --- |
| Authorize | `POST /api/local-execution/plans/{plan_id}/authorize`: exact `plan_digest`, canonical single `run_slot_digest`, UUID idempotency key, frozen `confirmed_budget`, `mode=FAKE_CODEX`, `max_model_cost_usd=0`, explicit `confirm_one_attempt` and `acknowledge_reference_budgets` |
| Read | `GET /api/local-execution/plans/{plan_id}`: current queue state, one original authorization, immutable result/Episode identity, counts and failure reason; evidence digest validation fails closed |
| Cancel | `POST /api/local-execution/plans/{plan_id}/cancel` with `{"action":"CANCEL"}`; queued cancellation prevents launch; active state remains active until Worker stops containers |
| Claim | Row lock + `SKIP LOCKED`, attempt `0→1`, owner and TTL; concurrent Workers cannot consume the same slot twice |
| Dispatch | Expiry, operator, task/source/qualification, plan/slot/budget, frozen configuration/application and execution policy/image IDs rechecked; a digest-checked task copy creates a separate subject Workspace |
| Seal | Runner atomically saves normalized Trace, sanitized native events, final Workspace/change digests and separate verifier artifacts. Result binds plan/authorization/slot/run/Episode; fsync + atomic seal precedes immutable DB result |
| Recovery | Expired consumed attempt is never requeued. After scoped owned-container cleanup, import a valid sealed result or record `INTERRUPTED / NOT_VERIFIED`; partial evidence remains preserved and cannot invoke a subject |

The original `/api/local-plans/plans/{id}/execute` still rejects execution. No old Run or Episode
is rewritten. Saving a plan, reading evidence, idempotent resubmission, Worker restart, or lease
expiry cannot authorize another physical attempt. This conservative policy may consume an attempt
without launching anything; obtaining a new attempt requires a new plan and separate authorization.
A lost response can be retried using the same request key; completed/cancelled/interrupted attempts
stay terminal. Rotating the operator credential invalidates unconsumed authorizations.

`VERIFIED_PASS` requires positive independent checks and a digest-bound final Workspace.
`VERIFIED_FAIL` means the verifier completed and rejected that Workspace. `TIMEOUT`, `BLOCKED`,
`FAILED_INFRA`, `INTERRUPTED` and `CANCELLED` are never passes. Agent success statements remain
Trace data. Lifecycle diagnostics distinguish verifier timeout/failure from subject timeout.
Cancellation preserves already collected evidence but its authoritative result is `NOT_VERIFIED`;
an already collected Episode retains its original recorded identity rather than being rewritten.

## Actual limits and cleanup

- Fake model-call limit **0** and model cost **$0**: fixed code, no credentials, network `none`.
  Planning tokens/USD are reference values, not reservations or hard caps.
- `wall_time_seconds` controls the **Subject process timeout**, not total preparation + verification
  time. Verifier uses its separately frozen task timeout. Docker CLI/preflight/cleanup operations
  have their existing bounded timeouts. No total queue waiting-time guarantee is claimed.
- Subject: readonly rootfs, user `10001`, no-new-privileges, all capabilities dropped, network none,
  memory 1 GiB, 2 CPUs, 256 PIDs, restart=no; only its writable isolated Workspace is mounted.
  No hidden verifier/oracle, host checkout, login credentials or Docker socket is mounted.
- Verifier: separate exact-ID container, readonly Workspace + staged verifier only, network none,
  memory 128 MiB, 0.5 CPU, 64 PIDs, non-root, no privileges; oracle is not mounted.
- Scoped deterministic names and labels prevent cleanup of unrelated containers. A terminal Worker
  result requires absence checks for both owned containers. Failed cleanup stops finalization;
  consumed attempts remain recoverable without redispatch. Active local flock prevents another
  process from reconciling an expired but still-running attempt.
- Normal subject/staged-verifier runtime and task copy are removed. Failed/crashed runtime remnants
  and verifier staging evidence are kept under operator-owned roots for inspection; no broad prune,
  historical cleanup or automatic artifact deletion occurs. Future retention/disk quotas are not
  implemented. Docker is not VM isolation; only trusted admitted tasks are in scope.
- API acceptance used a non-root readonly container with no Docker socket/device/privilege, plus
  subprocess denial sentinels. The acceptance container used host networking **only with loopback
  bind** to reach the disposable DB; this is not a production network recommendation or deployment.
  OS/service accounts, separate DB roles, backups and operational topology still require installation
  validation. The existing product Compose has not been rewritten or deployed.

## Before the first real Codex evaluation

A separate user authorization must identify the eligible engineering task and exact frozen image/
model/subscription route, trusted credential source outside Subject, one physical attempt, actual
wall timeout and request/turn limits, retention and cancellation. First admit and independently verify
live credential isolation, subscription quota availability and all request/retry/refresh paths.
No API key or USD/token hard cap is a subscription prerequisite; unforceable ceilings remain
observations. Unknown or exhausted quota, invalid auth or unverifiable critical controls deny.
See [Phase-2.5 first-real requirements](SUBSCRIPTION_EXECUTION.md#before-the-first-real-evaluation--separate-user-authorization).
Current acceptance grants no live execution, credential access, extra credits, deployment or Phase-3
permission. The real-task admission and offline CLI/protocol checks have their separately bound scope.
