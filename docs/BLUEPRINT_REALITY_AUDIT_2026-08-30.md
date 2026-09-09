# HarnessLab Blueprint Reality Audit — 2026-08-30

> Historical audit at the head named below. Its phase restrictions and statuses apply to that
> baseline, not the current task. See [Project Status](PROJECT_STATUS.md) and the maintained
> [Project Blueprint](PROJECT_BLUEPRINT.md). The original audit body and JSON remain unchanged.

## Outcome

This audit applies the authoritative final phase map in
`docs/FINAL_BLUEPRINT_PHASE_MAP_2026-08-25.md` to convergence head
`1caae6e043830ce09059de632131d01f4214cac7`.

HarnessLab has a strong engineering foundation, but the real-evidence loop is open. Phase M/N/O
foundations and the K-B4 Diagnosis Platform are integrated. The K-B4 phase is not complete because
the controlled real ablation, three real verifier-backed BadCases, and final attribution evidence
do not exist. The project is entering K-B2R Matrix redesign; it has not entered or completed K-B3.

The machine-readable authority for this audit is
`release/blueprint-reality-audit-2026-08-30.json`.

## Source boundary

The authoritative source is the Technical Lead phase map dated 2026-08-25. Repository source,
tests, frozen evidence, and release controls at the audited head establish implementation reality.
The phase map defines K-B2, K-B3, K-B4, K-C, L, M, N, O, P, Q, R, and S; Q is controlled RAG
evaluation and R is controlled Tool/MCP evaluation.

Statuses mean:

- `IMPLEMENTED`: the requirement has implementation and direct qualification evidence.
- `PARTIAL`: useful implementation exists, but a material required part is absent or disconnected.
- `MISSING`: no implementation satisfying the requirement exists.
- `BLOCKED_BY_EVIDENCE`: engineering may exist, but mandatory real or authoritative evidence does
  not.
- `SUPERSEDED`: a prior conclusion or artifact has been replaced by newer evidence.
- `NOT_YET_REQUIRED`: the defined phase is downstream of the current evidence gate and must not be
  implemented yet.

## Stage summary

| Stage | Status | Reality |
| --- | --- | --- |
| K-B2 | `PARTIAL` | Keyless configuration and bounded controls exist, but no valid seven-cell canary or evidence-backed cost/wall-clock dossier exists; K-B2R redesign is current. |
| K-B3 | `NOT_YET_REQUIRED` | The Core Real Matrix must wait for K-B2 authorization of a newly frozen successor; no 630-run campaign is authorized. |
| K-B4 | `BLOCKED_BY_EVIDENCE` | The Diagnosis Platform is implemented, but the real ablation, three factual BadCases, and real attribution report are absent. |
| K-C | `BLOCKED_BY_EVIDENCE` | Gate K is fail-closed; Real Matrix, Judge, pair/ablation, BadCase, claim-map, and Tag Guard evidence remain absent. |
| L | `PARTIAL` | Automated quality is strong; ownership, AI audit, debt cleanup, human refactor, debug drills, and interview ownership remain incomplete. |
| M | `PARTIAL` | Preflight, budget, lifecycle primitives, quality, splits, and clustering exist; discriminative/stress suites and full funnel/lifecycle integration remain. |
| N | `PARTIAL` | One-command productization and Workbench foundations exist; unified active registry/settings/control-plane completeness remains limited. |
| O | `PARTIAL` | Managed Custom Evaluation foundations exist; true external-repo execution and Workbench custom flow remain incomplete. |
| P | `PARTIAL` | Internal adapter seams exist; public ModelProvider/Harness/Judge SDKs and third-party loading do not. |
| Q | `NOT_YET_REQUIRED` | The controlled Static Context vs Retrieved Context RAG suite is defined but intentionally not implemented before the evidence loop closes. |
| R | `NOT_YET_REQUIRED` | The controlled Native Tools vs MCP Tools suite is defined but intentionally not implemented before the evidence loop closes. |
| S | `PARTIAL` | Fast/Full CI exists; regression gating, historical comparison governance, external imports, compatibility targets, and experiment interchange remain incomplete. |

## K-B2 — Real Matrix Authorization Decision

The current state is `K-B2R_REAL_MATRIX_REDESIGN`. Secret-safe configuration reconciliation and
Phase M preflight exist, but the attempted successor was not frozen and acquired zero calls. The
prior `REDESIGN_REQUIRED` decision is therefore a redesign entry, not a permanent K-B3 block.

K-B2 remains `PARTIAL` until a bounded, frozen seven-cell canary produces actual tokens, latency,
Harness turns, provider requests, trace/observed-model coverage, pricing where available, projected
630-subject and 63-Judge cost, and expected wall clock. Its final decision must be
`AUTHORIZE_FULL_MATRIX`, `REDESIGN_PLAN`, or `STOP`.

Historical timeout root cause remains `UNRESOLVED`. Old Matrix and Model Chat v2/v3/v3r1 evidence
remain immutable and may be used only as design references.

## K-B3 — Core Real Matrix

K-B3 is `NOT_YET_REQUIRED` because K-B2 has not authorized a frozen successor. The blueprint target
remains 18 task-version 1.0.2 tasks × 7 cells × 5 repeats = 630 subject runs followed by the fixed
real Judge campaign. Required outputs are Model Results, Harness Results, Comparability, P-Lane,
and Statistics.

