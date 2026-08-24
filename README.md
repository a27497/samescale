# HarnessLab AI

HarnessLab AI is a reproducible **Model × Harness × Judge** evaluation and attribution
platform. The repository currently contains **Phase A — Foundation & Contracts** and
**Phase B — Task Contract + Deterministic Verifier**, **Phase C — Native Docker Sandbox**, and
**Phase D — M-Lane Direct Model**, **Phase E — Codex H-Lane**, and
**Phase F — Multi-Harness + Comparability**, and
**Phase G — Experiment Matrix + Repeated Runs + P-Lane + Statistics**, and
**Phase H — JudgeLab + Judge Calibration**, and
**Phase I — Read-only Workbench UI + Regression Compare**, and
**Phase J — Read-only Attribution Analyst**.

## Implemented now

- An exact Python 3.12.14 runtime and uv lockfile
- A Typer CLI with `--help`, `--version`, `doctor`, and `serve`
- A FastAPI control API with a database-aware `GET /api/health` and typed read-only Workbench API
- Secret-safe settings loaded with Pydantic Settings
- PostgreSQL 18 development service, SQLAlchemy 2 async access, psycopg 3, and Alembic
- Pydantic v2 contracts for Task, Model, Harness, Experiment, and Run
- Versioned, strict-YAML task packages with deterministic task and workspace digests
- Fresh subject workspaces that exclude hidden verifiers and oracle overlays
- Fail-closed deterministic verification with baseline-fail/oracle-pass polarity validation,
  bounded partial scores, protected-file checks, and immutable evidence manifests
- Python, Java 21, and TypeScript/Node 24 controlled micro-task fixtures
- `harnesslab task validate` and an authoritative Gate B runner
- A Docker CLI sandbox with a fresh non-root Linux container per subject/verifier run
- Inspect-verified capability, privilege, network, rootfs, PID, CPU, memory, and mount controls
- Bounded/redacted logs, immutable image identity, safe workspace snapshots, and hashed artifacts
- Timeout/cancellation cleanup and fresh-run workspace isolation
- A minimal PostgreSQL execution lease with heartbeat and expiry recovery
- `harnesslab sandbox doctor` and an authoritative Gate C runner
- A normalized direct-provider boundary using async httpx for OpenAI Responses, Anthropic
  Messages, and generic OpenAI-compatible Chat Completions
- Credential-reference-only model profiles, one-attempt provider failure attribution, and safe
  public-output metadata without raw HTTP responses or private reasoning/thinking blocks
- Deterministic `direct-patch-v1` prompts, strict write/delete patches, protected-path and
  traversal defenses, and exact-secret artifact withholding
- An M-Lane runner that applies model patches in a fresh Phase B workspace and evaluates the
  result through the Phase C isolated hidden verifier
- `harnesslab model run`, model-profile validation, and an authoritative no-key Gate D runner
- A pinned non-root Codex 0.149.0 runtime, deterministic `codex-harness-v1` prompt, and minimal
  `HarnessAdapter` boundary for `codex exec --json`
- Sanitized native JSONL and Normalized Trace v1 without private reasoning content, plus
  filesystem-authoritative workspace changes and immutable H-Lane evidence
- Fake Codex end-to-end runs for the Python, Java, and TypeScript tasks through the isolated
  hidden verifier, and an authoritative no-key Gate E runner
- Pinned, non-root Claude Code 2.1.241 and DeepSeek Harness 0.1.1-rc.2 subject images with the
  same Python 3.12, Java/Javac 21, and Node 24 task toolchains as the verifier
- One shared Phase F runner for Claude Code bare stream-JSON and the public DeepSeek
  `dsh --profile headless` contract, including safe evidence and explicit trace coverage
- A deterministic Comparability Engine with three claim intents, field-level reasons, and
  `COMPARABLE`, `PARTIALLY_COMPARABLE`, or `NOT_COMPARABLE` outcomes
- An authoritative, keyless, non-recursive Gate F with critical-test and sensitivity enforcement
- Strict ExperimentSpec validation and timestamp-free deterministic ExperimentPlan expansion
- PostgreSQL experiment/cell/pair/ablation/run storage with idempotent enqueue, transactional
  `FOR UPDATE SKIP LOCKED` claiming, heartbeat, expiry reclaim, attempts, and cancellation
