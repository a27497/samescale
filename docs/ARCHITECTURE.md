# Architecture

## Foundation and deterministic task verification

HarnessLab is CLI-first. The `harnesslab` Typer CLI is the operator entry point, while the FastAPI
application is a small control API. Both use one Pydantic Settings model and the same database
health service. PostgreSQL 18 is the only infrastructure service. SQLAlchemy 2 uses psycopg 3 for
async application access; Alembic uses the same driver and metadata for schema changes.

Pydantic contracts describe domain inputs and reproducibility facts. They are intentionally
separate from SQLAlchemy persistence models: contracts protect API/domain meaning, while database
models describe storage. Phase A persists only a schema metadata foundation and does not pretend
that future experiment execution tables exist.

```text
Typer CLI ─┬─ doctor ───────────┐
           └─ serve ─ FastAPI ──┼─ Settings ─ SQLAlchemy/psycopg ─ PostgreSQL 18
                         health ┘

Pydantic contracts: Task × Model × Harness × Experiment Config → Run facts
```

Phase B adds a versioned task-package boundary without adding an execution engine. A strict
manifest names the subject workspace, optional context bundle, hidden verifier, optional oracle,
toolchain expectations, and execution policy. Deterministic digests bind the task package and the
materialized subject workspace independently.

```text
Versioned task package ── strict load + digest ──┬─ fresh workspace/context ─ subject edits
                                                │                                │
                                                ├─ hidden verifier ───────────────┤
                                                └─ oracle overlay (validation) ───┘
                                                                                 │
                                                   bounded result + immutable evidence
```

The subject-facing workspace never contains the package's hidden verifier or oracle. Package
validation requires the untouched baseline to fail and a separately materialized oracle overlay
to pass. The repository's Python, Java, and TypeScript fixtures execute trusted verifier code on
the host solely to validate this contract.

## Phase C native Docker boundary

Phase C adds the first boundary for an untrusted subject workspace. Trusted HarnessLab code owns
all Docker CLI argv construction; callers cannot supply raw Docker flags, mount destinations, or
host paths. Each run materializes the same Phase B package into a new managed directory and then
uses a fresh, labeled container.

```text
Phase B package ─ fresh managed workspace ─ subject container ─ safe artifact snapshot
                                                │                       │
                                                └─ destroyed ───────────┘

artifact workspace (read-only) ─┬─ isolated verifier container ─ deterministic report
hidden verifier (read-only) ─────┘
```

The subject container never sees `verifier/` or `oracle/`. The verifier is a separate hardened
container whose subject workspace and hidden verifier mounts are read-only. Both roles use no
network, no Docker socket, no added capabilities, a read-only root filesystem, non-root identity,
resource limits, bounded output, and finally-style cleanup. Local artifacts remain filesystem
bundles rather than database blobs.

Phase C also persists only a minimal execution lease: ownership, heartbeat, expiry, recovery
attempt, cancellation request, and status. It is not the planned experiment queue or worker
scheduler. Docker subprocess work on Windows runs on an isolated Proactor thread so the existing
psycopg/Uvicorn selector-loop boundary remains unchanged.

## Phase D M-Lane direct model

Phase D adds one direct-model path without a coding harness. A versioned logical prompt contains
only task instructions, the subject-visible fresh workspace, optional subject-visible context,
and the strict patch output contract. Provider adapters receive no tools. Trusted HarnessLab code
validates and applies the returned JSON patch; model-generated code is evaluated only when the
existing Phase C hidden-verifier container reads the final workspace.

```text
Phase B package ─ fresh workspace ─ direct-patch-v1 prompt ─ Provider API (no tools)
                                           │                       │
                                           │                public JSON patch
                                           │                       │
                                           └─ trusted safe apply ──┘
                                                       │
                                      Phase C isolated hidden verifier
                                                       │
                                   immutable direct-model evidence + score
```

The async httpx provider boundary implements OpenAI Responses, Anthropic Messages, and generic
OpenAI-compatible Chat Completions. It normalizes only public text, route/model identity, safe
request identifiers, usage counts, stop/status, latency, and attempt count. Raw responses,
headers, reasoning items, and thinking blocks are not evidence. Profiles contain credential
environment-variable names only. Gate D uses fake and MockTransport providers; real-provider
execution is not required or claimed.

