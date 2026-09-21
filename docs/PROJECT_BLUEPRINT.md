# SameScale Product Project Blueprint (HarnessLab-compatible)

## 当前授权：Phase S4 — Recruiter Demo + Job-search Freeze（2026-09-21）

复用 S1–S3 真实历史 evidence、既有 Offline Replay/CI 和单文件离线 HTML 模式，交付
3–5 分钟的 task → configurations → result → Trace Diff → diagnosis → replay → CI 路径。
导出显式筛选的公开字段；提供 README Engineering Highlights、演示脚本、面试材料与简历事实。
验收要求来源完整性、公开投影边界、必要测试与桌面/手机本地 Demo 验收；需要时仅 scoped
commit/push 当前 feature branch 并核验实际 SHA 的 CI。不得新增 Provider/model/Claude/Judge 调用。
保留 dirty work 与历史 evidence；S1 partial/blocked，S2/S3/S4 complete 后进入求职冻结并 STOP。
不规划 S5，不继续新功能，不 merge main、不 deploy。以下为历史阶段上下文，不自动启动。

## 当前授权：Phase S3 — CI Regression Integration（2026-09-21）

将 S2 Offline Replay + Trace Diff 接入普通 GitHub push/pull_request CI，本地与 CI 使用同一
入口和合同。冻结 representative evidence 与已观察到的输出；对 evidence/digest drift、
replay inconsistency、trace/schema/parser、changed-files attribution 和 failure taxonomy
回归 fail closed。回归无网络、无凭据，不执行 Provider/model/Claude/Judge/真实 benchmark。
验收要求本地回归 PASS、实际 pushed SHA 的 GitHub CI PASS、S3 final report 与 CURRENT_MILESTONE。
仅授权当前 feature branch 所需 scoped commit/push；保留 dirty work 与历史 evidence。
不做 S1 能力排名/完整比较，不 PR、merge main、deploy；完成 S3 后停止，不进入 S4。
下方阶段授权和旧产品阶段命名仅为历史上下文，不扩大本次 CI 集成范围。

Planning authority: **HL-BLUEPRINT-2026-09-05**, the user-supplied authoritative blueprint and
first-application delivery contract, amended by the **2026-09-09 SameScale macro-route freeze**
below. The user's latest explicit decisions govern scope.
[Current Milestone](../CURRENT_MILESTONE.md) records live state and the stopping point;
[Project Status](PROJECT_STATUS.md) retains P0 and real-smoke evidence;
this document defines goals and acceptance, not completion or execution authorization.

The [2026-08-25 phase map](FINAL_BLUEPRINT_PHASE_MAP_2026-08-25.md) is historical reference.
Its K-B4 or sequential M-S roadmap does not override this route. Preserve historical phase records
and evidence rather than rewriting them to match a new product description.

## SameScale Product S0 amendment — 2026-09-09

The S0 user request authorized a bounded start of SameScale productization from existing P0.
Reuse the current repository, feature branch, and dirty P0 implementation; do not initialize Git
or rebuild Core. This amendment supersedes only the older deferral of SameScale for S0.

S0 acceptance: inspect Git/worktrees and preserve user work; verify P0 offline/history/current-session
boundaries; establish root AGENTS, CURRENT_MILESTONE, PUBLIC_PRODUCT_CONTRACT, and a discoverable
repo-local `samescale-product` Skill; reconcile entrypoint documentation; retain frozen evidence and
HarnessLab runtime compatibility; run focused keyless checks; then commit and push the current
feature branch as explicitly requested. Verification results belong to CURRENT_MILESTONE.

SameScale is the product direction; the [public contract](../PUBLIC_PRODUCT_CONTRACT.md) freezes
the supported P0 claims and naming boundaries. S0 does not include global rebranding, a new runtime,
new paid campaigns, database restoration, public launch, merge, or implementation of S1 onward.
The first-application and architecture constraints below remain applicable within that scope.