- A bounded worker that dispatches through existing M/H runners and persists manifest identity
- Formal n=5, informal n>=3, and smoke n=1 tiers with infrastructure failures outside the
  capability denominator
- Wilson 95%, per-task macro pass@k, p50/p95, deterministic bootstrap, exact paired binary tests,
  and paired continuous statistics using NumPy, pandas, and SciPy
- Comparability-gated P-Lane and controlled ablation reporting in deterministic JSON/Markdown
- `harnesslab experiment plan/run`, `harnesslab run inspect`, `harnesslab report compare`, and an
  authoritative non-recursive, keyless Gate G
- Strict JudgeDefinition and public-case/hidden-gold suite contracts for LABEL, SCORE, and
  PAIRWISE evaluation
- Public-only Judge prompts over the existing one-attempt ProviderAdapter layer, with strict JSON
  outputs, immutable JudgeEvidence, pairwise order swaps, bias probes, and repeated calibration
- Label/score/pairwise metrics, suite-scoped qualification, PostgreSQL slots, verified disk
  artifact reload, deterministic reports, and a keyless Good-vs-Biased E2E
- `harnesslab judge suite validate/plan/calibrate/report` and an authoritative non-recursive,
  keyless Gate H
- A Vue 3/Vite/TypeScript analytical Workbench with Pinia, Vue Router, Element Plus, ECharts,
  Axios, Vitest, and a pinned npm dependency graph
- Read-only experiment, task-scoped multi-task Matrix, run/trace, JudgeLab, treatment-aware
  deterministic Regression compare, polling, and Core readiness views over PostgreSQL plus
  trusted-root-confined, digest-verified immutable evidence
- Explicit `NOT_REPORTED` versus zero and `NOT_COMPARABLE` versus missing evidence semantics,
  with no browser-triggered model, Harness, or Judge execution
- An authoritative non-recursive, fully keyless Gate I using real persisted Phase G/H fixtures
- A LangGraph 1.2.11 `StateGraph` confined to a read-only Attribution Analyst package, with an
  explicit 8-decision/12-tool-call bound and no generic Agent, RAG, or multi-agent runtime
- Exactly six experiment-scoped evidence tools: `query_runs`, `compare_cells`, `inspect_trace`,
  `inspect_failure`, `get_task_contract`, and `get_ablation`
- Exact-value structured fact assertions bound to deterministic evidence citations, enforced
  `VERIFIED_FACT` versus `HYPOTHESIS`, canonical JSON/Markdown reports, and a production-path
  keyless Gate J read-only proof
- pytest integration/unit coverage, Ruff, mypy, and one authoritative Gate A runner
- GitHub Actions using PostgreSQL 18 without model-provider credentials

## Core boundary

JudgeLab is an L2 annotation and comparison layer. Evidence authority is
`L0 deterministic > L1 repository-curated human gold > L2 LLM Judge`.

## Workbench boundary

Phase I implements a read-only evidence Workbench. Experiment and Judge execution remains in the
approved CLI/operator paths. The browser cannot mutate outcomes, cancel runs, change task/gold
data, or trigger provider execution. Phase J does not add an Analyst browser route.

## Analyst boundary

Phase J is a read-only attribution layer over approved Phase G/H/I evidence. It uses LangGraph
only for a bounded local decision/tool/finalize graph. Trace and task text are untrusted evidence,
not instructions. The Analyst cannot execute subjects, enqueue or cancel work, invoke a provider,
Harness, Judge, shell, browser, SQL, filesystem, or code tool, and cannot alter authoritative
evaluation evidence. Trusted host code writes only a validated Analyst report after completion.

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

With PostgreSQL running and `DATABASE_URL` configured, the authoritative local/CI gate is:

```powershell
uv run --locked python scripts/verify_gate_a.py
```

This runner executes locked sync, CLI checks, pytest (including an empty-database migration),
Ruff, mypy, Alembic, and Git whitespace validation. It rejects zero collected tests, skipped
critical tests, imports outside the working tree, or an absent database configuration. Exit `2`
means **NOT_VERIFIED**, not success.

The authoritative Phase B gate is:

```powershell
uv run --locked python scripts/verify_gate_b.py
```

It runs the Phase B test corpus, validates all three language fixtures through the public CLI,
checks their baseline/oracle polarity and critical tests, then runs Ruff, formatting, mypy, and
Git whitespace validation. Individual task packages can be inspected without exposing hidden
assets:

