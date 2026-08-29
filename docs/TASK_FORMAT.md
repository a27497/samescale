# Phase B task format

A task package is an immutable, versioned directory at `tasks/<task-id>/<version>/`. Its public
contract is `task.yaml`; the loader rejects duplicate keys, unknown fields, absolute or escaping
paths, and symbolic links.

## Layout

```text
tasks/<task-id>/<version>/
├── task.yaml
├── instruction.md
├── workspace/          # copied into each fresh subject workspace
├── context/            # optional, copied as declared context
├── verifier/           # hidden trusted verifier; never copied to the subject workspace
└── oracle/             # optional validation overlay; never copied to the subject workspace
```

The manifest identifies the schema version, task identity/version, lane, instruction, workspace,
optional context bundle, verifier entry point, optional oracle overlay, protected public paths,
expected tools, budgets, network policy, and metadata. Phase B validates representation and
polarity; it does not require context for any particular lane and does not implement lane
execution.

## Identity and materialization

The task digest hashes sorted POSIX-relative paths and exact bytes across the complete package.
The workspace digest independently identifies the subject-visible materialization. Neither digest
includes timestamps. Every baseline, subject, and oracle attempt receives a fresh temporary
workspace, so one attempt cannot contaminate another.

The subject runner receives only a materialized workspace plus explicit edits/deletions. It does
not receive the task package, hidden verifier, or oracle path. Oracle files are applied only to a
separate workspace used to validate task polarity.

## Verification and evidence

The hidden verifier emits one strict JSON report containing a boolean outcome, a bounded score in
`[0, 1]`, and per-check results. HarnessLab invokes it without a shell, bounds captured output,
applies a timeout, and treats malformed output, timeout, non-zero exit, or protected-file mutation
as a fail-closed infrastructure outcome. Immutable evidence records task/workspace/verifier
identity and output digests without embedding hidden verifier or oracle source.

A valid package must satisfy both conditions:

1. The untouched baseline produces a valid subject result and fails.
2. A fresh workspace with the oracle overlay produces a valid subject result and passes.

The Java and TypeScript fixtures require Java 21 and Node.js 24, respectively. Their host execution
is a controlled contract fixture, not a sandbox for untrusted code. Docker sandboxing, provider
adapters, and experiment workers are later-phase work.

## Optional Tier-B repository contract

Repo-scale tasks reuse the same package, digest, materialization, oracle, and evidence contracts.
They add `repo_engineering` to `task.yaml` with the fixed tier, frozen-workspace snapshot model,
an in-package hidden `robustness/` directory, and minimum multi-file oracle/negative-variant
counts. Existing packages omit this field, so their bytes and identities do not change.

Every `robustness/<variant>/` directory is an overlay representing a plausible incomplete repair.
It is trusted qualification input, never subject-visible material. Tier-B qualification requires
each overlay to terminate as a deterministic subject failure rather than verifier/platform
failure. See `docs/TIER_B_REPO_ENGINEERING.md` for the complete boundary.
