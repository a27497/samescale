# SameScale Product — Public Product Contract

## ChatGPT subscription preparation — Phase 2.5 — 2026-10-10

Real execution remains **closed by a code gate**. Subscription access requires neither an API key
nor a USD hard cap. Subscription request/turn/time contracts are explicit; unforceable Token/quota
ceilings remain observations. Data-only subscription preflight accepts a budget without USD fields
and returns `SUBSCRIPTION_RUNTIME_NOT_ADMITTED`; it cannot save an API-billing plan or enqueue Real.
Existing Fake planning/execution and historical evidence retain their own identities.

An operator-only protocol double runs the actual frozen CLI in isolated Docker through the existing
single-attempt queue/Worker/H-Lane. A separate network-none controller owns synthetic credentials,
counts/debits requests before transport and refuses reset/retry; Subject receives only Workspace,
and Verifier receives readonly Workspace/hidden assets. These are zero-model-call
`FAKE_CODEX / CUSTOM / synthetic / NOT_ATTESTED` results. Offline protocol compatibility and credential
canary isolation do not establish live subscription credential safety, quota or model access.

A separate copied real engineering task has actual deterministic hidden baseline/oracle admission;
protocol fixture results do not provide that qualification. No existing login state, services,
databases, website or frozen evidence are changed. The trusted live subscription auth boundary,
route/quota observation and all retry/interception paths remain unverified; missing critical controls
must deny. No real account Token is read, live inference/refresh/login/logout performed, extra credits
purchased, production deployment or Phase 3 started. See [scope and first-real requirements](docs/SUBSCRIPTION_EXECUTION.md).
The Phase-1/2 records below retain their original acceptance scope; their older token/USD prerequisite
wording does not govern subscription execution.

## Private local execution — MVP Phase 2 — 2026-10-09

The private `/plans/:planId` journey extends saved plans with **separate one-attempt execution
and budget authorization**, a durable local queue, independent Worker, real isolated Workspace/
Trace capture and independent Docker Verifier. Authorization does not rewrite the plan's
`execution_authorized=false` or any historical Episode. Exact plan/slot/configuration/application/
task/image identities and expiry are rechecked. UUID/one-plan constraints, row locks, leases and
local file locking prevent concurrent redispatch; consumed attempts are never automatically retried.
Valid sealed results can recover into PostgreSQL after a crash; incomplete attempts remain
`INTERRUPTED / NOT_VERIFIED`. Active cancellation confirms termination only after container cleanup.

**Execution is keyless Fake only**, using fixed trusted code and operator-approved isolated clamp
fixtures. The real H-Lane evidence/Verifier path runs, but no real Codex CLI, Provider, model,
user login quota or Judge is consumed. New Episodes are `CUSTOM / synthetic / NOT_ATTESTED`.
`REAL_CODEX` requests are rejected because enforceable live token/USD limits and a separately
authorized provider boundary are unavailable. Zero model calls and $0 model cost are enforced
for Fake; planning USD/tokens remain estimates. Subject process timeout and verifier timeout are
separate limits. Actual live runtime/version/protocol, real task admission and production Worker
operation remain unverified; this does not establish real model quality. Grok is **NOT_CONFIRMED**.

The control API can run non-root/read-only without a Docker socket or process execution privilege;
only the separate Worker needs Docker. Evidence reads check immutable result/Episode, Trace,
Workspace and verifier bindings and reject tampering instead of replacing results. Legacy dual
experiments, read-only Demo, historical identities and the plan-only `/execute` denial remain.
No installation/deployment, existing DB migration, public execution endpoint, complete export or
website publication is claimed. See [execution boundary/setup](docs/LOCAL_EXECUTION.md) and
[actual acceptance](docs/qa/local-execution-phase2-20261009/README.md).

## Private local planning — Phase 1 — 2026-10-10

`/plans` and `/plans/:planId` provide trusted local import/inspection → one compatible Codex
configuration → local preflight → explicit plan-only confirmation → immutable saved-plan reads.
The operator credential stays in component memory; private APIs require the existing local
operator/origin boundary and are disabled in public Demo mode. This is one local operator,
not multi-tenant isolation or remote task upload. Existing dual-configuration experiments remain.

Only server-approved roots and exact task snapshots are accepted; traversal, links, special files,
credential/repository files and bounded size/count violations are rejected. Eligible plans require
operator-trusted existing Custom qualification and baseline-fail/oracle-pass validation, bound to
task/verifier/workspace identities. Structure and hashing are data-only checks; **no new behavioral
validation or source attestation** is claimed. Missing/invalid prior evidence blocks saving.