## SameScale Product S1 amendment — 2026-09-09

The S1 request authorized implementation, tests, Browser QA, and commit/push of the existing
feature branch. This superseded S0's branding deferral for the following surfaces.

- Present SameScale in the application shell, browser metadata, CLI/API display descriptions, and
  current README entry. Preserve
  HarnessLab CLI/package/env/API/schema identities and historical evidence bytes.
- Make investigation entry and saved sessions the primary navigation; keep evaluation routes in
  an expandable advanced area that opens on direct evaluation navigation.
- Give new users a clear offline starting point, separate historical Real and current Fake/Real
  entries, explicit loading/error/retry states, and focus moved to the loaded result.
- Refactor the shared report into navigable conclusion, verified evidence, limitations/hypotheses,
  and next steps. Citations reveal exact tool data/digests and return to their originating fact;
  absent references stay unavailable.
- Separate current-session selection, new setup, progress/results, and proposal review. Preserve
  existing backend calls, frozen budgets, Real confirmation, stale-state clearing, and review-only
  approval bindings. No new runtime or database migration.
- Accept with frontend regressions/build, focused Analyst/compatibility contracts, disposable
  PostgreSQL checks, and desktop/mobile Browser QA of the built local app. Label browser fixtures
  separately from real API/database verification.

Results belong in CURRENT_MILESTONE. That authorization stopped after S1; it did not authorize
main integration, repository rename, later stages, new campaigns, deployment, or tags.

## SameScale macro-route freeze — 2026-09-09

This amendment owns the forward product sequence and supersedes conflicting older roadmap/NEXT
text. The current request authorizes **planning, documentation checks, and commit/push of the
existing feature branch only**. S1.5 and S2 execution is not authorized by this plan.
S0/S1 acceptance is recorded in CURRENT_MILESTONE and its linked Git history.

| Stage | Scope | Exit target |
| --- | --- | --- |
| S0 | Codex-native development environment and P0 baseline | Stable development foundation |
| S1 | SameScale external brand and core investigation UX | Recognizable SameScale product and evidence journey |
| S1.5 | Mainline integration and SameScale canonical identity | S1 integrated into `main`; prepare and execute the existing repository's `harnesslab-ai` → `samescale` rename, with verified identity continuity |
| S2 | **Local Productization & Developer Experience** | `samescale` CLI with `demo/up/status/doctor/down`; a simple, verified first-use path to a keyless local demo |
| S3 | Restricted public Demo | `demo.getsamescale.com` safely exposes an explicitly bounded demo experience |
| S4 | Portfolio / Release closure | Website → Demo → cited investigation result forms a coherent, recruiter-ready delivery |
| P1 | Minimal real engineering evidence input / Observe | Investigate one imported development Episode beyond existing experiment evidence |
| P2 | One read-only external connector | Prefer GitHub; use MCP as the connection protocol only if needed |
| Later | SSE / RAG / MCP extensions and other capabilities | Add only for a concrete JD or demonstrated user need |

**Observe is P1, not S2.** S1.5 → S2 → S3 → S4 precedes P1 → P2. This order freezes
scope, not dates or permission to start the next stage. Historical Phase P/S and M–S labels are
separate capability-map identities. Do not reinterpret their evidence as these product stages.

### Source basis and remaining product gaps

The S1 source baseline is commit `0c6c6c9be89f22fe2e8f345a7d6e84720bb609f3`.
These are source observations, not new execution/acceptance results:

| Existing implementation | Implication for the next stages |
| --- | --- |
| [CLI registration](../pyproject.toml) exposes only `harnesslab`; [CLI](../src/harnesslab/cli.py) already wires `up/status/doctor/down/serve` | S2 adds a compatible `samescale` entrypoint and a demo command; it reuses the existing lifecycle rather than building another runtime |
| [Lifecycle](../src/harnesslab/productization/lifecycle.py) selects a trusted Compose manifest, waits for services and endpoints, and preserves volumes on shutdown | Extend existing startup/diagnostic contracts; protect current project/volume identities and arbitrary-working-directory trust boundaries |
| [Compose](../docker-compose.yml) and [product image](../docker/product/Dockerfile) supply PostgreSQL → migrations → FastAPI plus built Vue, with loopback host ports | Full local product startup already has a base; S2 must prove installation and lifecycle from a fresh environment |
| [Showcase](../src/harnesslab/analyst/showcase.py) supplies synthetic offline Fake and digest-checked historical Real; [static serving](../src/harnesslab/api/static.py) discovers a source/container frontend build | DB-free investigation exists, but there is no `demo` launcher; a source build is not proof that an installed wheel contains a usable standalone UI |
| Wheel metadata embeds frontend sources and a trusted Docker build context | Verify the installed artifact outside the checkout; do not mistake bundled source for compiled demo assets |
| [Router](../frontend/src/router/index.ts) sends `/` to `/analyst`; current sessions still require database evidence | Preserve the S1 entry/report journey and explain which paths need the full product |
| [Fresh setup script](../scripts/verify_fresh_setup.py) distinguishes preflight from actual Actions reproduction | A successful preflight cannot satisfy S2's real clean-environment startup acceptance |

### S1.5 — Mainline integration and SameScale canonical identity

Scope is delivery/identity continuity, not new investigation behavior. Canonical product name is
**SameScale**; the target repository is `a27497/samescale`, continuing `a27497/harnesslab-ai`.
Repository slug and current distribution URLs may change in this stage. Python distribution
`harnesslab-ai`, npm package `harnesslab-workbench`, `src/harnesslab`, `harnesslab` CLI,
`HARNESSLAB_*`, API/schema/migration identities, Compose project/volumes, task/profile/session
identities, frozen tags and evidence remain compatible. The additive `samescale` CLI belongs to S2.

| ID | Acceptance criterion | Required evidence |
| --- | --- | --- |
| S1.5-1 | Prepare an integration and rename inventory against current remote `main` and the S1 feature branch: divergence/conflicts, active URLs, badges, CI/release links, clone instructions and local worktree/remotes. Classify current references versus immutable historical identities; define forward changes and rollback steps. | Exact input SHAs, scoped change list and compatibility/rollback record; no global replacement or repository recreation |
| S1.5-2 | Integrate accepted S1 and this route into `main` with Git history preserved. Resolve conflicts without discarding existing main work or changing the accepted S1 boundaries. | Recorded integration commit; accepted S1 SHA remains an ancestor; remote `main` matches the recorded result; required CI on that result passes, separately from local checks |
| S1.5-3 | Execute the existing repository rename to `samescale` within the later authorized S1.5 task. Keep repository visibility and access scope unchanged. Update active canonical references and the authorized local remote; preserve old evidence URLs/text. | Same repository identity before/after; canonical clone/fetch succeeds; old URL behavior is checked and reported, not assumed; main/history/tags and relevant PR/issue/CI links verified after rename |
| S1.5-4 | Reconcile current README/product contract/setup references with the canonical repository identity and explicit HarnessLab compatibility. Other worktrees are inventoried and handed off, not moved/deleted or rewritten as cleanup. | Link/reference audit and exact scoped diff; unchanged package/env/API/schema/volume/evidence identities; rollback instructions preserve history and data |
| S1.5-5 | Verify the integrated tree's S1 entry/report and compatibility before declaring integration accepted. | Focused Analyst/showcase/CLI/distribution/CI contracts; frontend tests/build; desktop/mobile smoke of offline/history and saved Fake review using disposable PostgreSQL where required; frozen bytes checked against the accepted S1 baseline |

Preparation alone may be recorded as **PREPARED**. If merge, rename, access or required CI is
unavailable, retain the concrete blocker and mark the corresponding acceptance **NOT_RUN** or
**NOT_VERIFIED**. S1.5 is accepted only when both main integration and canonical rename are
verified. Do not start S2 automatically. No tag, public launch, package-wide rename, new campaign,
or historical evidence rewrite is part of this stage.

