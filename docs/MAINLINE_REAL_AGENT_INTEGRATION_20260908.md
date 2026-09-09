# Mainline L + Real Agent integration — 2026-09-08

Result: **KEYLESS_READY / REAL_AGENT_SMOKE BLOCKED**. This is an uncommitted integration
on main@3335668, not a mutation of the main branch. No Provider/Harness/Judge/Matrix
invocation, commit, push, merge, or deployment was performed.

Worktree: `/home/dev/projects/harnesslab-ai-integration`

Branch: `codex/l-real-agent-main-integration`

Audit directory: `/home/dev/harnesslab-main-integration-20260908`

## Mainline integration and conflict decisions

Main's authoritative lifecycle, M.3 admission/exposure, M.4 funnel decisions, M.5 unified
preflight and durable budgets, M.6 attempts/resource/control journals and M.7 failure
projections are retained. All prior DB model definitions and Alembic migrations are
unchanged; the model export list adds Analyst alongside the existing M exports.

| Area | Mainline judgment and integrated result |
| --- | --- |
| F1 | Main still checked owner/lease without immutable claim attempt. Port all four mutation checks and caller snapshots, including main's M.6 test callers. Terminal reconciliation also locks and checks the physical attempt, rejecting stale-claim budget writes. |
| F2 | Main still counted trace events/cached metrics. Port digest-bound invocation counts shared by executor/report/Diagnosis; unknown stays unknown. A new Fake E2E counterexample exposed the merged executor losing the manifest argument; corrected and reverified persisted counts. |
| F3 | Port legacy expired-cancellation/dispatcher maintenance and cancellation-safe release. Exclude authoritative attempts from legacy maintenance; retain main's authoritative expiry, controls, transitions and reconciliation. |
| F4 | Port complete terminal refresh, serialized polling and retry handling; all frontend contracts pass. |
| F6 | Port locked frontend CI contracts and bounded Python coverage; preserve existing main job/gate structure. |
| Lifecycle deletion | Reject. Main queue, authoritative lifecycle and Diagnosis projection service import `experiment/lifecycle.py`. Module and its tests retained byte-identically. |
| Terminal statuses | Main already supports `BUDGET_EXHAUSTED`; retain it while sharing the existing terminal set with executor and Workbench. Do not reimplement the terminal state. |
| Evidence reader | Retain main's `EvidenceRecord` protocol used by physical-attempt projections. Port verified-manifest trace reuse and single-read digest validation. Reject reader→queue identity import: queue→authoritative→reader makes that old consolidation unsafe. |
| DB exports | Union Analyst and all main Phase M models. No replacement of main's export set. |
| Migration tests | Preserve dynamic head expectations in database/Judge tests; M.6-specific migration test targets its own revision. Gate J checks the single Analyst 0007 successor and no second head. |
| Workbench API | Union six Analyst API paths with main's 16 pre-existing paths, including projected-cluster API. |
| Historical source checks | Preserve accepted-commit Diagnosis/Analyst source binding map and tamper regressions. Frozen receipts and evidence bytes are unchanged. |
| Instructions | Port blueprint/status/AGENTS/rules layers; rewrite live status for this baseline. Do not restore main-deleted L.1 audit or obsolete lifecycle-removal claims. |

Seven three-way textual conflicts were resolved in model exports, reader, executor,
queue and database/Judge/Workbench tests. `merge-decisions.json` records the initial
per-file merge disposition; `reachability-main.json` records main consumers. The
original accepted F1 counterexample remains byte-identical. A cancellation test now uses
an injected clock to remove its observed 150ms host-scheduling race.

## Re-evaluation of all old closeout paths