```powershell
uv run harnesslab task validate tasks/micro-python-clamp/1.0.0
```

The Phase C gate runs real hardened subject and verifier containers, verifies cleanup and
fresh-workspace behavior, checks artifact/redaction integrity, exercises lease expiry recovery,
and invokes the Phase A and Phase B gates as regressions:

```powershell
uv run --locked python scripts/verify_gate_c.py
```

The Phase D gate invokes Gate C as its A/B/C regression, then checks all provider protocols,
deterministic prompt and patch safety, credential withholding, and the fake-provider M-Lane E2E:

```powershell
uv run --locked python scripts/verify_gate_d.py
```

Real provider calls are optional and were not used as Gate D evidence. See the safe example
profiles under `profiles/`; they contain environment-variable names, never credential values.

The Phase E gate independently checks the pinned runtime, profile and prompt fingerprints,
sanitization/trace mapping, failure taxonomy, workspace authority, and all three H-Lane fixtures:

```powershell
uv run --locked python scripts/verify_gate_e.py
```

Real Codex execution is opt-in and is not Gate E evidence. The default result is
`REAL_CODEX_SMOKE=NOT_RUN`; HarnessLab does not consume ambient Codex login state or credentials.

The non-recursive Phase F gate independently verifies Phase F and its current-tree contracts:

```powershell
uv run --locked python scripts/verify_gate_f.py
```

Real Claude and DeepSeek calls are optional and are not Gate F evidence. DeepSeek E1 is honestly
`FINAL_OUTPUT_ONLY`; E2 is `DEFERRED_NOT_VERIFIED` because no sufficiently documented public
persistent-session extractor seam was established.

The non-recursive Phase G gate verifies planning, PostgreSQL queue concurrency, keyless runner
execution, immutable manifest reload, repeated-run policy, P-Lane, ablation, statistics, reports,
and CLI contracts:

```powershell
uv run --locked python scripts/verify_gate_g.py
```

`REAL_MATRIX_EVIDENCE=NOT_RUN` remains separate from deterministic Gate G. A real Matrix Evidence
run is still required before the final Core hard stop and is never synthesized from ambient login.

The non-recursive Phase H gate verifies Judge contracts, leakage, strict outputs, evidence
hierarchy, order swaps, bias probes, repeats, persistence, artifact integrity, and qualification:

```powershell
uv run --locked python scripts/verify_gate_h.py
```

Gate H is keyless. `REAL_JUDGE_SMOKE=NOT_RUN` unless explicitly enabled with a
credential-reference-only ModelProfile.

The non-recursive Phase I gate generates actual deterministic Phase G and Phase H persisted
evidence, reads it through the Workbench API, verifies trace/artifact safety and Regression
semantics, and runs the pinned frontend type-check, Vitest suite, and production build:

```powershell
uv run --locked python scripts/verify_gate_i.py
```

All `REAL_*` evidence remains `NOT_RUN`; Gate I never uses provider or ambient Harness credentials.

The non-recursive Phase J gate verifies the bounded graph, exact tool surface, persisted evidence
reads, structured fact-to-evidence binding, contradictory run/numeric rejection, citations,
fact/hypothesis boundary, controlled ablation, injection resistance, deterministic reports, and
source immutability:

```powershell
uv run --locked python scripts/verify_gate_j.py
```

Gate J uses only `FakeAnalystBackend`; real external calls are not performed during analysis.

See [Architecture](docs/ARCHITECTURE.md), [Evaluation Methodology](docs/EVAL_METHODOLOGY.md), and
[Task Format](docs/TASK_FORMAT.md), [Sandbox Security](docs/SANDBOX_SECURITY.md), and
[M-Lane Direct Model](docs/MODEL_LANE.md), [Codex H-Lane](docs/CODEX_HARNESS.md),
[Harness Comparability](docs/HARNESS_COMPARABILITY.md),
[Experiment Statistics](docs/EXPERIMENT_STATISTICS.md), and [Resume Scope](docs/RESUME_SCOPE.md).
[JudgeLab](docs/JUDGELAB.md) documents the Phase H authority and calibration boundary, and
[Workbench](docs/WORKBENCH.md) documents the Phase I read API and Vue evidence surface.
[Attribution Analyst](docs/ANALYST.md) documents Phase J structured facts and read-only graph
boundary.