#### Prepared integration and rename procedure

Use the existing `codex/l-real-agent-main-integration` branch as the candidate, retaining all
five accepted commits from the original main baseline through the route freeze. The integration
includes the preceding Real Analyst/P0/S0 work, not just S1 display changes. The dated
[preparation evidence](evidence/SAMESCALE_S15_PREPARATION_20260909.md) records exact inputs and
verification; CURRENT_MILESTONE records whether the external steps have actually occurred.

1. Commit/push the preparation handoff on the feature branch and obtain passing CI on that exact
   head. Re-read remote main and candidate before creating a PR; if either changed, reassess the
   affected delta. Use a normal merge commit into `main`, preserving the accepted S1 ancestor;
   do not squash, rebase published history, force-push, or delete the source branch.
2. Verify the merged remote main SHA and its CI. Leave the other worktrees' local branches/files
   intact; the existing main worktree may remain behind remote main until its owner updates it.
3. Rename the existing private repository to `a27497/samescale` without changing its owner,
   visibility, access policy, default branch or numeric repository identity. Verify canonical
   API/Git access and old-URL behavior; do not recreate or transfer the repository. Preserve tags,
   issue/PR history and original Actions run identities.
4. Reconcile active README/public-contract/current-handoff references and clone instructions with
   the verified canonical URL. Retain `harnesslab-ai` in Python metadata, all historical documents
   and frozen source/evidence. The existing historical CI link in FIRST_APPLICATION remains a
   historical reference; verify its accessibility instead of rewriting its evidence identity.
5. Update `origin` to `git@github.com:a27497/samescale.git` and verify fetch/readback. Git remote
   configuration is shared across these linked worktrees: disclose that effect, but do not rename
   their directories, switch/reset their branches, or clean their files. Reconcile the small
   canonical-document follow-up through the same reviewed feature-branch/merge path and check
   its exact main CI before marking S1.5 accepted.

Rollback is forward and evidence-preserving: on pre-merge failure, keep main unchanged and correct
the candidate; on post-merge regression, use a reviewed revert of the recorded merge commit and
its dependent documentation, never reset published main. Do not downgrade any historical database
as an automatic rollback. If rename validation fails, retain the verified repository ID and restore
the old slug/remote only if available and authorized; otherwise record the actual accessible URL
and blocker. Keep all existing commits, tags and data throughout recovery. No speculative cleanup
or repeated unchanged retry is part of this procedure.

### S2 — Local Productization & Developer Experience

The minimum supported acceptance environment is a fresh Linux environment using the locked
Python/uv versions; the full stack additionally uses local Docker Engine and Compose v2. Document
other platforms as verified only after actual checks. First dependency installation may need
network access. Keyless means no Provider/Judge credentials or calls, not zero installation
prerequisites. No dependency upgrade or new framework is required.

Choose two explicit modes using the existing API, Vue UI and lifecycle:

- **First-use demo:** after one documented installation sequence, `samescale demo` starts a
  loopback API plus compiled frontend and prints a working investigation URL. It runs the existing
  synthetic offline case without Docker, PostgreSQL, keys or persistence. Historical Real remains
  a separate digest-checked read-only record. DB-backed saved investigations explain their
  prerequisite. Ship/resolve the built assets for the installed artifact; do not require users to
  run Vite, build Vue manually, or recover the developer checkout to launch this mode.
- **Full local product:** `samescale up` reuses the trusted Compose graph for PostgreSQL,
  migrations and the bundled API/UI. Host Node/Java/Alembic/frontend build commands are not required
  for this path; locked builds run inside Docker. It does not seed or reconstruct historical
  Real sessions or silently start an investigation.

The following table is a **target command contract**, not a claim that these commands exist today.

