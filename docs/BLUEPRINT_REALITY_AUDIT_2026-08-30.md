# HarnessLab Blueprint Reality Audit — 2026-08-30

## Outcome

HarnessLab has substantially more implemented foundation than a phase-name inventory suggests, but
the post-K roadmap is not complete. The integrated tree at
`968873954e7e00b5d3426bf1f224c32369e4118f` contains the Phase M control primitives, Phase N
one-command product baseline, Phase O Custom Evaluation foundation, and a corrected K-B3
configuration/preflight audit. It does not contain the K-B4 Diagnosis Platform, usable custom
execution, a public Adapter SDK, external benchmark validation, or the real evidence required to
close Core release.

The machine-readable authority for this audit is
`release/blueprint-reality-audit-2026-08-30.json`.

## Source boundary

The final HarnessLab post-K blueprint is unavailable. No tracked repository file defines the
acceptance criteria for K-C, L, P, Q, R, and S, and the supplied convergence brief names those
stages without defining all of them. This audit therefore uses only:

- the convergence brief's explicit K-B3, K-B4, M, N, O, P, Q/R, and S questions;
- repository architecture, methodology, release, and lane documentation; and
- source and tests at the audited integrated code head.

The classification of K-C is conditional on it meaning final Core release closure, which is the
closest repository-backed boundary. The audit does not assign inferred feature meanings to Q or R.
Their minimum remaining work is first to recover the authoritative blueprint.

Statuses mean:

- `IMPLEMENTED`: the major requirement has repository implementation and direct qualification
  evidence.
- `PARTIAL`: useful implementation exists, but a material part of the requirement is absent or not
  integrated.
- `MISSING`: no implementation satisfying the requirement exists at the audited head.
- `BLOCKED_BY_EVIDENCE`: the engineering boundary may exist, but the required real or authoritative
  evidence does not.
- `SUPERSEDED`: a prior conclusion or artifact is replaced by newer, more complete evidence.
- `NOT_YET_REQUIRED`: the task explicitly defers the phase, or its definition is unavailable and
  implementation would be speculative.

## Stage summary

| Stage | Status | Reality |
| --- | --- | --- |
| K-B3 | `BLOCKED_BY_EVIDENCE` | Configuration reconciliation is complete, but the exact successor cannot be frozen and no canary was acquired. |
| K-B4 | `PARTIAL` | Failure/evidence primitives exist; the unified diagnosis and attribution platform does not. |
| K-C | `BLOCKED_BY_EVIDENCE` | The release hard stop exists; final real evidence and exact-head release verification do not. |
| L | `PARTIAL` | Automated code-quality gates are strong; ownership/contribution governance is not tracked. |
| M | `PARTIAL` | Preflight, budget, lifecycle, quality, and split primitives exist; suites, clustering, and full funnel orchestration remain. |
| N | `PARTIAL` | One-command productization is implemented; active controls and released distribution evidence remain limited. |
| O | `PARTIAL` | Custom foundation is implemented; true custom execution and Workbench UX are missing. |
| P | `PARTIAL` | Internal seams are reusable; there is no supported public Adapter SDK. |
| Q | `NOT_YET_REQUIRED` | Definition unavailable; no meaning is inferred. |
| R | `NOT_YET_REQUIRED` | Definition unavailable; no meaning is inferred. |
| S | `PARTIAL` | Fast/Full CI exists; automated regression policy and external benchmark validation do not. |

## K-B3 — evidence re-entry

### Implemented or superseded

- Historical immutability is preserved. The convergence audit reports no old-Matrix resume, v3r1
  mutation, historical evidence rewrite, or full Matrix execution. Evidence:
  `release/kb3-convergence-reentry-audit.json` and
  `release/reports/core-real-matrix-v3-pause-checkpoint.json`.
- The earlier conclusion that legitimate configuration was absent is `SUPERSEDED`. The known
  private source was checked by name/presence and permission only and classified
  `CONFIG_SOURCE_VALID_NOT_SOURCED`. No value or endpoint was printed or persisted. Evidence:
  `release/kb3-convergence-reentry-audit.json`.
- Secret-file injection into Phase M preflight is implemented and qualified. Evidence:
  `docs/PHASE_M_EVALUATION_SYSTEM_2.md`, `src/harnesslab/preflight/io.py`, and
  `tests/test_phase_m_interfaces.py`.

### Partial or blocked

The completed Phase M run was configuration-focused and ended `BLOCKED` with
`BUDGET_ESTIMATE_REQUIRED`; it was not an exact successor authorization. More importantly, the
integrated audit found that the frozen seven-cell v3 plan and separate two-cell Alibaba plan do not
form one authoritative seven-cell successor binding. The current preflight schema also cannot
express all heterogeneous pricing, fixed Judge-campaign, and per-cell resource facts in one exact
manifest.

Consequently:

- `core-real-matrix-v4` has no plan digest and was not created;
- subject canary calls, Judge calls, and recovery attempts remain zero;
- projected subject, Judge, total cost, and wall clock remain `UNKNOWN`; and
- the current authorization decision is `REDESIGN_REQUIRED`.

