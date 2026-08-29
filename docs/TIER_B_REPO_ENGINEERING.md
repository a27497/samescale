# Tier-B repo engineering benchmark

Tier B is a small repo-level layer on the existing HarnessLab task architecture. It does not
introduce a SWE-bench clone, a second runner, or a long-horizon agent protocol. The same immutable
task package, fresh materialization, sandbox runner, evidence manifest, experiment slot, and
read-only Workbench task representation continue to apply.

## Corpus v1

| Task | Language | Engineering shape | Oracle production files |
|---|---|---|---:|
| `repo-python-ledger-transfer@1.0.0` | Python | SQLite atomicity, idempotency, rollback, and durable reopen | 2 |
| `repo-java-widget-update@1.0.0` | Java 21 | Cross-module API/service/repository optimistic update | 3 |
| `repo-typescript-resilient-client@1.0.0` | TypeScript | Environment config, factory wiring, injected transport, and retry behavior | 3 |

Each workspace is a complete frozen repository snapshot identified by the existing workspace tree
digest. The complete task package digest also covers instructions, public contracts, hidden
verifier, oracle, self-health workspace, and robustness overlays. Changing semantics requires a
new task version.

## Verifier and failure model

The verifier is `hidden-repository-contract-v1`. Its small trusted wrapper first runs the hidden
contract against a verifier-owned healthy workspace. Only after toolchain and hidden-test
self-health pass does it evaluate the candidate workspace in a separate worker process.

- Candidate import, compile, test, or runtime defects emit a valid `subject_result` failure.
- Verifier worker, protocol, self-health, timeout, or malformed-output defects fail closed as
  infrastructure through the existing verifier categories.
- Protected public contract mutations remain `protected_file_violation`.
- Hidden verifier, oracle, health workspace, and robustness overlays are never materialized for
  the subject.

The verifier uses only local Python 3.12, SQLite, Java/Javac 21, and Node 24 toolchains. It performs
no network access and reads no credentials. The shared sandbox image is versioned `0.3.1`; it adds
the SQLite runtime library required by the already-present CPython `_sqlite3` module.

## Qualification v1

`release/tier-b-qualification-v1.json` is a deterministic, timestamp-free addendum rather than a
rewrite of frozen Tier-A methodology or corpus evidence. For every task it records task, snapshot,
verifier, oracle, baseline terminal, oracle terminal, and partial-fix terminal identities.

Qualification requires:

1. untouched baseline `FAIL` repeated five times with identical terminal facts;
2. multi-file oracle `PASS` repeated five times with identical terminal facts;
3. two or more plausible partial overlays, each `FAIL` repeated five times as capability evidence;
4. fresh-workspace isolation and stable tree digests;
5. no hidden asset names in subject materialization;
6. protected-file mutation classified separately from capability; and
7. verifier-owned fault classified as infrastructure.

Rebuild or verify it keylessly:

```bash
uv run --locked python scripts/qualify_tier_b.py
uv run --locked python scripts/qualify_tier_b.py --check
```

## Planning and Workbench compatibility

Schema-v2 planning still uses the active methodology-v2 controls and five-run task-health gate.
A Tier-B plan additionally requires `tier_b_qualification_path`; the plan persists the benchmark
tier, qualification ID, and qualification digest. The planner rejects mixed Tier-A/Tier-B plans
so reports cannot pool distinct difficulty tiers.

Experiment tasks already carry task/version/digest identities, so the persistence schema,
execution queue, sandbox, evidence readers, and Workbench task/suite views need no parallel Tier-B
representation. Historical plans omit the optional new fields and retain their canonical JSON.

## Explicit non-goals

Tier B does not add provider evidence, Judge execution, network dependencies, secrets, mutable
benchmark databases, historical run resumption, autonomous milestones, or Tier-C semantics.
