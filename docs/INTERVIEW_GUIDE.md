# Core Interview Guide

## Why Model × Harness × Judge?

HarnessLab separates Model, Harness, and Judge so their effects are not collapsed into one score. Deterministic L0 verification establishes task correctness; Harness evidence describes the execution system; calibrated L1 Judge evidence can add a rubric assessment but cannot override L0.

## Why not compare Direct Model and Harness naively?

Different model revisions, routes, budgets, prompts, workspaces, verifiers, or network policy can explain a difference. Comparability makes those controls machine-checkable. The K-A direct `/responses` versus Codex pair is a useful example: provider-route mismatch currently blocks an uplift claim.

## Why is infrastructure failure not model failure?

A provider outage, lease loss, corrupt artifact, or executor fault does not show that the subject produced a wrong solution. HarnessLab reports infrastructure reliability separately and keeps it outside capability denominators while retaining explicit exclusion counts.

## Why is n ≥ 5 per task?

Repeated observations must address variation for the same controlled task/cell or pair. Pooling one observation from five different tasks disguises task difficulty and does not create repeated evidence.

## Why PostgreSQL queue, lease, and heartbeat?

They provide durable ownership, recovery after worker loss, cancellation, retry boundaries, and observable state transitions with one already-required system. Redis, Celery, Kafka, and Kubernetes were not added because repository-scale requirements did not justify another distributed subsystem.

## Why immutable artifacts?

Plans, manifests, traces, and reports are addressed by deterministic identities and digests. Mutation or path escape becomes an integrity error instead of silently changing historical evidence.

## Why does the Judge need calibration, and why can it not override L0?

Judge behavior is probabilistic and rubric-dependent. The frozen public suite measures coverage and label behavior. Deterministic task verification remains the correctness authority; a Judge disagreement is evidence to inspect, not permission to rewrite L0.

## Why are the Workbench and Analyst read-only?

Evidence inspection must not mutate the runs being analyzed or trigger costly execution. The Workbench reads typed, integrity-checked projections. The Analyst has six bounded evidence tools, exact scope, and no arbitrary SQL, path, queue, provider, or browser execution surface.

## How does Phase J constrain hallucinated facts?

Claims marked as facts carry structured assertions checked against a catalog of returned tool evidence. Unknown or contradictory values and fabricated references are rejected. Explanations without direct support remain hypotheses.

## Why no RAG or Multi-Agent expansion?

The problem is bounded evidence retrieval from authoritative PostgreSQL and immutable artifacts, not broad document search. More agents or retrieval infrastructure would expand the trust boundary without providing missing release evidence.

## What will the three real BadCases demonstrate?

After Phase K-B, they should show a verifier-caught plausible wrong solution; a carefully controlled cross-lane difference or the inability to attribute one; and an infrastructure, missing-evidence, or Judge-disagreement case. Until then every slot is explicitly pending.

## What is not yet proved?

No real ranking, Harness uplift, latency/cost ordering, Judge quality, regression, or BadCase is claimed in K-A. Exact Model-only selections, explicit call authorization, trusted results, exact-head CI evidence, and the release tag remain blocked.
