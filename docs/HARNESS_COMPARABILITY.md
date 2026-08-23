# Phase F multi-harness and comparability contract

## Frozen harnesses

Claude Code is pinned to `@anthropic-ai/claude-code@2.1.241` and npm integrity
`sha512-S7DWEmJJAsI5taAUjhKm6soXcFJYIVeTH6Lg9kmp3yntFllCP612hGwZ7thOGh8r7YaRUH9+1jCX5A9QGazsxg==`.
Its canonical invocation is equivalent to:

```text
claude --bare -p <claude-harness-v1 prompt> --output-format stream-json --verbose
       --no-session-persistence --permission-mode bypassPermissions --model <requested>
       --tools Read,Edit,Write,Bash --mcp-config {} --strict-mcp-config
       --disable-slash-commands --no-chrome
```

The initial `system/init` event must expose exactly Read, Edit, Write, and Bash and no MCP/plugin
state. Unexpected tools are a profile violation. Assistant text, tool use/results, lifecycle,
structured API retries, terminal results, and unknown safe events are retained. Thinking is only
`REASONING_PRESENT`; its content is not evidence. Trace coverage is `FULL_STREAM` for the accepted
native stream, not a claim to provider internals.

DeepSeek Harness is developer preview and pinned to `@deepseek-ai/dsh@0.1.1-rc.2` with npm
integrity
`sha512-UP1UIh6q3Gme/yXRn/QL2P8IsVlv8Shpg22TRJIZPsCRWLm4CBiA1MUvXmJAfsOEETBMLAl+xWPtFw6ICsN3wg==`.
E1 uses only the documented public invocation:

```text
dsh --profile headless <deepseek-headless-v1 prompt>
```

The process cwd is the fresh subject workspace and `DSH_HOME` is isolated inside the ephemeral
outer container. Gate F calls `--dump-default-config` and `--dump-config` and binds their digests
into runtime/profile evidence. It never calls a private JSONL test driver. E1 exposes only the
final answer, so its trace declares `FINAL_OUTPUT_ONLY`. The frozen dumped profile requests
`deepseek-v4-flash` through `deepseek-official`; observed model remains null because E1 does not
expose a routed model identity.

DeepSeek documents a plugin architecture, but Phase F found no public, stable contract that both
extracts the persisted headless session and avoids private implementation/test seams. E2 is
therefore `DEFERRED_NOT_VERIFIED`; no trajectory equivalence is claimed.

Both subject images run non-root, pin every base by digest, contain Python 3.12, Java/Javac 21,
and Node 24, and receive no verifier, oracle, Docker socket, or ambient home. Filesystem snapshots,
not harness file-change claims, determine changed paths. The Phase C isolated Hidden Verifier alone
determines pass and score.

Phase F also makes the existing Codex evidence contract explicit: its accepted native JSONL stream
declares `FULL_STREAM`. This preserves the Phase E profile fingerprint while allowing new Codex
manifests to participate in trace-coverage assessment without inference.

## Comparability assessment

`harnesslab compare assess LEFT RIGHT --intent harness-uplift` loads immutable M-Lane or H-Lane
manifest facts. Add `--json` for canonical structured output. The report contains both evidence
identities, every field comparison, reason codes and severities, declared intent, and status.

- `COMPARABLE`: all controls needed for the claim match; treatment differences are explicit.
- `PARTIALLY_COMPARABLE`: a nonfatal gap, such as absent observed model or reduced trace coverage,
  limits attribution while final outcome comparison may remain useful.
- `NOT_COMPARABLE`: a required control is missing/mismatched, or a known model identity conflicts
  with a harness-uplift claim.

For `HARNESS_UPLIFT`, task id/version/digest, input workspace, context, verifier definition/image,
requested model, provider route, resource budget, and network policy are controls. Harness name,
version, profile, and prompt are intended treatments. For `MODEL_COMPARISON`, model identity is the
treatment and harness identity is a control. `GENERAL` reports conservative field-level gaps.

Missing fields remain missing. The loader does not copy requested model into observed model, infer
trace coverage for older evidence, or treat null context as missing when the manifest explicitly
records that no context was supplied.

## Verification status

Gate F is keyless and non-recursive. Deterministic Claude and DeepSeek fakes each solve the Python,
Java, and TypeScript tasks through the real isolated Hidden Verifier. Negative controls remove the
workspace mutation while retaining success text, inject reasoning/secret values, drift DeepSeek
config, mutate uplift controls, hide/mismatch observed model, and reduce trace coverage. Missing or
skipped critical tests produce `NOT_VERIFIED`.

Real provider calls are optional and not Gate F evidence: `REAL_CLAUDE_SMOKE=NOT_RUN` and
`REAL_DEEPSEEK_SMOKE=NOT_RUN`.