| Command | Acceptance behavior |
| --- | --- |
| `samescale --help/--version` | Install an additive entrypoint into the existing CLI; expose `demo/up/status/doctor/down` and preserve legacy commands/options/version identity through `harnesslab` |
| `samescale demo` | Report startup progress and actual readiness, default to loopback, serve `/` → `/analyst` and deep-link refresh; clearly report nonpersistent synthetic data and zero Provider/Judge calls; Ctrl-C shuts down its foreground server |
| `samescale up` | Validate prerequisites/configuration, build or use the selected image, migrate and wait with bounded timeouts; print success and URL only after PostgreSQL, migration, API health and UI readiness pass; repeated startup preserves data |
| `samescale status` | Distinguish demo availability from full-stack stopped/partial/ready/failed state; report checked mode/endpoint and truthful exit status; do not mutate services or invoke models |
| `samescale doctor` | Offer a documented demo-specific check as well as full-product diagnostics; absent Docker/database cannot fail a healthy standalone demo; explain failed prerequisites and the next corrective command without printing secrets |
| `samescale down` | Stop only the selected managed full stack, retain database/artifact volumes, succeed repeatably, and document foreground demo shutdown; never kill an unrelated process on the same port |

Keep `/api/health`'s existing database round-trip semantics; DB-free demo readiness must check its
own UI/showcase path rather than turn a failed database check into a pass. Legacy lifecycle defaults
continue to address the existing `harnesslab` Compose project and volumes; a new executable name
must not make current data appear lost by silently selecting a new project.

| ID | Acceptance criterion | Required evidence |
| --- | --- | --- |
| S2-1 | One current README installation/start path leads to the first demo using the installed artifact from outside the source checkout. No manual frontend build, undocumented absolute path, Codex plugin, `.env` secret or local developer cache is required. | Exact source/artifact identity, prerequisite versions and commands from a disposable clean environment; first-start timing recorded without an invented performance claim |
| S2-2 | Both entrypoints satisfy the command contract; demo and full-stack readiness remain distinct. | Focused CLI/lifecycle tests, installed-wheel entrypoint/assets checks, existing API/static/Analyst contracts; errors and exit codes documented and asserted |
| S2-3 | Actual browser use completes offline demo → conclusion → citation/source → limitations/next steps, with reload and desktop/mobile layout. Historical Real stays distinct; inaccessible DB paths explain setup; no Fake/Real relabeling. | Browser evidence against the built installed product, not mocked success responses; no database or Docker required for the standalone demo check |
| S2-4 | Actual full-stack lifecycle passes first `up`, repeated `up`, `status`, `doctor`, `down`, repeated `down`, and restart. A disposable persisted Fake investigation and its review state survive restart. | Isolated Compose project/ports/volumes; migration head, real endpoint/UI checks and before/after session identity; no historical/demo business database fixtures |
| S2-5 | Missing/unsupported prerequisites, Docker stopped, port collision, invalid config, missing/corrupt UI assets, build/image-pull failure, migration failure and readiness timeout produce bounded failure and a useful recovery step. Correction followed by retry succeeds; stale success or raw credential-bearing stderr is never displayed. | Focused failure tests with injection labeled; actual port-collision/retry and stop/restart smoke; explicit distinction between configuration/not-running exit `2`, operational failure exit `1`, and success exit `0` |
| S2-6 | Default lifecycle/demo cannot use ambient provider credentials, expose private diagnostics, execute an untrusted CWD Compose/`.env`, remove data volumes or start Real/Harness/Judge work. | Existing trust/isolation and keyless contracts plus tests for the added launcher; observed zero model requests, not merely a printed `PROVIDER_CALLS=0` string |
| S2-7 | Documentation and public contract reflect only verified delivered behavior. | Focused distribution/lifecycle/CLI/API checks; frontend tests/build and Browser QA where changed; fresh-environment evidence above; CURRENT_MILESTONE records pass/failure/NOT_RUN separately from exact-head CI |