No successor digest, seven-cell canary, full Matrix evidence, or real Judge campaign exists. This
audit does not revive v3, graft v3r1 onto it, or authorize acquisition.

## K-B4 — Real Analysis

### Platform status: `IMPLEMENTED`

The shared backend and Workbench platform provides the closed failure taxonomy, capability versus
infrastructure separation, deterministic multidimensional clustering, full drill-down, explicit
`VERIFIED_FACT` versus `HYPOTHESIS`, and fail-closed BadCase export. Controlled-ablation membership
strengthens association but never becomes a causal claim. Synthetic qualification never counts as
real evidence.

### Phase status: `BLOCKED_BY_EVIDENCE`

The phase additionally requires the real Codex medium/high reasoning ablation, three real
verifier-backed BadCases, trace diagnosis over the real campaign, and a final attribution report.
Harness-uplift claims require Comparability Engine approval. None of that real evidence exists, so
the platform must not be reported as K-B4 completion.

## K-C — v1.0.0-core

K-C is `BLOCKED_BY_EVIDENCE`. Gate K and the final verifier fail closed, but release requires final
Gate K, exact-head A–K CI, Real Matrix Evidence, Judge Evidence, Pair/Ablation Evidence, three
factual BadCases, a Release Claim Map, and Tag Guard authorization. Engineering promotion to main
does not authorize the Core tag or claim K-B3/K-B4 completion.

## L — Ownership and Code Quality

Automated code quality is implemented through pytest, Ruff, strict mypy, migration checks,
whitespace enforcement, Fast CI, and Full Release CI. The broader phase remains `PARTIAL` because
Architecture Ownership, AI Code Audit, Technical Debt Cleanup, Human-led Refactor, Debug Drills,
and Interview Ownership are not complete tracked outcomes.

## M — Evaluation System 2.0

Implemented foundations include experiment preflight, simple cost/budget estimation, lifecycle
models, task-quality records, development/holdout split freezing, and failure clustering.

Material gaps keep the phase `PARTIAL`:

- no qualified Discriminative Suite;
- no qualified Stress Suite;
- no governed production quality-tier and dev/holdout manifests;
- no complete funnel orchestrator binding stage evidence and operator GO/STOP decisions;
- lifecycle/recovery models are not the authoritative queue/executor transition engine; and
- the existing simple preflight/budget schema does not represent heterogeneous seven-cell and
  fixed Judge campaigns.

## N — Productization

`harnesslab up/down/status/doctor`, production Compose, bundled Workbench, Experiment Builder,
registry views, Run Control observation, and Diagnosis UX exist. The phase remains `PARTIAL` because
the Model/Harness/Capability Registry is not a fully unified active control plane, Settings are
presence-oriented, recovery actions are not wired through Run Control, and no published supported
multi-platform distribution is evidenced.

## O — Custom Evaluation

Managed storage, import provenance, Task Builder, custom verifier criteria, Quick/Compare/Formal
plans, custom-only reports, and Official/Custom isolation exist. The phase remains `PARTIAL` because
external-repository import is local-package oriented, custom plans cannot execute through approved
Model/Harness runners, and the Workbench has no end-to-end Custom Evaluation flow.

## P — Adapter SDK and Ecosystem

Internal Provider, Harness, multi-Harness, experiment-lane, and analyst protocols are reusable.
They are not a supported SDK. Public ModelProviderAdapter, HarnessAdapter, and JudgeAdapter SDKs,
stable compatibility contracts, capability registration, provenance/security controls,
conformance tests, and third-party adapter loading are missing. Phase P is defined but deliberately
deferred until the evidence loop closes.

## Q — RAG Evaluation

Q is defined as a dedicated controlled RAG suite comparing `Static Context` with `Retrieved
Context`. It is `NOT_YET_REQUIRED`, not undefined and not implemented. Future work must freeze the
retrieval corpus, contamination controls, retrieval policy, context budgets, trace evidence, and
paired analysis without mixing RAG treatment effects into the Core Matrix.

## R — MCP Evaluation

R is defined as a dedicated controlled Tool/MCP suite comparing `Native Tools` with `MCP Tools`.
It is `NOT_YET_REQUIRED`, not undefined and not implemented. Future work must freeze tool
capabilities, MCP server identity, network/security policy, call budgets, trace semantics, and
paired analysis without contaminating Core evidence.

## S — Regression, CI, and External Benchmarks

Fast and manual Full Release CI architecture is implemented. The Workbench can compare persisted
experiments under comparability controls. The phase remains `PARTIAL` because it lacks a governed CI
Regression Gate, versioned historical-baseline policy, external benchmark import, SWE-bench subset
qualification, terminal-style compatibility qualification, and experiment export/import.

## Machine-readable convention

The JSON artifact records the authoritative phase-map reference, exact audited code SHA, closed
status vocabulary, stable requirement identifiers, repository-relative evidence references,
remaining work, and explicit limitations. It contains no credentials, endpoint values, or invented
evidence. `tests/test_blueprint_reality_audit.py` verifies the authority, stage coverage, K-B4
platform/phase separation, Q/R definitions, evidence references, and Markdown linkage.
