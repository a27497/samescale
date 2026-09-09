# HarnessLab Project Status

Updated 2026-09-09. Active scope: **P0 — Agent application main path closeout**.

## P0 application closeout

- Work continues on `codex/l-real-agent-main-integration` at `79056a1`; no commit, push or merge.
  Pre-existing edits to this file and FIRST_APPLICATION are retained.
- `/` now opens Analyst with separate offline Fake, frozen historical Real, and current database
  session entrypoints. Advanced evaluation pages remain available; Overview moves to `/overview`.
- The offline deduplication case runs the existing graph and structured fact validator against
  explicitly synthetic tools with a fixed Fake script: 2 decisions, 2 tools, zero Provider requests.
  It requires the local API/build but no PostgreSQL, Docker or credentials. It does not persist.
- Historical display reads hash-checked frozen files directly, including source data and digest
  bindings. No original session row is reconstructed. The effective 4/4 limit correction is shown
  separately; original report bytes remain unchanged.
- Reports show conclusion, navigable evidence, limitations/hypotheses, and next steps. Current
  sessions retain persisted resume/proposal/approval behavior and explicit Real confirmation.
  Registry failure no longer blocks Fake; failed scope changes clear stale session controls.
- Validation: 19 focused backend tests and 78 Analyst session/E2E tests passed; the latter used a
  new disposable PostgreSQL database. All 50 frontend tests, type checking and production build passed.
  Focused Ruff/format and mypy checks passed; all five frozen evidence files retained their hashes.
  Real browser checks passed at 1440/390 pixels for routing, offline/history separation, citations,
  refresh and no horizontal overflow. No provider or historical database was used by the browser.
- Suggested next step: rehearse the three entrypoints using the README quickstart. Locate a
  verifiable backup only if original-session restoration is needed; do not reconstruct it from
  summaries. Human ownership and prior security/runtime debts remain separate and unverified.

The sections below retain the previous real-smoke and first-application closeout evidence. Their
past test totals are historical, not additional tests executed by this P0 task.

The integrated source now has a complete local backend regression and a working keyless browser
rehearsal. Human ownership is still **NOT_VERIFIED**. The accepted real smoke below is supported
by frozen artifacts; its original database session row was not found in the databases checked
during this closeout. Do not claim it has been restored into the current Workbench.

## Current result

**REAL_AGENT_SMOKE = VERIFIED / COMPLETED** for the bounded Attribution Analyst vertical slice.

- Accepted live session: `analyst-0be376756a4f447bbdeeb44a58b292b5` over persisted
  `core-real-matrix-v6` evidence.
- Profile: `deepseek-official-v4flash-responses-smoke-v6`, official Responses route,
  `reasoning_effort=low`, 32,768 output-token ceiling.
- Final path: 4 provider decisions, 9 read-only tool calls, 4/4 request reservations, no Fake
  fallback. Observed total: 161,015 input + 15,617 output = 176,632 tokens, USD 0.09146104,
  107,305 ms summed provider latency.
- Canonical host-validated report:
  `sha256:1733eace25488c8e435e2fd1f7d5e6d1ae7c676a047259ab3edc3dd6315c19b1`.
- Review-only proposal:
  `sha256:24eec75a37c2695d39c1383b64208fa57ef56f3ef606873c75e3291aaa4b7820`.
  Approval is bound to the exact scope/proposal digest and carries `execution_authorized=false`.
- Repository evidence: [REAL_AGENT_SMOKE_20260909](evidence/REAL_AGENT_SMOKE_20260909.md) plus the
  canonical report/proposal/approval/session summary under `docs/evidence/real-agent-smoke-v6/`.

The accepted v6 session dynamically used `get_task_contract`, `query_runs`, `compare_cells`,
`inspect_failure`, and `get_ablation`. It did not select `inspect_trace`. Separate real v3/v5
trajectories did select and complete `inspect_trace`; those sessions remain historical failure
and tool-selection evidence rather than being merged into the v6 report.

## What the live closeout established

- Real ProviderAdapter structured decisions work on the official DeepSeek Responses route.
- Model-selected tool calls are host-scoped and host-executed; the model never receives shell,
  arbitrary SQL/filesystem, Harness/Judge execution, queue, browser, or generic code tools.
- PostgreSQL decision/tool reservations, resume, no-refund accounting, exact usage/cost telemetry,
  request ceilings, and profile/scope drift checks work across real calls.
- DeepSeek output accounting includes reasoning. Incomplete `max_output_tokens` responses now retain
  bounded `incomplete_response`, response status/reason, and a hashed request-ID fingerprint.
- Final facts remain fail-closed. A semantically invalid final draft is not accepted or rewritten;
  when decision budget remains, the host records an allowlisted finalization rejection and exposes
  exact valid scalar assertion candidates for a later explicit resume. Budget exhaustion still ends
  in `INVALID_ATTRIBUTION`.
- The final v6 report passed exact evidence binding, and its regression proposal passed scope and
  evidence validation. Review approval authorizes no execution.

The report intentionally does **not** claim that Codex-high outperforms Claude on
`core-java-deduplicate`, and does not add a harness-uplift or reasoning-effort causal claim. The
available task/cell evidence is informal or insufficient and includes substantial infrastructure /
execution-budget loss.