Preflight binds task/source/Workspace, qualification, registry configuration, endpoint fingerprint,
credential-reference availability, local image ID, application version/code identity, budgets and
one planned attempt. Phase-1-only mode checks local image metadata. With separate execution policy, the API uses an
operator-pinned image ID requiring Worker reinspection; actual CLI/version/protocol and
live Provider health are **NOT_PROBED**. Drift invalidates old preflight; blocked preflight cannot
create a saved plan. Confirmed snapshots persist in PostgreSQL with append-only DB triggers,
concurrent idempotence and restart-readable identities. Current drift does not rewrite originals.

**Plan saving grants no execution.** It creates zero Run/Episode and no paid authorization.
Phase 2 uses the separately authorized Fake queue above; the old plan `/execute` remains disabled.
Existing Codex runner timeout support is recorded as a future Worker requirement; it is inactive
here. Token and USD values are estimates/reference budgets, not hard caps or reserved quota.
The Phase-1 confirm action cannot authorize a later execution. Real task/Provider/Verifier execution,
Worker isolation, cost enforcement and live runtime verification remain outside this delivery.
[Operator setup](docs/LOCAL_PLANNING.md) and [bounded acceptance](docs/qa/local-plans-phase1-20261010/README.md).

## UI evidence reading boundaries — 2026-10-09

Run/experiment lifecycle, individual Trace events, Verifier execution and independent task
acceptance have distinct labels. A FILE_CHANGE event's `completed` status describes that event;
it does not establish run completion, task acceptance or persisted final-workspace change.
Neutral execution completion never substitutes for an independent verdict. Original status enums
and source text remain inspectable in explicit technical disclosures without passive badge focus
stops or duplicated bilingual accessible labels.

Collected task-result counts mean `capability_pass + capability_fail`; infrastructure failures are
separate. Pass/fail counts use existing authoritative filtered totals and consistency guards, not
rounded rates or the currently loaded page. Missing/inconsistent counts remain unreported.
Incomparable and partially comparable raw observations default to a disclosure explicitly excluding
quality/improvement conclusions; full original values and source direction remain accessible.
An access denial cannot establish whether a Run exists: UI 403 feedback stays distinct from a
product 404. Local gateway acceptance does not establish public release readiness or authorize API access.

## Bounded native-hook observation — 2026-10-07

One [operator-observed real Codex case](docs/evidence/real-codex-native-hook-20261007/README.md)
has a completed passive native-hook turn, a digest-bound final workspace, independent **5/5 L0
checks**, and two byte-identical offline replays. `freeze-hooks --allow-pass` permits a neutral
verified observation with independent verification; the failure-only format retains its original
meaning. CUSTOM hook Episodes keep their original `NOT_VERIFIED` acceptance; separately bound
verifier results do not rewrite them. Missing tool exit codes, usage, cost and root cause stay
unknown, and hashes do not attest origin. This bounded case establishes neither general model
quality nor a causal comparison; it adds no automatic execution or repair permission.

## Public demo integrity — 2026-09-30

An explicitly configured `/demo` selects the new `FIXTURE_OFFLINE` bundle and saved run identities.
The configured manifest digest, complete file inventory, database identities, verifier verdicts,
Diagnosis and Regression references must verify before the demo can report ready. Missing/hash/
identity failure returns HTTP 409 with no substitute file or regenerated evidence. Public browsing
requires no Provider credential; configuration and execution writes are disabled. The verifier
artifact endpoint serves only allowlisted, digest-checked fixture stdout, never private native
transcripts. Historical QA integrity failures retain their original records/digests and are labeled
as unavailable, outside the default journey. Public access requires a separate production gate;
local acceptance alone does not establish a ready public deployment.

## Evidence trust boundary — 2026-09-29

The evaluation UI identifies known keyless Fake/fixture experiments as `FIXTURE_OFFLINE` on
experiment, run, diagnosis, and regression surfaces. A persisted `IMMUTABLE_EXPERIMENT` run is a
database/evidence identity, not proof of a real Provider or model call. Provider execution records
remain distinct from frozen historical release evidence, which is outside the current experiment
registry. Other saved execution records remain source-unverified unless provenance is established;
the original record name and bytes remain unchanged; an offline fixture is never presented
as a live model benchmark.

Regression direction uses comparable paired capability observations from common task/repeat slots.
The UI separately presents common-task raw rates and each report's overall raw rate. A
`NOT_COMPARABLE` or `PARTIALLY_COMPARABLE` comparison does not declare improvement or regression.
Direction remains descriptive and never establishes causality or significance by itself.

