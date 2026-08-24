# Evidence and resume scope

This file separates repository evidence from intended design. A capability moves to
`IMPLEMENTED_AND_VERIFIED` only after its named gate has produced current evidence.

## IMPLEMENTED_AND_VERIFIED

- Python 3.12.14/uv project installation from the repository lock
- Typer CLI help/version, fail-closed doctor, and Uvicorn serve entry point
- FastAPI database-aware health endpoint, including healthy and unavailable behavior
- PostgreSQL 18.6 connectivity through SQLAlchemy 2 async and psycopg 3
- Alembic upgrade from a newly created empty PostgreSQL database
- Pydantic v2 contracts for Task, Model, Harness, Experiment, and Run comparability facts
- Local pytest, Ruff, mypy, and working-tree checks through the authoritative Gate A runner
- Remote GitHub Actions Gate A for baseline commit
  `f97f5218cfd898a349f1237505b2e5731a65452e` (run `32572916235`, result `success`)
- Versioned task packages with strict YAML loading, duplicate/unknown-field rejection, safe paths,
  symlink rejection, and deterministic task/workspace digests
- Fresh subject-workspace materialization that excludes hidden verifier and oracle assets
- Hidden deterministic verification with fail-closed malformed-output, timeout, and protected-file
  handling; bounded partial scores; and immutable evidence manifests
- Baseline-fail/oracle-pass validation and tamper-resistance tests
- Controlled Python, Java 21, and TypeScript/Node task fixtures
- `harnesslab task validate` and the authoritative local Gate B runner
- Remote GitHub Actions Gate A + Gate B for the approved Phase B head
  `99edecc8c09aedece35ad847c319fbe3fb722b5c` (run `32576411069`, result `success`)
- Local Docker/Docker Desktop Linux-container preflight with remote TCP/SSH context rejection
- Fresh hardened subject and isolated-verifier containers with inspect-derived security evidence
- Timeout and cancellation cleanup, fresh-workspace isolation, bounded redacted output, immutable
  image identity, and symlink-safe local artifact bundles
- Containerized Fake Subject solving the Python micro task followed by isolated hidden verification
- Minimal PostgreSQL execution lease with owner heartbeat, expiry recovery, attempt count, and
  cancellation request
- `harnesslab sandbox doctor` and the authoritative local Gate C runner
- Remote GitHub Actions Gate A + Gate B + Gate C for the final approved Phase C head
  `cdf37c6b5c21a712194120b1d2d96a8d37a49f76` (run `32582365570`, result `success`)
- Credential-reference-only profiles and async httpx adapters for OpenAI Responses, Anthropic
  Messages, and generic OpenAI-compatible Chat Completions
- Versioned deterministic `direct-patch-v1` prompt identity and bounded strict write/delete patch
  application with traversal, symlink, protected-file, and exact-secret defenses
- M-Lane fake-provider execution from fresh Phase B workspace through the Phase C isolated hidden
  verifier, with immutable direct-model evidence and requested/observed model separation
- `harnesslab model run`, model profile validation, and the authoritative no-key Gate D runner
- Remote GitHub Actions Gate A + Gate B + Gate C + Gate D for the Phase D implementation head
  `efacc13397f3f12d3eff6c120c50809fea6d6a5d` (run `32588389612`, result `success`)
- A pinned, project-owned Codex 0.149.0 image/profile and the minimal Codex HarnessAdapter contract
- `codex-harness-v1`, sanitized native JSONL, Normalized Trace v1, filesystem-authoritative
  workspace diffs, explicit Harness failure taxonomy, and immutable H-Lane evidence
- Deterministic Fake Codex execution of all three controlled tasks through the Phase C isolated
  hidden verifier, including fail-closed protocol/profile/artifact and self-report-negative cases
- `harnesslab harness codex doctor` and the authoritative no-key Gate E runner
- Remote GitHub Actions Gate A + Gate B + Gate C + Gate D + Gate E for the approved Phase E head
  `ca0cc5921169259f9cd8668901bfc4eaa3d758c0` (run `32594279021`, result `success`)
- Pinned project-owned Claude Code 2.1.241 and DeepSeek Harness 0.1.1-rc.2 images/profiles with
  immutable npm integrity, non-root execution, and Python 3.12.11, Java/Javac 21.0.12, and
  Node 24.19.0 task toolchains