## Phase E Codex H-Lane

Phase E adds one coding-harness path. The pinned Codex CLI receives a fresh writable subject
workspace and the small `codex-harness-v1` prompt. It never receives the hidden verifier, oracle,
operator home, host repository, or Docker socket. The adapter reports execution and artifact facts;
it never decides task correctness.

```text
Phase B package -> fresh workspace -> Codex adapter -> sanitized JSONL -> Normalized Trace v1
                                            |                                  |
                                            +-> final filesystem identity -----+
                                                               |
                                             Phase C isolated hidden verifier
                                                               |
                                                  immutable H-Lane evidence
```

The project-owned image pins Node by digest and `@openai/codex` at 0.149.0, runs non-root, and
contains only the Python, Java, and Node toolchains needed by the three controlled tasks. The
canonical profile disables approvals, tool network access, web search, external MCP, plugins,
ambient user config, and rules. The optional real backend constructs an argv-only hardened outer
container, but Phase E does not claim a safely separated provider control plane; real smoke is
therefore opt-in and `NOT_RUN` by default.

Native events are sanitized in memory before persistence. Private reasoning becomes only a
`REASONING_PRESENT` marker; malformed/raw authorization data and credentials are never artifacts.
Normalized Trace v1 preserves accepted order and maps unfamiliar safe events to `UNKNOWN`.
Native file-change claims and agent success messages are trajectory evidence only. Workspace
digests and changed-path inventory come from the actual filesystem, and the isolated hidden
verifier alone produces the pass/score outcome.

## Phase F multi-harness and comparability

Phase F adds Claude Code and DeepSeek Harness without creating separate orchestration stacks.
Both implement the same adapter contract and traverse one shared runner for task loading, fresh
workspace materialization, prompt identity, filesystem inventory/diff, artifact withholding, the
Phase C isolated Hidden Verifier, and immutable evidence persistence.

```text
Phase B task ─ fresh workspace ─┬─ Claude bare/stream-json ─ safe native stream ─┐
                               └─ dsh --profile headless ─ final stdout only ────┤
                                                                                 │
                              filesystem identity ─ Phase C Hidden Verifier ─────┘
                                                              │
                                             Phase F H-Lane evidence manifests
                                                              │
                    M/H manifest facts ─ Comparability Engine ─┘
```

Claude Code 2.1.241 runs in bare print mode with exactly Read/Edit/Write/Bash exposed and no MCP,
plugins, skills, Web, or user interaction. Thinking content becomes only `REASONING_PRESENT`.
Structured retry and failure events remain distinct, and unknown safe events become `UNKNOWN`.

DeepSeek Harness 0.1.1-rc.2 uses only documented E1:
`dsh --profile headless <task>`, with the fresh workspace as cwd and isolated `DSH_HOME`. Gate F
records default/effective config digests. E1 prints only a final answer, so it declares
`FINAL_OUTPUT_ONLY`. The public plugin architecture does not document a stable, safe
persistent-session extractor sufficient for E2; E2 remains `DEFERRED_NOT_VERIFIED`.

The Comparability Engine is a pure assessment over extracted evidence identities. Intent selects
controls and treatments. It emits every field comparison, reason codes/severities, both evidence
identities, and `COMPARABLE`, `PARTIALLY_COMPARABLE`, or `NOT_COMPARABLE`. It does not schedule
experiments, calculate statistics, or judge output quality.

## Phase G experiment matrix and statistics

Phase G turns immutable lane runs into a deterministic plan and PostgreSQL queue. A strict
ExperimentSpec resolves task packages and frozen cell identities, then expands cells x tasks x
repeat index in canonical order. The plan contains no timestamp or random UUID; canonical JSON
produces its stable digest.

```text
ExperimentSpec -> ExperimentPlan -> PostgreSQL experiment/cell/run rows
                                           |
                        FOR UPDATE SKIP LOCKED claim
                                           |
              existing M/H runner -> persisted manifest + digest
                                           |
                  manifest loader -> statistics/report
```