This is `BLOCKED_BY_EVIDENCE`, not permission to alter a provider, model, route, or historical plan.
The historical timeout root cause remains `UNRESOLVED`.

## K-B4 — Diagnosis and Attribution Platform

The baseline is `PARTIAL`. Existing components should be reused:

- provider failures and transport phases in `src/harnesslab/model_lane/models.py`;
- Harness and capability/infrastructure distinctions in
  `src/harnesslab/harness_lane/models.py` and `src/harnesslab/experiment/outcomes.py`;
- verifier lifecycle failures in `src/harnesslab/sandbox/models.py`;
- run/trace inspection in `src/harnesslab/analyst/evidence.py`; and
- the enforced `VERIFIED_FACT`/`HYPOTHESIS` boundary in
  `src/harnesslab/analyst/models.py` and `src/harnesslab/analyst/report.py`.

These do not yet form the required platform. Material gaps are:

- one deterministic diagnosis taxonomy covering compile, test, timeout, provider, Harness
  protocol, tool, no-modification, wrong-files, protected-file, dependency, verifier, and artifact
  failures;
- canonical clustering across model, Harness, task, language, family, failure, trace, tool, and
  workspace-diff dimensions;
- the complete Experiment → Cell → Task family → Cluster → Run → Trace/diff/tool/verifier/
  attribution chain;
- diagnosis-specific attribution records that never treat correlation as causality and identify
  controlled-ablation support separately;
- deterministic BadCase export from eligible real capability failures; and
- a dedicated API and Workbench experience backed by the same analysis service.

`release/badcases.json` remains an honest three-slot placeholder. It must not be populated with
synthetic cases as if they were real evidence. The machine-readable requirement IDs under K-B4 are
stable so the status and evidence references can be updated after the isolated K-B4 implementation
lands.

## K-C — conditional Core release closure

If K-C is the final Core release boundary, it is `BLOCKED_BY_EVIDENCE`.

The fail-closed engineering boundary is implemented by `scripts/verify_gate_k.py`,
`src/harnesslab/release/final_verifier.py`, and `release/release-evidence.json`. A keyless pass proves
that incomplete evidence cannot authorize release; it does not prove readiness.

Still required are trusted final bindings for the real Matrix, paired comparison or explicit
no-uplift policy, controlled ablation, real Judge report, three factual BadCases, exact final
candidate commit, and successful exact-head Full Release CI. The final verifier must rebuild and
semantically validate those artifacts before any Core tag operation. This convergence phase does
not authorize the 630-run campaign, main merge, or tag creation.

## L — ownership and code quality

The code-quality half is `IMPLEMENTED`: `pyproject.toml`, `.github/workflows/ci.yml`,
`.github/workflows/full-ci.yml`, and `scripts/verify_gate_a.py` enforce pytest, Ruff lint and format,
strict mypy, migration checks, and whitespace integrity.

Ownership is `MISSING` under the ordinary meaning of that requirement. The repository has task
governance in `AGENTS.md`, but no tracked CODEOWNERS, OWNERS, MAINTAINERS, or contribution document.
Because the final Phase L blueprint is unavailable, this audit does not invent a team topology or
mandatory review policy. The minimum safe next step is to recover the acceptance criteria and then
add only the ownership artifacts they require.

Boundary convergence is `PARTIAL`. Provider, Codex, multi-Harness, and experiment protocols are
well typed but use several related adapter and failure contracts. K-B4 taxonomy convergence and a
future public Adapter SDK should reuse these seams without rewriting stable evidence contracts.

## M — Evaluation System 2.0

### Implemented

- Preflight: `src/harnesslab/preflight`, CLI/API registration, and
  `tests/test_phase_m_preflight.py`.
- Budget: `src/harnesslab/budget` and `tests/test_phase_m_budget.py`; unknown price remains unknown.

### Partial

- Lifecycle: `src/harnesslab/experiment/lifecycle.py` implements states, immutable attempt ledgers,
  and explicit infrastructure recovery authorization, but it is not wired as the authoritative
  transition engine for `experiment/queue.py` and `experiment/executor.py`.
- Task Quality: `src/harnesslab/tasks/quality.py` provides digest-bound records and fail-closed
  qualification semantics, but it consumes existing evidence and is not a production quality
  registry.
- Dev/Holdout: `src/harnesslab/tasks/splits.py` provides canonical freeze and leakage checking, but
  no audited production split manifest exists.
- Funnel Evaluation: `experiment/methodology.py` and `experiment/plan.py` define the stages and
  explicit GO/STOP semantics. They do not implement a complete campaign orchestrator that binds
  stage evidence and operator decisions to the next acquisition.

### Missing

- The Discriminative Suite is not implemented.
- The Stress Suite is not implemented.
- Failure Clustering is not implemented and should be supplied by the shared K-B4 diagnosis layer.