`FILE_CHANGE` reports a trace event; `No Modification` reports no persisted final workspace change.
The UI describes both when observed. Agent success statements remain separate from the independent
verifier. Downloads contain safe normalized API projections, not hidden native reasoning or private
artifact paths. Core Readiness remains `NOT_READY` while any required check is unresolved. Its READY
rows cite the frozen source identity/version and available timestamp; QA fixture counts do not revise
frozen V6 records. Provider registration, credential presence, runtime health and execution preflight
are separate states.

## Recruiter Demo — Phase S4 冻结范围（2026-09-21）

`docs/recruiter/demo/index.html` 是从 S1–S3 已保存证据导出的只读分享页，不是实时运行界面。
展示同一真实任务的 Codex verified pass 与 Claude Code timeout/NOT_VERIFIED、描述性 Trace Diff、
有边界的 diagnosis、Offline Replay 和已保存的 GitHub CI 验收记录。仅公开字段，不包含凭据、
内部 endpoint、原始 trace/command、源码或隐藏 verifier 资产；导出失败不发布替代结果。
打开页面无外部请求、模型调用、命令执行或 verifier 重跑。S1 仅 2/16 cells，仍 partial/blocked；
不支持能力排名、完整配置比较、普遍效率或 Harness 因果结论。CLI/provider/model/template 差异明确列出。
本地 HTML 与求职资料属于分享准备，不代表私有仓库已公开、网站已部署或招聘者理解度已实测。

SameScale helps an AI Coding developer inspect an engineering failure, follow verified evidence,
separate facts from hypotheses, and review a regression proposal. The initial product continues
the existing HarnessLab P0 Analyst application; S1 updates its external brand and investigation
experience while preserving the S0 development and evidence boundaries.
The GitHub repository is PUBLIC (verified during the 2026-09-30 Git closeout). Product public claims
remain evidence-scoped; repository visibility does not verify public deployment or trusted TLS.

## User journey and evidence

`question → bounded read-only investigation → validated citations → conclusion and limitations
→ human review of a regression proposal → separately authorized validation`

Reports present **conclusion → evidence → limitations/hypotheses → next steps** with keyboard
accessible section navigation and citation return controls. Evidence references
must lead to the corresponding tool data and digest bindings. Unavailable evidence stays unavailable.

| Entry | Supported behavior | Prerequisites and limits |
| --- | --- | --- |
| `/` → `/analyst`: offline Fake | Fixed synthetic deduplication case runs the existing graph and fact validator; 2 decisions, 2 tools, 0 Provider requests | Local API and built frontend; no PostgreSQL, Docker, or credentials; no persistence or model-reasoning claim |
| `/analyst`: historical Real | Reads digest-checked frozen v6 report, proposal, and session summary; shows provenance and effective-limit correction | No new model request or database restoration; original bytes preserved; no resume/approval controls |
| `/analyst/sessions`: current Fake/Real in local/private workspace | Lists and saves current database investigations; bounded resume, cited results, versioned proposal and review-only approval | PostgreSQL, migrations, verifiable experiment evidence; Fake is deterministic; Real additionally needs enabled server/profile, credentials, budgets, and explicit confirmation |
| Advanced evaluation pages | Existing Overview at `/overview`, experiments, Registry, Matrix, JudgeLab, diagnosis, regression, and settings remain accessible | Existing component prerequisites and backend authority continue to apply |

Public Demo is read-only. Persistent Analyst sessions are available only in a local/private
workspace. The public home and sessions pages show the evidence story, Offline Fake demo and
historical Real read-only report as alternatives; they do not offer session creation, Real
execution, resume, proposal saving or approval. The server rejects session mutations with
`403 / PUBLIC_DEMO_READ_ONLY`. Only the exact `POST /api/workbench/analyst/examples/offline`
endpoint is additionally allowed for bounded fixed Fake computation: no database/artifact writes,
Provider requests or external network calls. This does not grant general POST permission.

Core Readiness labels `REAL_JUDGE_SMOKE` as **Frozen release snapshot**. JudgeLab labels it as
**Current JudgeLab registry**, derived by the backend from digest/identity-validated completed
reports across the registry, independent of pagination. No current report means `NOT_RUN`;
unverifiable completed evidence means `NOT_VERIFIED` unless another verified smoke report exists.
The release snapshot and the current JudgeLab registry are different evidence scopes.

