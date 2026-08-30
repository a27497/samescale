# Custom Evaluation

Custom Evaluation is a separate, keyless control plane for user-owned task packages. It does not
extend Official task discovery and it is never an Official benchmark input.

## Managed store

The store has two layers:

- `snapshots/<identity>/package/<task-id>/<version>/` is a read-only, content-addressed package.
- `index/<task-id>/<version>.json` binds one custom id/version to one immutable snapshot.

The snapshot identity binds the `CUSTOM` namespace, complete task content, ownership, category,
and structured criteria. Every read re-hashes the package, workspace, verifier, and criteria.
Re-importing identical content is idempotent; reusing an id/version for different content fails.
The store rejects locations inside `tasks/` and `release/`.

Frozen provenance records source type, exact source commit when applicable, source content
identity, UTC import time, managed snapshot identity, owner/category, and namespace. Supported
imports are a local folder, a local repository subpath, a prepared HarnessLab package, or a Git URL
at an exact 40-character commit. Remote Git transport is denied by default and must be explicitly
enabled outside CI; tests use local repositories only. Package paths reject traversal, and packages
containing symlinks or junctions are rejected by the standard task package loader.

## Builder and criteria

The builder copies an instruction, workspace, verifier, and oracle into the standard versioned task
layout, writes strict `task.yaml` and `custom-eval.yaml` manifests, then loads the output through the
standard `TaskPackage` validator before returning it. Sources containing links are rejected. A built
package can be imported without editing HarnessLab source.

`custom-eval.yaml` supports build, unit-test, hidden-test, contract, security, performance-threshold,
structured deterministic-rule, and optional Judge-rubric criteria. Deterministic criteria are L0:
any deterministic failure fixes the capability result to failure even if supplied Judge evidence
passes. This subsystem consumes already-recorded Judge evidence only; it contains no Judge or
provider execution path.

## Presets and reports

The presets reuse the canonical methodology `EvaluationMode` repeat semantics:

| Preset | Methodology mode | Repeats |
|---|---|---:|
| Quick | `QUICK` | 1 |
| Compare | `INFORMAL` | 3 |
| Formal | `FORMAL_EXHAUSTIVE` | 5 |

Plans are timestamp-free, content-addressed, and contain only `CUSTOM` snapshots. Reports reuse the
canonical statistical outcome and cell-summary primitives while preserving custom task identities,
selected model/harness, deterministic evidence, capability pass/fail rate, separately disclosed
missing and infrastructure counts, cost availability, trace availability, and comparability limits.
Custom n=1 is explicitly smoke evidence and cannot support a universal model claim. Custom reports
are never Official benchmark reports.

## CLI and API

Use `harnesslab custom-eval --help` for `import`, `list`, `inspect`, `build`, `validate`, `plan`, and
`report`. The default store is `.runtime/custom-eval`; pass `--store` to select a managed location.
Structural validation is inert. Behavioral baseline/oracle verification is available only through
the explicit `validate --execute-verifier` CLI flag.

The API exposes equivalent operations below `/api/custom-eval`. Set
`HARNESSLAB_CUSTOM_EVAL_STORE` to a server-owned storage location. API validation intentionally
performs structural and immutable-identity checks without executing imported verifier code.

## Isolation contract

Custom task code does not import or call Official discovery, Tier-A/Tier-B qualification, release
freeze, experiment execution, provider, or Judge runners. Official `ExperimentSpec` continues to
accept only paths below `tasks/`; custom planning resolves only managed snapshot references and
marks every plan/report `official_benchmark_eligible=false`. Integration into a future execution
orchestration layer should consume `CustomEvaluationPlan` as an explicit separate namespace instead
of widening Official discovery.
