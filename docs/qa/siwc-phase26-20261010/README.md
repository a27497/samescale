# Phase 2.6 — official SIWC applicability and offline auth acceptance

Base `main@1061ddd7b13288f27e6d0545c8d6f6467278073b`; isolated branch
`codex/product-phase26-siwc-20261010`. Authorized: offline work, commit/push, Draft PR and CI.
No real OAuth, account/quota/catalog RPC, token refresh, credential access, inference, merge,
deployment, existing database migration or Phase 3. **REAL_CODEX remains unconditionally closed.**

## Applicability and evidence scope

[Official sources](official-sources.json) record current official document URLs/date/content hashes,
not copied documentation. [Repository eligibility](repository-eligibility.json) observes public
visibility, no detected/root license and unconfirmed licensing/account eligibility. Public source
alone is insufficient. No license is selected and no real consent or qualification is inferred.
[Operator boundary and independent gates](../../SIWC_AUTH_BOUNDARY.md) explains local/self-hosted
versus hosted applicability, credentials, preview limits and first-real authorization.

[Frozen Runtime receipt](frozen-runtime.json) records SameScale initialize/initialized acceptance
on existing pinned 0.149.0 / 0.153.4 images in network-none containers with empty disposable auth
storage. No auth/thread/turn/model RPC was sent. Initialization is not real route compatibility.
The 0.149.0 execution tests run the frozen executable against a local Responses double, including
actual tools/Workspace/Trace and the existing independent hidden Docker Verifier. All these results
remain **FAKE_CODEX / CUSTOM / synthetic / NOT_ATTESTED**, zero real model calls. Existing real-task
admission from Phase 2.5 is retained; synthetic clamp results do not qualify a new real task.

The controller-only in-memory OAuth issuer validates synthetic signatures/claims/granted scopes,
client/account binding, state/nonce/PKCE and lifetimes. HMAC fixtures are not OpenAI JWKS proof.
Lifecycle tests exercise synthetic serialized rotation/revocation and VM host separation. A consumed
physical attempt freezes auth, denies refresh/switch/replay, and preserves durable request debits.
No real OAuth listener, credential importer/store, upstream transport or new Worker was introduced.
[Safe controller observations](controller-observations.json) retain only bounded receipts and counts.

## Final checks

[Source-bound acceptance](acceptance.json), [broad backend log](backend-tests.txt) and
[final auth/ingress log](auth-tests.txt): **221 distinct passing cases across two batches**.
The broad batch passed 218: 64 auth contract, 27 subscription controls, 22 protocol Docker,
21 authorization/queue, 9 original Fake Docker and 75 planning cases. Final focused batch passed
67 (64 repeated, 3 new malformed HTTP counting probes) after the final ingress-count correction.
It is not a single 221-test invocation. Protocol Docker includes 13 SIWC and 9 legacy cases:
solve/request cap, auth/scope/client/availability failure, failed/incomplete streams, timeout,
active cancellation and actual Worker crashes during Subject/after seal without redispatch.
[Initial checks](initial-checks.json) preserve unsuccessful/interrupted checks and corrections;
no interrupted batch is counted as a pass.

Full [Ruff](ruff.txt), [format](format.txt) **817 files**, [mypy](mypy.txt) **418 sources** PASS.
No local frontend/browser campaign is claimed; unchanged frontend contracts run in remote Fast CI.
[Offline replay](offline-regression.json): **73 PASS**, network namespace loopback down/no routes,
two byte-identical replay passes/five outputs, zero external/model/Provider/Judge calls, no Subject
or Verifier execution. [Frozen guard](frozen-protection.json): **419 files BEFORE == AFTER**.
Credential/canary and [documentation-link checks](boundary-checks.json) record bounded scan scope.

## Protection and handoff

[Protection](protection.json): all nine prior worktrees retain HEAD/status/diff/file hashes; UI-2
retains 17 dirty entries and 1,494 hashes. All 58 prior containers retain identities/images/start and
running state/mounts (mount lists compared semantically). Developer auth metadata is unchanged;
credential bytes are never read or captured. Website/configuration/deployments are untouched.
Only a new labeled tmpfs PostgreSQL was migrated for isolated tests and then removed. Attempt-owned
containers were cleaned only within the new test scope. No existing database was queried or migrated.

Exact pushed SHA, Draft PR and push/PR CI are separate Git handoff facts, pending in this immutable
pre-publication snapshot. [Base CI](base-ci.json) already passed at the exact requested base.
Remaining gates: license/copyright and integration/account eligibility; independent product OAuth
consent; real JWKS/storage/lifecycle/TLS/egress/route and complete request/retry/cancellation controls;
then a separately authorized exact task/model/image/route and one physical attempt. Token/quota
are availability observations, never hard spending caps; no automatic extra-credit purchase.
**STOP after offline acceptance, Draft PR and CI. No real evaluation or Phase 3.**