Real failure must not silently fall back to Fake. Creating a session, reading it, preflight, and
approval do not invoke a model. Resume can make a paid call only within current authorization.
Changing scope or failing to load a newly selected session clears stale controls/results.
Registry failure must not prevent otherwise available Fake sessions or the standalone offline demo.
Loaded examples receive focus; failed example loads remove stale results and offer explicit retry.
Saved investigations show scope selection and current results with new-session setup collapsed.
Proposal review is separately expandable; collapsing a panel does not change the saved state.

Approval binds scope and exact proposal content and keeps `execution_authorized=false`. A reviewer
label is not authenticated identity. Saving a plan does not execute Replay, repair code, or prove
that the suggested regression passes. Recovery preserves spent budgets; it is not a distributed
exactly-once guarantee or a native LangGraph PostgreSQL Checkpointer claim.

## Claims and exclusions

- Deterministic L0 > human gold L1 > LLM Judge L2. Keep Official and Custom evidence distinct;
  model-generated conclusions are accepted only within host-validated evidence contracts.
- The frozen real smoke proves one bounded Analyst vertical slice. Its original database session
  has not been restored. The successful v6 session did not select `inspect_trace`; do not attribute
  other sessions' traces to it. See [original evidence](docs/evidence/REAL_AGENT_SMOKE_20260909.md).
- Synthetic demonstration, historical observation, current persisted execution, and controlled
  causal evidence are different claims. P0/S1 does not establish general model rankings, Harness
  uplift, reasoning-effort gains, or a new controlled causal result.
- Unknown usage/cost/root cause stays unknown. `NOT_RUN` and `NOT_VERIFIED` are not success.
- Observe import, cross-Episode diagnosis, automatic repair/execution, SaaS authentication/RBAC,
  billing, public hosting, and human ownership completion are not S1 deliverables.

## Compatibility and change control

SameScale is the external product name in the shell, route titles, browser metadata, and current
README entry. HarnessLab remains the implementation and historical identity. Visual v1 navigation
contains investigation entry, Public Demo, saved sessions, experiments, diagnosis and regression;
other tools remain in an expandable advanced area, automatically expanded on their direct routes.
Run evidence navigation is bound to an actual run context. No route is removed or renamed.
Visual v1's five core pages and shared Shell support zh-CN (default) and en-US. The local
2026-10-09 UI closeout candidate extends this interface locale to Experiments list/detail;
other advanced pages retain their existing locale implementation. Locale switching translates
interface copy and exact checked code labels, not evidence bytes, IDs or backend summaries.
Checked backend guidance can have a labeled Chinese explanation with its source text retained.
Unknown source strings remain unchanged. Machine states remain inspectable through explicit
technical disclosures, exact-value copy actions and original evidence; passive badges do not add
focus stops or duplicate bilingual labels. Lifecycle completion is
separate from task verification and does not use task-pass presentation. The second local closeout
keeps full technical identities in disclosures/copy actions while names and peer-distinguishing keys
serve as interface labels. Search, routes, references and downloads continue to use original identities.
Historical Real overviews are bounded projections of exact checked assertion fields, with the source
report retained; free-form summaries are not interpreted as source authentication or causal proof.
The candidate is authorized for PR review. Grok's final independent reassessment and final human
visual acceptance remain unconfirmed; branch publication does not establish deployment.
Top-level CLI help and API documentation display SameScale with an explicit HarnessLab compatibility
note. Package-version help, technical identifiers, and historical/evidence text retain their identity.
S1.5 integrates the accepted work into `main` and renames the existing private GitHub repository
in place from `a27497/harnesslab-ai` to [a27497/samescale](https://github.com/a27497/samescale).
The canonical Git remote is `git@github.com:a27497/samescale.git`; repository identity, privacy,
Git history and historical tags/evidence are retained. The additive `samescale` CLI is still a
future S2 deliverable; use the compatible `harnesslab` executable today.
Preserve the `harnesslab-ai` Python distribution,
`harnesslab-workbench` npm package, `src/harnesslab`, `harnesslab` CLI, `HARNESSLAB_*` environment
variables, API paths, database schema/migrations, task/profile/session IDs, and artifact digests.
The P0 home-route change is recorded above; it is not an API or data migration.

Future product changes must update this contract only after checking source, focused tests, and
the evidence required by the claim. Historical contracts and immutable reports retain their own
scope. Plans belong to [Project Blueprint](docs/PROJECT_BLUEPRINT.md), and current verification
belongs to [Current Milestone](CURRENT_MILESTONE.md).
