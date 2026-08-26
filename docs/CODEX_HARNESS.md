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

`docker/codex/Dockerfile` pins every Python, Java, and Node build stage by immutable digest and
installs exactly `@openai/codex@0.149.0`. It runs as uid/gid 10001 and contains Python 3.12,
Java/Javac 21, and Node 24, but no credential, verifier, oracle, or Docker client/socket. The
isolated verifier image provides the same required execution toolchains. A task's
`expected_tools` are part of H-Lane execution identity: Gate E derives its requirements from every
H-Lane task manifest, compares declared major or major/minor versions to both images, and records
both immutable image IDs and exact tool versions. Python 3.11 and Java/Javac 17 are explicit
sensitivity controls and must be rejected.

The adapter builds argv directly and sends the deterministic `codex-harness-v1` prompt on stdin.
The frozen profile uses strict configuration validation, workspace-write sandboxing, approval
`never`, disabled tool network and web search, ephemeral state, ignored user config/rules, and no
external MCP/plugins/skills. Requested model is always recorded. Observed model is recorded only
when native evidence exposes it; otherwise it remains null with `not_exposed` status.
The configured provider route is explicitly identified as `codex-cli-default`; this describes the
frozen CLI routing configuration and does not claim an observed provider-internal route.

The provider credential is injected only into the outer Codex control process. Codex 0.149.0 is
explicitly configured with shell environment inheritance `core`, default credential-name excludes
enabled, explicit `*KEY*`, `*SECRET*`, `*TOKEN*`, and `*PASSWORD*` excludes, and login shells
disabled. PATH, HOME, and normal language tools remain available, while Codex-spawned shell/tool
subprocesses cannot inherit provider credentials or unrelated parent secrets. This exact policy is
part of the frozen profile and therefore its fingerprint. Credential names, but never values, may
appear in Docker argv.

## Evidence path

The adapter contract is limited to `preflight`, `prepare`, `execute`, `collect`, and `normalize`.
It streams bounded JSONL, sanitizes every accepted line before persistence, and converts supported
events into Normalized Trace v1. Reasoning content is replaced with a structural
`REASONING_PRESENT` marker. Unknown safe schemas are retained as `UNKNOWN` structural evidence.

HarnessLab hashes the fresh workspace before Codex and the real filesystem after Codex but before
verification. Changed paths and per-path digests come from these snapshots, never from Codex's own
claims. A backend that injects a provider credential automatically declares that credential to the
runner's redaction, workspace, verifier, and artifact boundary; the caller does not repeat it.
Exact run credentials in paths or file content fail artifact publication closed. The Phase C
verifier then runs separately with read-only workspace/verifier mounts; its result and score are
bound into the immutable H-Lane evidence.
The task's verifier-definition digest and resource budget are also bound at the evidence top level
so Phase E manifests expose the same Comparability controls as Phase D and Phase F.

The real backend always attempts kill and forced removal in its `finally` path. Absence is verified
only when the final Docker container query succeeds and returns no match. A daemon or query failure,
including nonzero status with empty stdout, is not evidence of absence and raises a Harness adapter
error; timeout and cancellation cannot turn that unverified cleanup into successful execution.

Harness failures are explicit: configuration, authentication only from structured native data,
timeout, cancellation, process error, protocol error, model-turn failure, profile violation, and
artifact error. These are not verifier failures. A completed turn may proceed after an intermediate
command error, while `turn.failed`, malformed/missing terminal JSONL, and unexplained non-zero
process exits fail in their respective categories.

## Deterministic and real execution status

Gate E uses Fake Codex scenarios through the same collection, sanitizer, trace, workspace, verifier,
and evidence path. Python, Java, and TypeScript fixtures each pass at score 1.0 after the fake
workspace mutation; negative cases prove self-report and native file-change claims are not
authoritative. Fake Codex evidence remains deterministic fixture evidence and is never represented
as a real Codex model run.

Real execution is never automatic and never consumes ambient `CODEX_HOME`, login state, quota, or
API keys. It requires explicit opt-in and credential configuration. The outer Docker backend is
hardened and subject network is denied; Phase E has not proven a safe provider-control-plane-only
network channel. The post-R4 attempt reached Codex but produced no durable Codex call artifact, so the current Gate E result is `REAL_CODEX_SMOKE=NOT_VERIFIED`, and no
real Codex model success is claimed.
