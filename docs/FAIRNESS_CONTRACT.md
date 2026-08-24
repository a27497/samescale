# Core Fairness Contract

HarnessLab treats fairness as an evidence contract, not a presentation choice. A Matrix cell is useful only when its treatment, controls, and missing evidence are explicit. This document summarizes the frozen Core rules; [HARNESS_COMPARABILITY.md](HARNESS_COMPARABILITY.md) and [EXPERIMENT_STATISTICS.md](EXPERIMENT_STATISTICS.md) remain authoritative for implementation details.

## Lanes and treatments

The Model-only lane calls a provider protocol directly with no coding harness. A Harness lane runs Codex, Claude Code, or DeepSeek Harness with its declared tool and prompt environment. “Model-only” and “Harness” are therefore different treatments. Harness uplift may be claimed only from a declared P-Lane whose hard controls pass the Comparability engine.

A controlled ablation changes exactly one declared dimension. The Core ablation changes Codex `reasoning_effort` from medium to high. Task, requested model, provider route, resource budget, network policy, container/toolchain, prompt contract, workspace, verifier, and every other hard control remain frozen. An observed association is not automatically a causal explanation.

## Identity that must be present

Every release observation binds:

- requested model and, when exposed, observed model;
- provider protocol, base URL, and route identity;
- task id, version, and digest;
- workspace-input and verifier identities;
- resource budget and network policy;
- harness/profile/config/prompt identities for Harness lanes;
- repeat index, paired-slot identity, and trace-coverage classification.

Requested and observed model are separate facts. A provider or harness may route differently from what was requested; missing observed identity lowers evidence strength and is never silently filled in.

## Comparability states

`COMPARABLE` means required hard controls are present and equal, with only the declared treatment differences. `PARTIALLY_COMPARABLE` preserves directional evidence when a non-hard fact such as observed-model identity or full trace coverage is missing. `NOT_COMPARABLE` blocks the intended strong comparison because a hard control is absent or mismatched.

K-B0 configures direct `gpt-5.6-sol` versus Codex medium through the same operator-trusted relay/Responses route identity. The pair is still `CONFIGURED_NOT_VERIFIED`: requested labels and display names cannot prove actual routing or observed model. Only authorized K-B1 evidence and the ComparabilityEngine may return `COMPARABLE`; otherwise no Harness-uplift claim is available.

## Denominators, repetitions, and ranking

Infrastructure failures remain outside the capability denominator. They are reported separately because treating an expired lease, provider outage, corrupt artifact, or runner failure as a wrong solution confounds system reliability with task capability. Exclusion is not erasure: counts and reason codes remain visible.

Repetition is per task. Formal repeated evidence requires at least five comparable observations for each task/cell or paired task slot; five pooled observations across unrelated tasks do not meet that bar. Per-task pairing controls task difficulty and supports explicit uncertainty estimates.

Arbitrary pooled rankings are unsafe because tasks differ in language, category, difficulty, missingness, and comparability. HarnessLab reports cell/task evidence, denominators, uncertainty, and exclusions before any aggregate. No single leaderboard number may conceal incompatible routes, incomplete cells, or infrastructure failures.

## Missing evidence

Unknown is never encoded as zero, failure, or success. Release artifacts use `NOT_RUN`, `NOT_VERIFIED`, `CONFIGURED_NOT_SMOKED`, `DEFERRED_NOT_VERIFIED`, and `INTEGRITY_ERROR`. K-B0 is keyless configuration and contract evidence only; it establishes no real ranking, uplift, latency, cost, Judge quality, regression, or production conclusion.