Extend [existing lifecycle tests](../tests/test_product_lifecycle.py),
[distribution tests](../tests/test_product_distribution.py), and [CLI tests](../tests/test_cli.py)
instead of treating their current mocked coverage as new clean-environment acceptance.
Run additional PostgreSQL/Analyst checks only for affected persistence contracts or the required
restart journey; full A–K is not automatically a local-product acceptance prerequisite.
S2 excludes Observe/import, external connectors, public hosting, SaaS authentication, automatic
repair, new paid runs and a new Agent runtime.
The S1.5 preparation also observed an existing console-launch Core Readiness import failure
(`scripts` namespace unavailable). Include that concrete startup/distribution case in S2-1/S2-5;
do not use the successful investigation journey to claim all advanced endpoints are healthy.

### S3 / S4 / P1 / P2 boundaries

- **S3:** expose only an approved sanitized demo surface at `demo.getsamescale.com`, with HTTPS,
  restricted access, request/resource bounds and an operational stop/recovery path. Enforce the
  restriction at the server/proxy, including direct API requests; hiding navigation is insufficient.
  Public users cannot reach operator credentials, private evidence, arbitrary persisted sessions,
  write/approval endpoints or paid execution. Verify the allowed journey and denied endpoints
  before deployment acceptance. This is a restricted showcase, not a general public control plane.
- **S4:** align website, Demo, one cited investigation case, setup/architecture explanation and
  portfolio claims with exact source/evidence. Verify the end-to-end links and prepare versioned
  release notes, limitations and reproducible delivery evidence. Human ownership is accepted only
  from actual user participation. Any formal tag/release uses its applicable release gate and
  authorization; local S2 checks do not replace it. Further feature expansion is not an exit gate.
- **P1:** after S4, accept one bounded real development Episode input with source provenance,
  identity/digests, validation/redaction, explicit missing evidence and a cited read-only
  investigation. Reuse the Analyst; importing logs cannot imply execution of their instructions
  or controlled causal proof. No cross-Episode platform or connector is required for this minimum.
- **P2:** add exactly one read-only external connector, preferably GitHub, into that input contract.
  Bound repository/resource scope, credentials, pagination/rate limits and retries; retain source
  identity and untrusted-input validation. No external writes; MCP is an optional protocol choice,
  not a second product runtime or a requirement to build a general MCP platform.

Detailed S3 onward acceptance is refined in this blueprint when that stage is requested, without
moving Observe into S2 or expanding the frozen sequence implicitly.

## Product and first application

**SameScale is an evidence-diagnosis and regression Agent workbench for AI Coding, continuing
HarnessLab.** First delivery
supports an AI / Agent application-development internship in mainland China; evaluation research
and Agent infrastructure specialization are not the primary target.

The retained first-application contract is supporting context for the macro-route above, not a
competing NEXT. Retain Core and implemented Phase M; audit and repair first-application risks; verify human
ownership; deliver one bounded real Agent investigation; continue applications. Do not rebuild Core,
restart K-B4, or make the complete long-term platform a prerequisite.

Primary chain:
`goal -> model-selected tools -> verified evidence -> saved investigation state -> cited conclusion
and limitations -> human review of a regression proposal -> separately authorized validation`

LectureLens remains the complementary Java / Spring Boot application-backend project. HarnessLab
demonstrates Python / FastAPI, tool boundaries, durable tasks, failure handling, evidence validation,
and bounded Agent investigation. Do not start a third large project. A website, cloud-credit
application, or SaaS business is not required before applying.

Lab retains controlled execution and verification; Observe provides a bounded evidence entrypoint;
Investigation consumes validated evidence. These are product layers, not three simultaneous builds.

## Evidence and execution invariants