Claims record owner, heartbeat, expiry, and observable attempt count. Expired active work is
reclaimable, non-owners cannot heartbeat or release it, and cancellation is durable. Planning is
idempotent through immutable plan checks plus database logical-slot uniqueness. The worker is a
bounded in-process loop and dispatches to approved lane runners through injected bindings. It
heartbeats throughout active runner execution, gives every attempt a distinct artifact identity,
and fails closed after lease loss or cancellation.

Reports re-open each persisted manifest, verify its digest, extract Phase F ComparisonFacts, and
derive metrics from those bytes. The executor applies the same manifest-vs-slot control validator
before attaching capability evidence. P-Lane pairs exact task/repeat slots and always invokes
ComparabilityEngine. Ablations declare one treatment dimension; undeclared hard-control drift is
rejected. JSON and Markdown reports omit timestamps from identity.

NumPy, pandas, and SciPy supply Wilson, pass@k, descriptive, deterministic bootstrap, and exact
paired statistics. Infrastructure failures remain outside capability denominators. Formal claims
require sufficient repetition per intended task and `COMPARABLE` pairs per intended task; pooled
smoke, insufficient, and `NOT_COMPARABLE` evidence cannot enter formal ordering.

## Phase H JudgeLab and calibrated L2 evidence

Phase H adds Judge as an evaluation dimension over immutable inputs; it never reruns an M/H/P
subject because another Judge cell is added. A strict spec resolves a versioned JudgeDefinition,
ModelProfile identities, public-case/hidden-gold suite digest, three explicit repeats, and a
versioned qualification policy into timestamp-free slots.

```text
public case ─ public-only prompt ─ existing ProviderAdapter ─ strict JSON ─ JudgeEvidence
                                                                          │
hidden gold ────────────── disk reopen + digest/identity validation ───────┤
                                                                          v
                         LABEL/SCORE/PAIRWISE metrics ─ suite qualification

Authority: deterministic L0 > repository-curated human L1 > Judge L2
```

Every provider-facing slot is exactly one attempt. Refusal is abstention, malformed judgment is
an output error, and transport/auth/rate-limit/timeout uses the Phase D failure taxonomy. No
DirectModelRunner, patch parser, subject runner, or Hidden Verifier runs for the Judge call.
JudgeEvidence stores safe route/model/request/usage/latency facts and digests, but no gold, oracle,
API key, raw HTTP, private reasoning, or duplicated subject artifact.

PAIRWISE cases use neutral Candidate A/B labels and expand original and swapped orders. LEFT/RIGHT
is canonicalized to stable A/B identity before position consistency, gold accuracy, repetition,
and verbosity probes. Reports reopen each artifact and verify slot, suite, case, definition, and
profile identities. PostgreSQL stores durable calibration/slot state and artifact references;
the immutable Judge evidence remains on disk.

## Phase I read-only Workbench

Phase I adds a presentation boundary without adding an execution boundary. FastAPI resolves
persisted experiment, run, and calibration identities from PostgreSQL, confines resolved artifact
paths to server-configured trusted roots, verifies their digests and logical identities, and maps
selected safe fields into strict Pydantic DTOs. SQLAlchemy records and server paths never cross the
API boundary.

```text
PostgreSQL identity ──┬─ ExperimentPlan + verified lane manifests ─ ExperimentReport ─┐
                     ├─ run id ─ verified normalized trace sibling ─ safe events ────┤
                     └─ Judge calibration ─ verified Judge report ─ suite metrics ───┤
                                                                                     v
                                               /api/workbench typed read DTOs ─ Vue 3
                                                                                     │
                                        Pinia query state + route reconstruction + polling
```

The Vue client uses one typed Axios boundary, Pinia only for query/UI state, Vue Router for durable
URLs, Element Plus for focused interaction affordances, and modular ECharts heatmaps/bars. Numeric
values come from backend report contracts. Task×cell Matrix statistics reuse Phase G verified
observations and `summarize_cell()` without pooling tasks. Missing evidence is status-bearing
`NOT_REPORTED`, not zero. Comparison eligibility remains `COMPARABLE`,
`PARTIALLY_COMPARABLE`, `NOT_COMPARABLE`, or comparison `NOT_REPORTED` when no pair exists.

