# Codex H-Lane boundary

Phase E implements one H-Lane family: Codex CLI 0.149.0. It is distinct from Phase D M-Lane:

```text
M-Lane: model -> direct-patch-v1 response -> trusted patch application -> final workspace
H-Lane: Codex harness -> filesystem/tools -> final workspace
                                                    |
                                      isolated Hidden Verifier
```

In both lanes, the final workspace and the same hidden verifier determine correctness. Harness
self-report, native `file_change` events, and exit zero never substitute for verification.

## Frozen runtime and invocation

`docker/codex/Dockerfile` pins its Node base by immutable digest and installs exactly
`@openai/codex@0.149.0`. It runs as uid/gid 10001, contains the Python/Java/Node task toolchains,
and contains no credential, verifier, oracle, or Docker client/socket. Gate E executes
`codex --version` and `codex exec --help` in this image and records its immutable image ID.

The adapter builds argv directly and sends the deterministic `codex-harness-v1` prompt on stdin.
The frozen profile uses workspace-write sandboxing, approval `never`, disabled tool network and web
search, ephemeral state, ignored user config/rules, and no external MCP/plugins/skills. Requested
model is always recorded. Observed model is recorded only when native evidence exposes it;
otherwise it remains null with `not_exposed` status.

## Evidence path

The adapter contract is limited to `preflight`, `prepare`, `execute`, `collect`, and `normalize`.
It streams bounded JSONL, sanitizes every accepted line before persistence, and converts supported
events into Normalized Trace v1. Reasoning content is replaced with a structural
`REASONING_PRESENT` marker. Unknown safe schemas are retained as `UNKNOWN` structural evidence.

HarnessLab hashes the fresh workspace before Codex and the real filesystem after Codex but before
verification. Changed paths and per-path digests come from these snapshots, never from Codex's own
claims. Exact run credentials in paths or file content fail artifact publication closed. The Phase
C verifier then runs separately with read-only workspace/verifier mounts; its result and score are
bound into the immutable H-Lane evidence.

Harness failures are explicit: configuration, authentication only from structured native data,
timeout, cancellation, process error, protocol error, model-turn failure, profile violation, and
artifact error. These are not verifier failures. A completed turn may proceed after an intermediate
command error, while `turn.failed`, malformed/missing terminal JSONL, and unexplained non-zero
process exits fail in their respective categories.

## Deterministic and real execution status

Gate E uses Fake Codex scenarios through the same collection, sanitizer, trace, workspace, verifier,
and evidence path. Python, Java, and TypeScript fixtures each pass at score 1.0 after the fake
workspace mutation; negative cases prove self-report and native file-change claims are not
authoritative.

Real execution is never automatic and never consumes ambient `CODEX_HOME`, login state, quota, or
API keys. It requires explicit opt-in and credential configuration. The outer Docker backend is
hardened and subject network is denied; Phase E has not proven a safe provider-control-plane-only
network channel. Accordingly the default and Gate E result is `REAL_CODEX_SMOKE=NOT_RUN`, and no
real Codex model success is claimed.
