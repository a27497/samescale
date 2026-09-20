# SameScale

SameScale is an **evidence-diagnosis and regression Agent workbench for AI Coding**, built on
reproducible Model × Harness × Judge execution and verifier-backed evidence.

SameScale Product continues the existing P0 Analyst application in the canonical private repository
[a27497/samescale](https://github.com/a27497/samescale), renamed in place from `a27497/harnesslab-ai`.
Git history, package/CLI names, configuration, and historical evidence retain HarnessLab compatibility.
S1 presents SameScale in the application shell and makes investigation entry, cited reports, and saved sessions the primary
experience. The runtime and existing evaluation routes remain compatible.

Clone the canonical repository with an account that has access:

```bash
git clone git@github.com:a27497/samescale.git
cd samescale
```

The supported executable is still `harnesslab`; the additive `samescale` CLI and `demo` launcher
belong to S2 and are not implemented yet. Existing checkout directories can keep their names.

## Codex development entry (source checkout)

Read root `AGENTS.md`, `CURRENT_MILESTONE.md` (live scope/results), and
`PUBLIC_PRODUCT_CONTRACT.md` (supported behavior/claims). Plans remain in Project Blueprint;
Project Status preserves the earlier P0 and real-smoke evidence.

The repo-local Skill is `.agents/skills/samescale-product/SKILL.md`. From this checkout, invoke
`$samescale-product` with a bounded task. Its location follows the
[official Codex skill discovery convention](https://learn.chatgpt.com/docs/build-skills);
root guidance follows [AGENTS.md discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md).
These are source-development files, not a new runtime dependency or a prerequisite for running
the installed application. No personal Codex configuration or plugin installation is required.

## 先体验工程问题调查（无 Provider Key）

打开首页即进入 **SameScale / 工程问题调查**。第一次使用不需要了解 Phase、Matrix 或 Judge。

```bash
uv sync --locked
npm ci --prefix frontend
npm run build --prefix frontend
HARNESSLAB_ANALYST_REAL_ENABLED=0 uv run --locked harnesslab serve
```

打开 <http://127.0.0.1:8000/>，选择：

- **运行离线演示**：固定去重失败案例，使用合成工具数据运行现有 LangGraph 与事实校验。
  无模型请求，无需 PostgreSQL、Docker 或凭据。结果不保存，刷新后可以重新运行。
- **查看历史真实记录**：只读加载并校验仓库内冻结报告，点击引用定位具体工具证据。
  这是过去的真实调查；原数据库会话尚未恢复，不提供恢复或审批按钮。
- **进入 Real 调查 / Fake 与已保存会话**：使用当前数据库的已有实验。
  需要下方完整环境设置；Fake 可演练持久化与方案审阅，Real 还需要可用 Registry profile、
  服务端显式启用、预算和逐步调用确认。创建与预检不调用模型；失败不会自动回退 Fake。

报告按 **结论 → 证据 → 限制 → 下一步** 展示。审批仅保存审阅记录，不执行回归或自动修复。
离线模式仍需本地 Python API 与构建后的前端；首次安装依赖需要网络。
报告章节导航可跳转到结论、证据、限制和下一步；引用展开工具数据与摘要后，可返回引用处。
已保存调查先显示会话范围与结果，新建表单和回归审阅可按需展开。
旧 Overview 位于 `/overview`；Experiments、Matrix、JudgeLab 等保留在可展开的「评测工具」内。

## Project entrypoints

- [Project Blueprint](docs/PROJECT_BLUEPRINT.md): product direction, architecture choices, phase
  requirements, and acceptance scope.
- [Project Status](docs/PROJECT_STATUS.md): preserved P0/real-smoke evidence and historical handoff;
  links to the current SameScale milestone in source checkouts.
- `AGENTS.md` in source checkouts: development-agent guidance and permission boundaries.
- [Architecture](docs/ARCHITECTURE.md): implemented execution and evidence contracts.
- [Productization](docs/PRODUCTIZATION.md): bundled local product operation.
- [Release Evidence](docs/RELEASE_EVIDENCE.md): versioned candidate and final-release procedure.
- [First Application](docs/FIRST_APPLICATION.md): bounded demo script, capability draft, and human
  ownership checkpoints.

Current milestone results are maintained in root CURRENT_MILESTONE.md. Domain documents
explain component behavior; dated audits and campaign records retain their original scope.

## Implemented Capabilities

- **Reproducible task evaluation:** versioned Python, Java, and TypeScript task packages,
  baseline/oracle qualification, fresh workspaces, and isolated hidden verification in Docker.
- **Model and Harness execution:** direct-provider adapters and Codex/Claude/DeepSeek Harness
  integrations, with normalized traces, filesystem-derived changes, and immutable run evidence.
  Adapter implementation and qualification for a real campaign are separate claims.
- **Durable experiments and comparison:** deterministic Matrix plans, PostgreSQL leases and
  heartbeats, cancellation/recovery, repeated-run statistics, and comparability-gated pairs/ablations.
- **Judge calibration and diagnosis:** suite-scoped JudgeLab evaluation, bias/consistency checks,
  failure clustering, factual BadCase reports, and a bounded read-only attribution Analyst.
- **Local workbench and planning:** bundled CLI/API/Vue application, evidence and trace inspection,
  regression comparison, registry/settings views, and validated experiment planning snapshots.
- **Evidence and release controls:** digest-verified artifacts, credential-reference configuration,
  keyless CI gates, and an independent final-release verifier binding evidence to an exact Git/CI head.

These are implemented system capabilities, not blanket phase-completion or model-performance
claims. [Release Evidence](docs/RELEASE_EVIDENCE.md) records the accepted campaign scope and limitations.

## Core boundary

JudgeLab is an L2 annotation and comparison layer. Evidence authority is
`L0 deterministic > L1 repository-curated human gold > L2 LLM Judge`.

## Workbench boundary

Phase I evidence pages remain read-only. Unified Registry Lite adds backend-validated planning
pages for models, providers, Harnesses, capabilities, settings, and new experiment snapshots.
The browser still cannot mutate outcomes, cancel runs, change task/gold data, read secrets or
private runtime URLs, or trigger subject/Harness/Judge execution. The Analyst page adds saved
investigations and review-only approvals. Explicitly enabled real Analyst decisions use a Registry
profile; creation, reads, and approvals make no provider calls. See
[Unified Registry Lite](docs/UNIFIED_REGISTRY_LITE.md) and [Analyst](docs/ANALYST.md).

## Analyst boundary

Phase J is a read-only attribution layer over approved Phase G/H/I evidence. It uses LangGraph
only for a bounded local decision/tool/finalize graph. Trace and task text are untrusted evidence,
not instructions. Its six evidence tools cannot execute subjects, enqueue or cancel work, or invoke
Harness, Judge, shell, browser, arbitrary SQL, filesystem, or code tools. Fake is the deterministic
default. The explicit real decision backend reuses ProviderAdapter and strict JSON output; the
host validates tool scope, citations, facts, and proposals. PostgreSQL stores only the Analyst
session and review state; authoritative experiment evidence remains unchanged.

A bounded live Real Agent smoke completed on 2026-09-09 using persisted `core-real-matrix-v6`
evidence. The accepted report is host-validated, the model proposal is review-only, and approval
keeps `execution_authorized=false`. This verifies the Analyst vertical slice; it does not authorize
a new Matrix/regression campaign or strengthen the accepted V6 causal claims. See
[Real Agent smoke evidence](docs/evidence/REAL_AGENT_SMOKE_20260909.md).

## Local setup

Gate A prerequisites are Docker and [uv](https://docs.astral.sh/uv/). Gate B additionally requires
Java 21 (`java` and `javac`) and Node.js `>=24.18.1 <25` on `PATH`. Gate C requires a reachable local
Docker Engine, or Docker Desktop using Linux containers; remote TCP/SSH contexts are unsupported.
Gate D uses deterministic fake/MockTransport providers and requires no model API key. Gate E
builds the pinned Codex image and uses deterministic Fake Codex runs. Gate F builds pinned Claude
and DeepSeek images and uses deterministic fake harness runs; none requires a key.
Gate G adds real PostgreSQL queue concurrency and actual keyless runner execution without
consuming provider or ambient harness credentials.
Gate H adds a 15-case keyless suite and 126 persisted Judge slots without real model calls.
Gate I adds a keyless persisted two-task Matrix, Judge calibration fixture, treatment-aware
manifest Regression proofs, trusted artifact-root escape tests, typed Workbench API tests, and
frontend type/test/build checks. The frontend accepts compatible Node releases in
`>=24.18.1 <25`.
Gate J adds a keyless production queue/executor/manifest/report fixture, controlled ablation,
host-validated structured fact binding, safe normalized-trace reads, no-ablation hypothesis proof,
and source snapshots.

Tier-B corpus qualification is also fully keyless. It repeats baseline/oracle and known-defect
verification, checks workspace isolation and failure attribution, and never invokes a provider or
Judge. See [Tier-B repo engineering](docs/TIER_B_REPO_ENGINEERING.md).
The operator-blocked six-slot preregistration is documented in
[Tier-B keyless smoke experiment](docs/TIER_B_SMOKE_EXPERIMENT.md).

```powershell
Copy-Item .env.example .env
uv sync --locked
docker compose up -d
uv run alembic upgrade head
uv run harnesslab doctor
uv run harnesslab sandbox doctor
uv run harnesslab model profile validate profiles/openai-responses.example.yaml
uv run harnesslab harness codex doctor
uv run harnesslab harness claude doctor
uv run harnesslab harness deepseek doctor
uv run harnesslab experiment --help
uv run harnesslab judge suite validate judge_suites/core-calibration/1.0.0
uv run harnesslab judge plan judge_suites/core-calibration/1.0.0/calibration.yaml
uv run harnesslab analyst --help
```

Start the frontend development server in a second shell:

```powershell
Set-Location frontend
npm ci
npm run dev
```

Start the API and query its health endpoint:

```powershell
uv run harnesslab serve
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

`doctor` returns exit `0` when all required checks pass, `1` for a failed configured check, and
`2` when required configuration is not available. Health returns HTTP 503 when the database
round trip fails and never returns a DSN or credential.

## Verification

Choose checks for the changed contract and risk; the command catalog below is not a mandatory
sequence for every task. Documentation-only edits need link/consistency checks and any affected
existing documentation contracts. Behavior changes need the relevant focused tests. Expand to
phase gates or full regression for cross-cutting risk or the selected acceptance/release scope.

The repository supplies keyless `scripts/verify_gate_a.py` through `scripts/verify_gate_k.py`.
Run a selected gate with `uv run --locked python scripts/verify_gate_<letter>.py` after checking
its prerequisites. These scripts may run substantial tests, Docker builds, or database fixtures.

| Gate | Contract |
| --- | --- |
| A | Foundation, runtime, static checks, and regression suite |
| B–C | Task packages, deterministic verification, and Docker isolation |
| D–F | Direct-model and pinned Harness adapters, traces, and Comparability |
| G–H | Durable experiments, statistics, and Judge calibration |
| I–J | Workbench projections and bounded read-only attribution |
| K | Corpus, immutable history, evidence/claim bindings, and release hard stop |

Keyless/fake checks do not acquire or replace real campaign evidence. Missing prerequisites,
zero collected tests, or skipped critical checks do not prove acceptance. Final release requires
its own exact-head verification; see [Release Evidence](docs/RELEASE_EVIDENCE.md).

Domain references: [Evaluation Methodology](docs/EVAL_METHODOLOGY.md),
[Task Format](docs/TASK_FORMAT.md), [Sandbox Security](docs/SANDBOX_SECURITY.md),
[M-Lane](docs/MODEL_LANE.md), [Codex H-Lane](docs/CODEX_HARNESS.md),
[Comparability](docs/HARNESS_COMPARABILITY.md), [Statistics](docs/EXPERIMENT_STATISTICS.md),
[JudgeLab](docs/JUDGELAB.md), [Workbench](docs/WORKBENCH.md), and [Analyst](docs/ANALYST.md).
Historical smoke plans are documented in [Real Evidence Authorization](docs/REAL_EVIDENCE_AUTHORIZATION.md);
reading them does not authorize a new campaign.

## Fresh clone operator path

Assumptions are Python 3.12.14, uv 0.12.5, Docker, PostgreSQL 18, Java 21, and Node 24
(`>=24.18.1 <25`). From a fresh clone:

```bash
uv sync --locked
docker compose up -d postgres
uv run --locked alembic upgrade head
uv run --locked harnesslab task validate tasks/micro-python-clamp/1.0.0
npm --prefix frontend ci
npm --prefix frontend run build
uv run --locked python scripts/verify_fresh_setup.py --check-runtime
```

That command is a non-mutating setup preflight contract, not proof that a clean checkout was fully
reproduced. The default push/pull-request workflow is bounded development CI. The manually
dispatched full-release workflow supplies the authoritative clean-checkout reproduction: after its
isolated A-K and qualification jobs succeed, `--actions-reproduction` verifies the exact
`GITHUB_SHA`, pinned runtimes, and an unmodified tracked checkout. That mode is CI-only and does not
invoke any gate recursively.

For a task requiring the full keyless chain, run Gates A–K using their prerequisites; database-backed
gates need an appropriate test PostgreSQL instance. Ordinary edits use the verification scope above.
Real execution needs current authorization and credential references; never commit `.env` or secret values.

## S2.5 本地资源配置

在 Registry 导航中打开“连接与配置”（`/connections`），可查看并配置本地凭据、连接、模型用途/参数与受限 Harness 预设。内置目录只读；保存配置不会执行评测，也不会切换当前 Analyst/Judge。

此入口默认关闭。先按上方开发说明配置本地数据库；在启动 API 的同一个 Bash 会话中设置独立管理令牌（至少 32 字符，不使用模型 API Key）：

```bash
read -r -s -p 'Local operator token: ' HARNESSLAB_LOCAL_CONFIGURATION_TOKEN
export HARNESSLAB_LOCAL_CONFIGURATION_TOKEN
```

直接运行 API 的开发者须先对自己的工作区数据库执行 `uv run --locked alembic upgrade head`，
并为凭据目录设置绝对路径。例如在启动 API 的同一个 Bash 会话中：

```bash
export HARNESSLAB_CREDENTIAL_STORE="$HOME/.local/share/samescale/credentials"
install -d -m 0700 "$HARNESSLAB_CREDENTIAL_STORE"
```

目录必须属于 API 进程用户、权限为 0700，文件权限为 0600；路径不得含符号链接，也不得与源码或
工作区产物目录重叠。未配置目录时，原有环境变量引用和本地模型编辑仍可使用，新增密钥/连接保存会失败。
这是受操作系统权限保护的本地文件存储，**不宣称磁盘加密或云端密钥托管**。备份和恢复时需配套保留
数据库与凭据卷/目录及原权限；只恢复数据库不会恢复密钥。不要把凭据目录加入可下载产物根。


在同一会话运行 `uv run --locked harnesslab serve`；在现有前端开发服务或已构建的工作区打开 `/connections`。用本机 `localhost` 或 `127.0.0.1` 地址访问，输入管理令牌解锁；令牌只留在页面内存，锁定或离开后清除。

每次保存产生新版本，旧计划不改写；凭据轮换或配置停用后需重新绑定。API Key 和连接地址不回显；“校验配置（不联网）”只校验本地引用，连接健康仍为 `NOT_VERIFIED`。