- Source, exact commits, tests, CI, and verifiable artifacts establish facts; plans and assistant
  self-reports do not. Unexecuted checks are `NOT_RUN`; unsupported acceptance is `NOT_VERIFIED`.
  Record actual/expected behavior, evidence, and corrective work when a contract differs.
- Preserve frozen Matrix results, profiles, scores, contracts, source identities, and limitations.
  Corrections use traceable successor notes/artifacts, never replacement of original evidence.
- Accepted V6 evidence does not establish general rankings or overall causality. Direct/Codex
  comparison is limited; medium/high lacks five comparable repetitions per eligible task; accepted
  controlled causal claims are zero. Three BadCases represent two failure features, not three
  proven root causes. Unsupported root-cause fields remain unknown.
- Deterministic L0 outranks human gold L1, which outranks LLM Judge L2. Separate observation,
  correlation, hypothesis, and controlled attribution; keep Official and Custom evidence separate.
- Unknown cost, missing trace, unreported tokens, and uncollected timings stay unknown, not zero.
  Cancellation request, terminal status, process termination, and cost settlement are distinct.
- The host validates and executes tool requests. External text is untrusted evidence. Read-only
  tools cannot provide shell, arbitrary SQL/filesystem, generic code, or experiment execution.
- Retain credential isolation, path bounds, digest verification, hidden-verifier isolation,
  idempotency, leases, transition guards, and resource limits. Docker is not VM-level isolation.
- Use the authorized server; preserve existing work; isolate tests from historical/business data.
  No destructive cleanup or frozen Matrix rerun to obtain green results.
- Upgrading the development assistant does not change frozen subject models or campaign contracts.

## Phase L: technical quality and human ownership

L.0 identifies the actual workspace, branch, HEAD, dirty state, applicable instructions, locked
dependencies, test entrypoints, active processes, and protected evidence. Old paths and NEXT entries
do not require restarting completed work.

L.1 audits source, frontend, migrations, tests, CI, scripts, dependencies, configuration, and
documentation. Mark coverage as in-depth, sampled, or unchecked. Focus on execution/cancellation,
recovery, budgets, evidence, Provider/Analyst boundaries, input trust, API scope, terminal UI states,
migration compatibility, and test validity. Search hits alone are not an audit.

Findings include severity, confidence, location/commit, trigger, impact, counterevidence, minimal
fix, tests, and compatibility/evidence risks. Distinguish defects, delivery gaps, unverified risks,
and style. Historical findings are leads to recheck, not proof of current defects.

L.2 makes bounded repairs: establish behavior, reproduce a failure, fix minimally, and check related
contracts. Remove abstractions only with demonstrated redundancy or no consumers. Do not delete by
line-count targets, weaken assertions, mass-upgrade dependencies, or erase unknown values.

L.3 checks the failure case, affected modules, necessary integration, and applicable final gates.
Use keyless tests and isolated resources. A distinct review pass considers counterexamples;
same-model review is not statistical independence. Keep historical bytes/digests stable where
compatible; document corrected behavior with an explicit contract or correction record.

L.4 is **human ownership**, accepted separately from technical completion. The user must explain
the execution/evidence/Agent chains, participate in at least one test and core repair, explain a
rejected alternative, and adapt a test or locate code under a new boundary condition.

Use three small learning checkpoints: A, predict the behavior contract; B, participate in a failing
assertion and choose an approach; C, explain the change and apply it to a new case. Record concrete
human contributions and AI assistance. Documents, approvals, and memorization do not replace this.
Use one concept and a small code excerpt per step.

Phase L exits when first-application high-risk issues are fixed or explicitly isolated, regressions
are evidenced, one human-participated repair passes explanation and transfer, and remaining debt
is understood. There is no requirement for a perfect repository.

## Real Agent delivery

### Read-only investigation

Reuse LangGraph, the existing Provider boundary, and six tools: `query_runs`, `compare_cells`,
`inspect_trace`, `inspect_failure`, `get_task_contract`, and `get_ablation`. Keep Fake for deterministic
tests; real mode is explicit and never silently falls back to Fake.