- One shared Phase F H-Lane runner with fresh workspace, filesystem-authoritative diff, exact-secret
  artifact withholding, Phase C Hidden Verifier authority, and immutable multi-harness evidence
- Claude `claude-harness-v1` bare stream-JSON collection with minimal Read/Edit/Write/Bash tools,
  retry/lifecycle/failure evidence, unknown-event preservation, and private-reasoning exclusion
- Public DeepSeek E1 `dsh --profile headless` collection with isolated `DSH_HOME`, default/effective
  config digests, `FINAL_OUTPUT_ONLY` trace coverage, and explicit developer-preview identity
- Deterministic Fake Claude and Fake DeepSeek runs of all three controlled tasks through the
  isolated Hidden Verifier, including self-report negatives, taxonomy, config-drift, and
  secret/reasoning controls
- Comparability contracts, manifest fact extraction, deterministic intent-aware assessment, and
  `harnesslab compare assess` text/JSON output with field-level reasons and evidence identities
- Explicit `FULL_STREAM` coverage on new Codex evidence, alongside Claude `FULL_STREAM` and
  DeepSeek `FINAL_OUTPUT_ONLY`, without changing the approved Phase E Codex profile fingerprint
- `harnesslab harness claude doctor`, `harnesslab harness deepseek doctor`, and the authoritative
  non-recursive, keyless Gate F runner
- Actual Phase D, Phase E Codex, Phase F Claude, and Phase F DeepSeek deterministic runners each
  persisting `manifest.json`, followed by disk-based `load_manifest_facts` and Comparability
- Remote GitHub Actions Gate A + B + C + D + E + F for the final approved Phase F head
  `370559665a1ed38c727ec12493906ff35db6f332` (run `32633994665`, result `success`)
- Strict Phase G ExperimentSpec validation, deterministic task/cell/repeat expansion, canonical
  plan JSON, stable logical slot identities, and SHA-256 plan identity
- PostgreSQL experiment/cell/pair/ablation/run persistence, additive Alembic head
  `20260823_0003`, idempotent enqueue, real `FOR UPDATE SKIP LOCKED` two-worker claiming,
  heartbeat, owner enforcement, expiry reclaim, attempts, cancellation, and lifecycle checks
- Existing M/H runner dispatch through a bounded local worker, with persisted manifest paths and
  evidence digests reloaded for statistics and reporting
- Capability/infra/cancellation normalization, n=1 smoke, n>=3 informal, n>=5 formal, and the
  infrastructure-denominator rule
- Comparability-gated exact-slot P-Lane, controlled reasoning-effort ablation, Wilson 95%,
  per-task macro pass@k, p50/p95, deterministic bootstrap, exact McNemar-style tests, and paired
  bootstrap statistics
- Deterministic JSON/Markdown reports and the Phase G experiment/run/report CLI
- An authoritative non-recursive, keyless Gate G with real PostgreSQL queue evidence and an
  actual nine-slot runner-to-manifest-to-loader-to-report experiment E2E
- Approved Phase G head `1f9ef540d3d1d32e7ae8ccc5e514374600959ce0`, remote CI run
  `32639483950` (`success`), including execution-time worker heartbeat, stale-worker write
  prevention, attempt-scoped artifacts, coherent cancellation, per-task repetition eligibility,
  task lane-support validation, and manifest-vs-slot enforcement
- Strict versioned JudgeDefinition, public-case/hidden-gold suite, deterministic
  definition/public/gold/suite/plan identities, and LABEL/SCORE/PAIRWISE contracts
- Existing one-attempt ProviderAdapter reuse, immutable JudgeEvidence, refusal/output/provider/
  artifact taxonomy, and private-reasoning/gold/credential exclusion
- Three explicit repeats, pairwise A/B↔B/A swaps and canonicalization, position consistency,
  verbosity probes, repeat consistency, and suite-scoped qualification metrics
- PostgreSQL Judge calibration/evaluation persistence at Alembic `20260823_0004`, verified disk
  artifact reload, Phase G read-only regression, and deterministic JSON/Markdown reports
- Actual keyless 126-slot Good-vs-Biased Judge E2E and non-recursive Gate H coverage across
  leakage, hierarchy, strict output, bias, repetition, persistence, qualification, CLI, and scope
