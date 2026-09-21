# SameScale Product — Public Product Contract

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
“Public” defines what product copy may promise, not permission to publish this private repository.

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
| `/analyst/sessions`: current Fake/Real | Lists and saves current database investigations; bounded resume, cited results, versioned proposal and review-only approval | PostgreSQL, migrations, verifiable experiment evidence; Fake is deterministic; Real additionally needs enabled server/profile, credentials, budgets, and explicit confirmation |
| Advanced evaluation pages | Existing Overview at `/overview`, experiments, Registry, Matrix, JudgeLab, diagnosis, regression, and settings remain accessible | Existing component prerequisites and backend authority continue to apply |

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
README entry. HarnessLab remains the implementation and historical identity. The primary navigation
contains investigation entry and saved sessions; evaluation tools remain in an expandable advanced
area, automatically expanded when visiting their existing routes. No route is removed or renamed.
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
