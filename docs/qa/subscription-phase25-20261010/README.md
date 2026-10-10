# Phase 2.5 — subscription preparation acceptance

Baseline: `main@3cbefb6731d07c6eddb3463c895eeef60b2f0fd9`. Independent branch/worktree:
`codex/product-phase25-subscription-20261010` / `/home/dev/.worktrees/samescale-phase25-20261010`.
The user authorized offline implementation/acceptance, commit, push and Draft PR; no subscription
inference, actual Token extraction, account/quota RPC, login/logout, runtime upgrade, existing DB
migration, deployment, merge or Phase 3. Real dispatch remains unconditionally closed.

## Evidence scopes

- [No-model runtime checks](runtime-checks.json): development CLI 0.160.1 / local ChatGPT status /
  built-in OpenAI Responses selection, no URL overrides; actual served route and entitlement remain
  NOT_VERIFIED. Frozen Docker versions 0.149.0/0.153.4 and local protocol-schema declarations were
  checked with network disabled, without auth RPC or inference. CLI 0.149.0 is used by the double.
- [Task admission](task-receipt.json), [qualification](task-qualification.json),
  [baseline/oracle validation](task-validation.json): copied real `core-python-deduplicate@1.0.2`,
  two actual baseline-fail/oracle-pass rounds, five hidden checks each, stable repeated stdout hashes,
  readonly network-none verifier and verified cleanup. Existing Phase-1 import/admission accepts it.
  This is deterministic engineering-task qualification, not a Subject/model result or an alteration
  of Official qualification. Full isolated source/verifier artifacts remain under
  `/tmp/samescale-phase25-checks/real-task-admission`.
- Protocol execution uses the **separate synthetic clamp fixture**. Real frozen CLI, real tool
  execution, Workspace, Trace, separate Docker Verifier and PostgreSQL ledger are exercised; its
  Responses server and credentials are doubles. Evidence stays CUSTOM/synthetic/NOT_ATTESTED,
  zero real model calls, unknown real Token/quota usage. No inference entitlement claim is made.
- [Initial checks and corrections](initial-checks.json) retain unsuccessful attempts. Initial
  comprehensive checks passed 140 tests; final compatibility review added an old-authorization
  serialization check and preserves absent optional controls in immutable historical digests.
  Final acceptance results and exact source bindings are recorded separately below.

## Final local acceptance

**141/141 backend tests PASS**: 27 subscription contracts (including API denial and old digest
compatibility), 9 actual frozen-CLI protocol Docker cases, 21 original authorization/queue contracts,
9 original Fake Docker cases and 75 Phase-1 planning checks. Protocol cases cover solve, request cap,
auth/quota/transport failure, controller deadline, active cancellation and actual Worker crashes during
Subject/after seal. Original Fake cases additionally cover verifier timeout, wrong Workspace,
after-claim crash and forged recovery verdicts. Source-bound [acceptance receipt](acceptance.json),
[backend log](backend-tests.txt) and [frontend log](frontend-tests.json) preserve their scope.

Frontend **23/23 PASS**, Vue typecheck and isolated production build PASS. Python full Ruff and
format **814 files PASS**, mypy **416 files PASS**, credential-pattern scan PASS and whitespace PASS.
No new browser campaign is claimed for the single copy change. [Offline regression](offline-regression.json)
**73 PASS**, two byte-identical replay passes/five outputs, zero external/Provider/model/Judge calls,
no Subject/Verifier execution. [Frozen protection](frozen-protection.json): **419 BEFORE == AFTER**.
The replay results remain valid after the later optional-field serialization correction; the final
141-test suite directly verifies the affected authorization/evidence contracts.

## Protection and isolation

[Protection receipt](protection.json) compares all eight original worktrees, HEAD/status/diff and
file bytes; original UI-2 retains 17 dirty entries and 1,494 file hashes. All 58 existing containers
(including 23 running) retain their identities, image, start/running state and mounts. One Docker
mount-list ordering difference is compared by destination/source; no mount attribute changed.
Developer auth metadata is unchanged; credential contents are never captured. Existing databases
were not queried or migrated, and no website/service deployment or configuration edit occurred.
Only `samescale-phase25-test-postgres-20261010`, with tmpfs data and loopback ephemeral port, was
created/migrated; test schemas are disposable. All subject/controller/verifier cleanup is attempt
scoped. The isolated frontend build is outside any served `frontend/dist`.

Local frozen-evidence guards protect the existing 419 release/evidence/recruiter files.
Offline replay runs inside a network namespace with loopback down, no routes, denied external calls
and no Subject/Verifier execution. Remote GitHub CI is a separate source/check scope; it does not
run Docker protocol acceptance or consume account quota.

## Remaining live blockers and stopping point

The existing credential-in-Subject and opaque CONNECT architecture is incompatible with the required
subscription secret/request boundary. The new controller has **no live credential loader, token
refresh or upstream transport**. Its isolation/request proof applies to the offline double only.
Live route, account/quota availability, real credential injection outside Subject, all retry/refresh
paths and production topology remain unverified. Subscription budgets need neither API keys nor USD
hard caps; Token/quota observations are never promoted to hard ceilings. Unknown/exhausted quota or
unverifiable controls must reject dispatch. No additional credits are bought.

First real evaluation requires a separately reviewed safe live boundary and explicit user permission
for product credential/account-metadata access, exact task/model/image/subscription route, one attempt,
time/request/turn limits, cancellation and retention. Offline acceptance/PR/CI grants none of those
permissions. See [operator boundary and contracts](../../SUBSCRIPTION_EXECUTION.md).
**STOP after Git/CI handoff. No real evaluation, merge, deployment or Phase 3.**