The model selects actions using the question and returned evidence. Validate structured arguments,
return values, scope, facts/citations, timeouts, failures, and abstention. Global starting ceilings
are 8 decisions and 12 tools, with lower frozen session limits allowed. Record real-run request,
token, time, and cost bounds before spending. Longer trajectories are not evidence of quality.

### Recovery and minimal review

Persist goal, scope, evidence references, completed actions, remaining limits, and pause position
using existing PostgreSQL and the investigation graph. Recovery cannot reset budgets or silently
repeat completed/ambiguous actions. Do not claim distributed exactly-once processing.

The implementation uses application-managed PostgreSQL session journals around LangGraph nodes,
not a native LangGraph PostgreSQL Checkpointer. Verify the mechanism through recovery behavior;
do not introduce another workflow system solely to change its label.

The minimal side effect is saving a versioned regression proposal or safe snapshot reference after
review. Host code binds approval to user/operator scope, exact content/digest, snapshot, and valid
state. Changed content invalidates approval; repeated confirmation cannot duplicate plans.
An unverified reviewer label is not authenticated identity and must be disclosed as such.

Actual regression execution is a separate scope with visible counts, costs, risks, authorization,
and isolated execution. Saving a plan is not executing Replay.

### Case, interface, and acceptance

Use one verifiable engineering failure case showing provenance, tools, facts, unknowns, proposal,
and review. Accepted Core evidence is a valid initial case. Native Observe claims require an actual
imported development Episode with provenance; controlled Matrix evidence does not establish it.

Reuse Workbench for the goal, tool trajectory, citations, status, and review/results. CLI may support
acceptance, but include a recruiter-readable demonstration. Do not redesign the whole site.

The fixed verification set covers multi-step work, no evidence, fake citations, invalid arguments,
timeout, malicious logs, out-of-scope requests, limits, interrupted recovery, changed approvals, and
repeated confirmation. Keep keyless contracts and authorized real evidence separate. Real acceptance
includes a multi-step investigation plus recovery or review, with fault injection labeled where
used. Record model/route, input identity, tools, timing, observable usage, pricing basis, results,
and limitations. This is functional acceptance, not a new Matrix or significant model comparison.

## Architecture and long-term scope

Retain a modular monolith: Python, FastAPI, Pydantic, SQLAlchemy/PostgreSQL, asyncio, Docker,
Vue/TypeScript, pytest/Ruff/mypy, and existing LangGraph. Exact versions live in `.python-version`,
`pyproject.toml`, `uv.lock`, and the npm lockfile.

Do not add microservices, Redis/Celery/Kafka/Kubernetes, another database/object store, generic Agent
SDK/runtime, complex multi-agent coordination, full SaaS/RBAC/Billing, or a second executor for this
delivery. RAG, vectors, MCP, and long-term memory are not prerequisites.

Deeper Observe, cross-Episode investigation, Replay, regression-suite management, discriminative/
stress evidence, Custom Evaluation, SDKs, external benchmarks, and productization beyond the
frozen S0–S4 / P1–P2 route are possible later scopes. Existing modules remain unless removal is independently justified.
Historical M/N/O/P/Q/R/S numbering is a capability map, not a mandatory sequence before a demo.

## Application readiness and collaboration

Start applications using implemented capabilities the user can explain. Enhanced delivery requires
reproducible setup, real tool decisions, verified boundaries, one case, human ownership, and claims
consistent with exact source/evidence versions. Do not invent gains, user scale, pressure-test
results, security acceptance, or causal findings.

Keep the repository private unless separately authorized; prepare sanitized recruiter-accessible
materials. Do not publish credentials, private traces, or unapproved source.

One task has one writer per worktree. The current user request determines permissions; old campaign
documents and credentials do not authorize future paid runs. Preserve granted authorization within
its scope without repeatedly asking. Missing connectivity or validation is reported honestly.