## Validation position

- Final full backend regression: **1279 PASS, zero failures/skips**, 785.07 seconds, using a fresh
  job-owned PostgreSQL container and an environment without provider credentials. This includes
  Analyst sessions, Phase M, migrations, release compatibility, and the new effective-limit cases.
- Frontend: **43/43 Vitest PASS**, `vue-tsc --noEmit` PASS, Vite production build PASS.
- Ruff check/format, mypy, and whitespace checks PASS.
- Actual browser rehearsal on the isolated V6 demo copy: Fake COMPLETED, 2 decisions / 6 tools,
  zero provider requests; proposal saved, review-only approval persisted, refresh retained state.
  No page errors or horizontal overflow at 1440x1000 and 390x844.
- Five original real-smoke file hashes remain unchanged. The original final report's 35 structured
  assertions, raw-artifact equality, proposal/approval binding, and usage sums were checked.
- Exact delivery SHA and remote CI belong to Git and its commit checks; an earlier main CI pass is
  not evidence for this candidate. Full A-K release/tag acceptance is a separate procedure.

The prior 1272 PASS / 4 FAIL run remains historical evidence. The final run above supersedes its
unresolved-test status. No new real Provider/Harness/Judge/Matrix campaign was run.

## First-application corrections and demonstration

- New reports carry the actual session decision/tool limits in JSON and Markdown. The original v6
  report retains its digest and recorded 4/8 display; the effective limit was 4/4, documented in
  [the separate correction](evidence/REAL_AGENT_SMOKE_20260909_CORRECTION.md).
- The Analyst UI now selects a visible bounded set of proposal references; a 104-entry evidence
  catalog no longer causes an oversized default proposal. Long identifiers and controls fit
  desktop/mobile widths; the evidence catalog can be expanded without burying the report.
- [First-application materials](FIRST_APPLICATION.md) contain a capability draft, 3-5 minute script,
  and pending human A/B/C checkpoints. They do not claim the user authored or mastered AI-assisted code.
- Current default DB: 1404 runs, zero Analyst sessions. Integration DB: 2034 runs, zero Analyst
  sessions at inspection. Neither contained the accepted real session. The local demonstration
  uses its own V6-only copy of the integration DB; other legacy experiments caused a plan-identity
  error in the unfiltered list. Original databases/evidence were not repaired, deleted, or rewritten.
- The demo serves at `http://127.0.0.1:8765/analyst` while its local process is running, with real
  invocation disabled. It demonstrates Fake interaction; frozen files demonstrate the past real run.

## Mainline / historical authority retained

- Integration worktree: `/home/dev/projects/harnesslab-ai-integration`, branch
  `codex/l-real-agent-main-integration`, starting baseline `3335668f4f11e384a9f99fb0a8692f07d8937902`.
- Phase M lifecycle/admission/funnel/budget/resource/failure-cluster authority is retained;
  `experiment/lifecycle.py` is not replaced by the Real Agent work.
- Accepted historical V6 Matrix/Judge/BadCase/Pair/Ablation evidence remains immutable. Post-freeze
  source evolution is bound to historical SHA-256 identities rather than rewriting frozen reports.
- Phase L technical closeout remains `ACCEPTED_WITH_KNOWN_DEBT`: F1/F2/F3/F4/F6 accepted; F5 durable
  cancellation/orphan-process interruption remains known debt.

## NEXT

The delivery candidate and exact-SHA Fast CI have been checked: source
`79056a1a4619863970b8d5b37102434427cec5f3`, successful run `34344469107`.
At the user's request, pause the continuous ownership questions and proceed with first-application
materials and demonstration preparation. Guided behavior predictions, a completed `None` assertion,
and a predicted test failure are recorded in [the participation log](FIRST_APPLICATION.md).
The AI demonstrated a temporary incorrect counter against an existing test; this was not a new
user-authored repair. B/C and overall human ownership remain **NOT_VERIFIED**, not waived.

Use the project introduction and separated frozen-real/Fake demonstration script; omit the personal
core-repair demonstration until actually completed. The local demo entry returned HTTP 200 during
this materials update; the earlier full browser rehearsal remains the interaction evidence. No
application submission, publication, merge, or paid execution was performed by this update. Locating
a verifiable backup of the missing original real session remains an explicit runtime-recovery task;
do not reconstruct a supposedly original row from public summaries or rerun paid calls to hide it.

**Stop Real Agent platform expansion.** Do not rerun the 630-slot Matrix, restart K-B4, or add
reliability experiments merely to improve the demo. Only fix concrete application-blocking defects.

Final release/tag verification is a separate release procedure. This Real Agent closeout neither
reruns nor redefines the accepted V6 release contract.

## Retained limitations

Security acceptance remains `NOT_VERIFIED`, including the H-Lane protected-file gap, unauthenticated
local reviewer label, localhost/single-user Workbench assumptions, and the F5 orphan-process gap.
The final v6 report did not itself use trace evidence; real trace-tool execution is evidenced by
separate v3/v5 trajectories. No new regression plan was executed. No new Provider/Harness/Judge/
Matrix campaign is authorized by the review-only proposal.