| Old closeout paths | Mainline decision |
| --- | --- |
| docs/ARCHITECTURE.md | Retain current implementation boundaries and standalone-lease removal; authoritative Phase M remains. |
| docs/PHASE_M_EVALUATION_SYSTEM_2.md | Reject obsolete lifecycle deletion/no-schema narrative; document retained M.6 and additive Analyst migration. |
| docs/PROJECT_STATUS.md | Replace stale live state with this integration result; prior handoff evidence remains external and immutable. |
| frontend/src/stores/experiments.ts; frontend/tests/workbench.spec.ts | Retain terminal-loading correction and behavioral counterexample. |
| scripts/verify_gate_c.py | Retain real queue integration suite selection after owner-only service removal. |
| src/harnesslab/api/workbench_service.py | Retain terminal set reuse including main's budget-exhausted status. |
| src/harnesslab/evidence/reader.py | Retain byte-bound trace reuse; reject queue import/concrete ORM regression. |
| src/harnesslab/experiment/dispatch.py | Retain abandoned cancellation frontier repair for legacy runs only. |
| src/harnesslab/experiment/executor.py | Retain claim-safe caller changes, terminal set reuse and queue identity export; preserve authoritative claim/reconciliation. |
| src/harnesslab/experiment/lifecycle.py; tests/test_experiment_lifecycle.py | Reject both deletions: reachable main authority and regression coverage. |
| src/harnesslab/experiment/queue.py | Retain legacy maintenance with authoritative exclusion and all main M.6 transitions/reservations. |
| src/harnesslab/experiment/tool_metrics.py | Retain shared byte-verified trace counter and invalid-terminal handling. |
| src/harnesslab/leases.py; tests/test_execution_lease.py | Retain deletion: main source has no consumer; only its own test imports service. Keep execution_lease ORM/table and historical migrations. |
| src/harnesslab/release/badcases.py | Retain accepted-source binding adjustment; do not rewrite frozen evidence. |
| tests/test_ci_workflow_contracts.py | Retain queue selection and frontend contracts; update Analyst lineage gate. |
| tests/test_eval_methodology_v2.py | Retain dispatcher cancellation counterexamples. |
| tests/test_experiment_executor_safety.py | Retain ownership/cancellation counterexamples; make cancellation clock deterministic. |
| tests/test_experiment_tool_metrics.py | Retain invocation counting and missingness regressions. |
| tests/test_kb4_badcase_freeze.py | Retain historical-source and tamper checks. |
| tests/test_release_semantic_verifier.py | Retain isolated empty-Git fixture plus existing-tag rejection test; production tag guard unchanged. |

The only removed production module is the unreferenced owner-only lease service.
Repository imports/text and package configuration were checked; unknown external direct
imports are outside repository reachability. Main lifecycle is included in the wheel.

## Migration and data preservation

Single head: `20260908_0007`; down_revision: `20260904_0006`.
Clone source at 0006 → upgrade 0007 → downgrade 0006 → upgrade 0007: PASS, comparing
all prior table row counts, ordered row-data SHA256 and column-schema SHA256.
Only after this passed, current restored DB was backed up and upgraded.

Restored DB before/after: **experiment=6; experiment_run=2034**. All pre-existing table
rows and column schemas preserved, including Phase M. Constraints and indexes also
compared unchanged. The final DB adds exactly one Analyst session. No historical
run, attempt, budget or evidence row was regenerated, deleted or backfilled.

Backup: `restored-before-0007.dump` (mode 0600), with SHA256 in `backup.json`.
Detailed evidence: `clone-migration.json`, `restored-migration.json`,
`restored-constraints-indexes.json`, `restored-final.json`, `integrity.json` and
`historical-evidence-integrity.json`. Reference a91f825 dirty tree status and changed-file
hashes remain unchanged; original frozen release/artifact and migration hashes remain.

## Validation

- Mainline and accepted capabilities: `regression-final.xml` — 326 PASS.
- Analyst/Diagnosis/provider MockTransport/Registry/Phase M budget/preflight/suites/Judge
  Fake regressions: `extended.xml` — 171 PASS.
- Final executor/F2/attempt reconciliation suite: `executor-verified.xml` — 43 PASS.
- Latest unique union: **500 PASS, 0 FAIL, 0 SKIP** (`test-summary.json`); these overlap.
- Frontend 42 PASS; type-check and production build PASS.
- Ruff check/format and mypy 333 files PASS. Wheel build and portable smoke recorded
  in `wheel.log` and `wheel-smoke.json`.