`docs/EVAL_METHODOLOGY_V2.md` and `release/evaluation-methodology-v2.json` explicitly describe
discriminative/stress as an optional future extension. A stage enum is not a qualified suite.

## N — Productization

The one-command baseline is `IMPLEMENTED`:

- `harnesslab up`, `down`, `status`, and `doctor` use the trusted lifecycle in
  `src/harnesslab/productization`;
- `docker/product/Dockerfile` and `docker-compose.yml` build the production service graph;
- `src/harnesslab/api/static.py` serves the compiled Workbench with deep-link fallback; and
- product lifecycle, distribution content, and bundled asset behavior have dedicated tests.

The broader phase remains `PARTIAL`:

- Settings intentionally exposes non-secret defaults and presence-only credentials; it is not an
  operator mutation surface.
- Run Control observes durable state and labels recovery boundaries, but does not issue authorized
  lifecycle operations.
- The source/wheel distribution contract is tested, but no published prebuilt artifact, installer,
  provenance binding, upgrade qualification, or supported-platform matrix is evidenced.
- Diagnosis and Custom Evaluation product navigation remain pending their backend execution
  boundaries.

These are remaining product capabilities, not grounds to rebuild the finished one-command shell.

## O — Custom Evaluation

The foundation is implemented:

- immutable managed storage and import provenance;
- package builder, strict criteria, and structural or explicit behavioral validation;
- Quick/Compare/Formal deterministic planning and custom-only reporting;
- CLI and API operations; and
- strict Official/Custom isolation.

Evidence is concentrated in `src/harnesslab/custom_eval`, `tests/test_custom_eval.py`, and
`docs/CUSTOM_EVALUATION.md`.

True usable custom execution is `MISSING`. The CLI has import, list, inspect, build, validate, plan,
and report commands but no run/execute command. The package intentionally does not call Provider,
Harness, Judge, or Official experiment execution. The next implementation must add a custom-only
execution binding, preflight, lifecycle, persistence namespace, and immutable evidence loading
while preserving the Official boundary. The Workbench also has no Custom Evaluation route.

## P — Adapter SDK

Reusable internal seams already exist:

- `ProviderAdapter` in `src/harnesslab/model_lane/models.py`;
- `HarnessAdapter` in `src/harnesslab/harness_lane/adapter.py`;
- `MultiHarnessAdapter` in `src/harnesslab/multi_harness/adapter.py`;
- `ExperimentLaneBinding` in `src/harnesslab/experiment/executor.py`; and
- `AnalystBackend` in `src/harnesslab/analyst/backend.py`.

This is `PARTIAL`, not an SDK. The public package has no versioned adapter API, entry-point group,
extension discovery, compatibility policy, conformance suite, template, security/provenance
contract, or migration guide. Phase P is explicitly outside the current convergence phase; these
internal protocols should be evaluated for stabilization later rather than broadly refactored now.

## Q and R — definitions unavailable

Both stages are `NOT_YET_REQUIRED`. The repository architecture lists several planned or excluded
future boundaries, but there is no evidence assigning any of them to Q or R. In particular, this
audit does not guess whether either stage means remote execution, RAG, MCP, distributed artifacts,
or another feature.

Minimum remaining work for each stage:

1. supply or recover the authoritative final blueprint;
2. define the stage's security, evidence, product, and qualification boundaries; and
3. rerun a source-backed audit before implementing it.

## S — CI, regression, and external benchmarks

Fast and Full CI architecture is already implemented:

- `.github/workflows/ci.yml` runs bounded deterministic checks on push and pull request and cancels
  stale work; and
- `.github/workflows/full-ci.yml` is the manual full gate/qualification/fresh-setup workflow.

Do not rebuild these workflows merely because Phase S is incomplete.

Regression capability is `PARTIAL`. The API and `frontend/src/views/RegressionView.vue` compare
persisted experiment reports under explicit comparability controls. That surface deliberately does
not claim significance, infer causality, or enforce a regression budget. A complete regression
system still needs versioned baselines, owners, thresholds, decision policy, and a fail-closed
automated gate.

External benchmark validation is `MISSING`. `docs/EVAL_METHODOLOGY.md` explicitly disclaims it for
the current Judge qualification. A future implementation needs governed source and license
provenance, contamination controls, task conversion, qualification, execution, and reporting that
remain distinct from both official Core and user Custom evidence.

## Machine-readable convention

The JSON artifact follows established repository conventions:

- `schema_version` and a stable `audit_id`;
- an exact audited code SHA and authoritative base SHA;
- a closed status vocabulary;
- stable per-requirement identifiers;
- repository-relative evidence references;
- explicit remaining work and limitations; and
- no timestamps, credential values, endpoint values, or inferred Q/R meanings.

This shape follows `release/resume-claim-evidence.json`, `release/release-evidence.json`,
`release/kb3-convergence-reentry-audit.json`, and the strict canonical evidence contracts under
`src/harnesslab/release`. `tests/test_blueprint_reality_audit.py` validates the closed schema,
stage coverage, status vocabulary, evidence-reference safety/existence, and Markdown linkage.
