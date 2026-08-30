# Task quality and development/held-out splits

Task quality records are immutable metadata around a task package, not fields added to historical
packages. A record copies the existing task ID, version, package digest, workspace digest, and
verifier digest. It therefore cannot rename or silently reinterpret a `1.0.0`, `1.0.1`, or
`1.0.2` package.

## Quality categories and qualification

Quality uses separate categorical axes and never a guessed numeric score:

| Family | Benchmark tier | Source | Default interpretation |
|---|---|---|---|
| `CORE` | `TIER_A` | `HARNESSLAB` | Core deterministic micro-contract task |
| `REPO_ENGINEERING` | `TIER_B` | `HARNESSLAB` | Qualified repository-engineering task |
| `IMPORTED` | `UNASSIGNED` | `IMPORTED` | Future imported task; no tier claim yet |
| `CUSTOM` | `UNASSIGNED` | `CUSTOM` | Future custom task; no tier claim yet |

The package's existing `repo_engineering` contract distinguishes built-in Tier-B packages from
built-in Tier-A packages. An explicit source kind distinguishes future imported and custom tasks;
those tasks remain `NOT_QUALIFIED` and `UNASSIGNED` until a future governed methodology assigns a
tier. Importing a package never promotes it to Core or Tier-B.

A `QUALIFIED` claim is digest-bound to categorical evidence. Tier-A requires package validity,
baseline fail, oracle pass, and deterministic health evidence. Tier-B requires those checks plus
the frozen repository snapshot, workspace and hidden-asset isolation, failing robustness variants,
and valid capability/infrastructure failure boundaries. Missing evidence fails closed. Evidence
identities may point at existing corpus and qualification artifacts; the quality layer does not
rerun tasks, make provider calls, or manufacture benchmark results.

## Development and held-out methodology

Each assignment binds the complete quality and qualification record and declares one role:
`DEVELOPMENT` or `HELD_OUT`. Development tasks must be marked `USED`. Held-out tasks must be
qualified and must explicitly be `NOT_USED`; `UNKNOWN` exposure is blocking rather than treated as
safe.

Before freezing, the leakage check blocks:

- an exact task identity in both sets;
- different versions of the same task ID across sets;
- a source or parent-provenance identity shared across sets;
- known or unknown held-out development exposure;
- unqualified held-out tasks; and
- empty or duplicate assignments.

Parent identities are the mechanism for recording shared generators, upstream benchmark items,
templates, or derivation sources. Operators must include known derivation lineage rather than
minting unrelated source identities for related tasks.

`freeze_split` sorts assignments canonically, embeds the deterministic leakage report, and hashes
the complete timestamp-free payload as `split_identity`. Input order does not affect the identity;
task, qualification, provenance, role, exposure, methodology, or split-ID changes do. Loading a
freeze recomputes both leakage and identity and rejects drift. A blocked split cannot be frozen.

This split is a preregistered assignment boundary, not a result. It contains no model or Judge
calls, no scores, and no post-outcome selection mechanism.