- Earlier failures are preserved in logs: migration/gate adaptation, legacy cancellation
  lease cleanup, F2 manifest-path counterexample and test scheduling/import fixes.

Full repository pytest, full A–K, remote CI, browser E2E, product deployment and security
audit NOT_RUN. All exercised provider/harness/judge regressions use Fake or MockTransport.
No live provider schema, accounting, or reasoning quality is claimed verified.

## Official profile and fixed smoke

Profile: `deepseek-official-v4flash-responses`. Historical chat profile and digest are unchanged.
Route: `deepseek-official|responses|https://api.deepseek.com/responses`. Context: **1,000,000**; Responses + json_schema.
Peak cache-miss planning price: input **$0.44 / 1M**, output **$1.32 / 1M**, request **$0**.
[Current official evidence reference](evidence/DEEPSEEK_OFFICIAL_20260908.md) is new;
frozen historical price/evidence files are unchanged.

Scope: `core-real-matrix-v6`. Goal:

> Compare Codex high and Claude on core-java-deduplicate, inspect relevant failures and traces, report only evidence-backed facts and limitations, and propose one review-only regression plan if justified.

Fixed caps: 3 decisions, 6 tools, 3 provider requests, 1200 output tokens/request,
256000 input bytes/request, 1050000 cumulative tokens, 90s/request, **$0.50**.
First envelope: **67,505 input bytes**; conservative token reservation **1,001,200**;
conservative cost reservation **$0.441584**. Caps allow at most three requests; they do
not guarantee three continuations. Each next request must fit observed cumulative usage
plus the next full context/output reservation. Unknown accounting blocks continuation.

Exact input: `profiles/analyst/core-real-matrix-v6-smoke.json`.
Keyless preparation entrypoint: `scripts/prepare_real_agent_smoke.py` (explicitly empty
provider environment, no resume, no real enablement). DB connection is configured separately.

Session: `analyst-8b704a86d9424cd49c7983925b832094`.
The persisted session is PAUSED; its smoke preflight is **BLOCKED**. Decision/tool/request
usage is 0. Preflight reason: **CREDENTIAL_REFERENCE_MISSING**. Credential status **MISSING**;
base endpoint status SET. Process DEEPSEEK_API_KEY name-presence check returned MISSING;
no provider credential value was loaded or printed.

| Digest | Value |
| --- | --- |
| Registry profile | `sha256:3de99defe42b2aed8798bd1190160fba489f1953d93cafd98ae07130ca373f60` |
| Frozen Analyst profile | `sha256:abe445b726feea6d4ac9c8ef4b81cabc067da0abe62710e762f97d47c57e6731` |
| Session | `sha256:eae02638a87cd6d148d16b885e61b1c18d44d857f9105a26b3ee33d0d5796e18` |
| Scope | `sha256:d3d026cfbfbe014b943705a894ad06e125f59ad6060b73c05daf84588b7aa73e` |
| Decision schema | `sha256:db9972f16f9e7d150f4a68748945ee7c58c6e5cbfa50fa19c4a4278c94ebc896` |
| Preflight | `sha256:72dc7a3b9becf97a7eaf1b46aa7d4799a16a3306522fe40360c7d466c02297b0` |

Full JSON: audit directory `smoke/session.json` and `smoke/preflight.json`.
Server real enablement is false; per-step confirmation remains required;
execution_authorized is false. These execution gates remain closed independently of
configuration readiness. Real Agent smoke itself is **NOT_RUN**. F5, H-Lane protected-file
and human/security-acceptance limitations remain. **Stop at this handoff.**

## 2026-09-09 follow-up

The `KEYLESS_READY / REAL_AGENT_SMOKE BLOCKED` result above remains the exact 2026-09-08 handoff
state. On 2026-09-09, separately authorized bounded live work completed the Real Agent vertical
slice. The accepted session/report/proposal/approval identities and the failure/repair history are
recorded in [Project Status](PROJECT_STATUS.md) and
[REAL_AGENT_SMOKE_20260909](evidence/REAL_AGENT_SMOKE_20260909.md). No historical session or frozen
V6 release artifact was rewritten.