The trace route accepts a run id only. It verifies the persisted manifest, deterministic physical
attempt identity, normalized trace sibling containment, and trace digest. It never opens native
private transcripts; `REASONING_PRESENT` becomes a content-withheld marker. Regression compare
reopens two persisted reports and actual paired run manifests, then applies Phase F comparability
under an explicit model, Harness, or general intent. It does not rerun subjects, claim significance,
or infer causality.

The only Workbench POST is the computation-only Regression compare request. There are no browser
routes for model, Harness, or Judge execution, cancellation, deletion, scoring, or task/gold
mutation. The Core readiness view is derived from structured persisted evidence and remains
`NOT_READY` while real Matrix evidence or release artifacts are unverified.

## Phase J read-only Attribution Analyst

Phase J adds the repository's one confined use of LangGraph 1.2.11. A local `StateGraph` has
explicit decide, validated-tool, and deterministic-finalize nodes, no checkpoint service, and hard
limits of 8 decisions and 12 tool calls. State contains only the public request and scope,
validated actions, safe evidence catalog, counters, and report—not private chain-of-thought.

```text
AnalysisRequest + bound experiment ─ decide ─ strict six-action union
                                      ^                    │
                                      └── safe evidence ───┤
                                                           v
                              experiment-scoped read repository
                                                           │
                            structured fact + citation validation ─ report
```

The repository starts PostgreSQL work read-only and exposes no mutation method. Run, cell, task,
and ablation identities are checked against the bound ExperimentPlan. Artifact reads use trusted
root confinement plus manifest and normalized-trace digests. Native transcripts are never read,
`REASONING_PRESENT` remains content-withheld, and paths never enter the report.

`compare_cells` calls the Phase G report/statistics path; it copies no formulas and creates no new
significance claim. `get_ablation` returns declared treatment and persisted paired statistics with
evidence tier and Comparability limitations. Every `VERIFIED_FACT` is a set of exact-value
assertions over a cited entry's tool namespace and field path. The trusted host resolves and checks
those assertions, derives citations, and renders the canonical statement; the backend cannot attach
contradictory prose. Unknown references, wrong namespaces, absent paths, and unequal values fail
closed. Unsupported interpretation remains `HYPOTHESIS` and names evidence needed to verify or
falsify it.

`FakeAnalystBackend` is the only operational Phase J backend. No implicit credential/provider path
or Workbench Analyst route exists. Trusted host code alone atomically persists a validated report;
source experiment and Judge evidence remains unchanged.

## Planned Core boundaries

The following are **PLANNED**, not implemented:

- Additional harness adapters at explicit external-system boundaries
- Remote/cloud artifact storage and worker execution
- Remote/cloud Judge artifact storage and distributed Judge workers
- Provider-backed Analyst execution, RAG, and multi-agent attribution

## Deliberate exclusions

Core remains Python because the evaluation ecosystem, schemas, subprocess orchestration, and
analysis tooling are Python-centered; adding Java would create a second runtime without solving an
adapter boundary. Redis and Celery are unnecessary while PostgreSQL can later provide durable
state and queue semantics transactionally. Kafka/RocketMQ and Kubernetes solve scale and
operations problems not established by current evidence. RAG and multi-agent frameworks do not
solve HarnessLab's core reproducibility and adapter problem.

These exclusions are decisions against premature complexity, not claims that those technologies
are universally unsuitable.

## Phase K Core release boundary

Phase K adds no new execution backend. It composes approved A-J contracts into a canonical 18-task
corpus, seven-cell real-evidence preflight, strict prospective release bindings, and keyless Gate K.
Ordinary CI rebuilds task identities, validates plan/evidence semantics, and proves incomplete
evidence cannot authorize a tag. It never resolves credentials or calls providers, Harnesses, or a
Judge.

The release layer is `src/harnesslab/release`; canonical inputs live in `release/`. K-A distinguishes
structurally verified preparation from real results. Final mode additionally requires a trusted
PostgreSQL store, trusted artifact root, artifact identities/digests, exact Git/remote CI head,
supported resume claims, three BadCases, and all mandatory `REAL_*` states. Tag creation stays
outside the verifier and is authorized only when derived readiness is true.