- Approved Phase H head `f8f6ecdf644cb01e73afb039a4a503a394a51fe5`, remote CI run
  `32651571933` (`success`), proving public-suite answer-key exclusion, JudgeDefinition-owned order
  swap, versioned qualification, provider-infra separation, persisted L0 authority resolution,
  byte-exact JudgeEvidence integrity, service-level real-Judge opt-in, and that ambient credentials
  alone cannot trigger a real Judge
- Typed read-only `/api/workbench` DTO/routes for experiments, Matrix, runs, safe trace, JudgeLab,
  deterministic Regression compare, durable status polling, and Core readiness
- Vue 3/Vite/TypeScript frontend with pinned npm graph, Pinia query state, Vue Router routes,
  focused Element Plus affordances, modular ECharts, Axios, Vitest, and production build
- Real keyless Phase G queue/runner/manifest/report evidence including an authoritative two-task,
  three-cell, three-repeat persisted Matrix, plus Phase H fake-Judge fixtures read end-to-end
  through Workbench API contracts, including trusted-root/digest/path/private-reasoning sensitivity
- Explicit `NOT_REPORTED`, `PARTIALLY_COMPARABLE`, and `NOT_COMPARABLE` UI/API semantics; suite-
  scoped Judge qualification; directional non-causal Regression comparison; `NOT_READY` evidence-
  driven Core dashboard; and no browser execution endpoint
- Treatment-aware immutable-manifest Regression using Phase F ComparabilityEngine; task-scoped
  Matrix comparability; explicit Judge report integrity state; and 15-25 task readiness threshold
- An authoritative non-recursive Gate I with 15 backend persisted-evidence tests, 14 focused
  frontend tests, strict TypeScript, Vite production build, Ruff, mypy, and scope/secret checks
- LangGraph 1.2.11 confined to an explicit bounded Attribution Analyst `StateGraph`, with strict
  request/action/report contracts and no checkpoint, RAG, or multi-agent expansion
- Exactly six experiment-scoped read tools, trusted manifest/normalized-trace reopening, safe task
  contract resolution, approved Phase G report/statistics reuse, and persisted ablation evidence
- Deterministic non-path citations, exact-value structured fact binding, fabricated-reference and
  contradiction rejection, canonical host-rendered fact prose, and enforced
  `VERIFIED_FACT`/`HYPOTHESIS` separation
- Canonical timestamp-free report JSON/digest plus Markdown, atomically persisted only after
  validation under a controlled Analyst artifact root
- A keyless production-path Gate J fixture using ExperimentSpec/Plan, queue, executor, fake Codex,
  persisted manifests/report/AblationSpec; 22 focused tests with zero skips
- Before/after proof that analysis leaves experiment/cell/pair/ablation/run rows, outcomes,
  artifact digests/mtimes, Judge state, and fake execution-backend call counts unchanged

Evidence date: 2026-08-24. Phase H remote evidence is approved at the exact head/run above. Phase I
and Phase J entries have current local gate evidence pending this change's named remote CI run. Phase D
provider contracts are MockTransport/fake-provider verified; Phase E/F harness behavior is
deterministic fake verified. None implies a real provider/model call or VM-level isolation.

## IMPLEMENTED_NOT_YET_MASTERED

None recorded. This category requires an implemented capability whose operational ownership has
not yet been demonstrated.

## DESIGN_ONLY

- Additional Harness adapters beyond Codex, Claude Code, and DeepSeek E1
- Provider-backed Analyst execution, RAG, and multi-agent attribution workflows

## WORKBENCH_ONLY

- Phase I read-only evidence Workbench, Matrix visualization, deterministic Regression compare,
  safe trace presentation, Judge calibration browser, polling, and Core readiness dashboard

## NOT_VERIFIED

`REAL_JUDGE_SMOKE = NOT_RUN`, `REAL_MATRIX_EVIDENCE = NOT_RUN`, `REAL_PROVIDER_SMOKE = NOT_RUN`,
`REAL_CODEX_SMOKE = NOT_RUN`,
`REAL_CLAUDE_SMOKE = NOT_RUN`, and `REAL_DEEPSEEK_SMOKE = NOT_RUN`. DeepSeek persistent-session E2
is `DEFERRED_NOT_VERIFIED`. No real provider credential is required for Gates D-F, no ambient
harness login is consumed, and no real-provider/model invocation is claimed. Deterministic Gate G
does not replace the required pre-Core-hard-stop real Matrix Evidence. The provider control
plane versus subject network separation is not operationally verified. Future capabilities remain
`DESIGN_ONLY` until their own gates exist.
