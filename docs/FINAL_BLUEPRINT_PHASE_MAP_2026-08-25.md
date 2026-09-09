# HarnessLab Final Blueprint Phase Map — 2026-08-25

> Frozen Technical Lead source (2026-08-25). The text below is preserved for historical
> references. Maintain future planning in [Project Blueprint](PROJECT_BLUEPRINT.md) and
> current progress in [Project Status](PROJECT_STATUS.md).

This document is the authoritative final phase map supplied by the Technical Lead. It governs
phase naming and completion claims. Engineering primitives do not complete an evidence-bound phase
unless the phase's required real evidence also exists.

## Global principles

1. Close the evidence loop before expansion.
2. Require real evidence before new features.
3. Establish credibility before leaderboard appearance.
4. Use traces for diagnosis; require controlled ablation for causal claims.
5. Keep Custom Evaluation isolated from Official Benchmark evidence.
6. Treat RAG and MCP as controlled treatments.
7. Do not expand Memory or Multi-Agent behavior without a research question.

## K-B2 — Real Matrix Authorization Decision

After bounded real smoke, use actual tokens, latency, Harness internal turns, provider requests,
provider price, estimated Matrix cost, and expected wall clock. The decision is exactly one of
`AUTHORIZE_FULL_MATRIX`, `REDESIGN_PLAN`, or `STOP`.

## K-B3 — Core Real Matrix

Run 18 tasks × 7 cells × 5 repeats = 630 subject runs, followed by the real Judge campaign.
Required outputs include Model Results, Harness Results, Comparability, P-Lane, and Statistics.

## K-B4 — Real Analysis

Requires the Codex medium/high reasoning ablation, three real verifier-backed BadCases, failure
taxonomy, trace diagnosis, and an attribution report. Harness-uplift claims require Comparability
Engine approval. A diagnosis platform without the required real evidence does not complete K-B4.

## K-C — v1.0.0-core

Requires final Gate K, exact-head CI A–K, Real Matrix Evidence, Judge Evidence, Pair/Ablation
Evidence, three factual BadCases, a Release Claim Map, and Tag Guard authorization.

## L — Ownership and Code Quality

Requires Architecture Ownership, AI Code Audit, Technical Debt Cleanup, Human-led Refactor, Debug
Drills, and Interview Ownership.

## M — Evaluation System 2.0

Requires a Discriminative Suite, Stress Suite, Task Quality Tiers, Dev/Holdout, Cost and Budget,
Funnel Evaluation, Experiment Preflight, Run Lifecycle Upgrade, and Failure Clustering.

## N — Productization

Requires `harnesslab up`, the bundled Workbench, unified Model/Harness/Capability Registry UI,
Settings, Experiment Builder, Run Control Plane, and Diagnosis UX.

## O — Custom Evaluation

Requires External Repo Import, Managed Task Store, Task Builder, Custom Verifier,
Quick/Compare/Formal modes, Custom Report, and Official/Custom isolation.

## P — Adapter SDK and Ecosystem

Requires ModelProviderAdapter, HarnessAdapter, and JudgeAdapter SDKs, a Capability Registry, and
third-party adapter loading.

## Q — RAG Evaluation

Requires, at minimum, a controlled `Static Context vs Retrieved Context` comparison in a dedicated
RAG evaluation suite.

## R — MCP Evaluation

Requires, at minimum, a controlled `Native Tools vs MCP Tools` comparison in a dedicated Tool/MCP
evaluation suite.

## S — Regression, CI, and External Benchmarks

Requires progressive support for a CI Regression Gate, Historical Version Compare, External
Benchmark Import, SWE-bench subset compatibility, terminal-style task compatibility, and
Experiment Export/Import.
