# Fixed mixed full campaign — 2026-10-14

The user authorized the fixed 30 on 2026-10-14: retain the six original observations, run the
remaining 24 at most once, and stop on observed API-equivalent spend >= $20, including retained
fees. [Selection, revisions and licenses](MIXED_PROTOCOL.md) and [mixed-config.json](mixed-config.json)
were published before outcomes at `61b56e7fb4ad5932cbd27a49e9b5b351549a7193`. Environment failures
remain selected. No task replacement, Agent retry, best-of-N, Judge or manual verdict editing.

This is an **external direct Codex CLI campaign**. The product REAL_CODEX gate remains closed and
unchanged. Claude Code remains disabled. Full SWE repositories exceed existing import limits;
the saved task-specific UTF-8 `solution.patch` delivery enters the existing intake and isolated
Verifier. Complete repositories remain outside Git. A privacy-refused stream can use existing
code-only intake if its unchanged patch independently passes the same privacy checks; both the
refused stream and the import-mode receipt remain evidence. No import limit or product rule changes.

The three retained HumanEval observations retain their original standalone Docker verifier,
resource configuration and fees; they are not retroactively represented as current TaskStore
receipts. New HumanEval controls use existing admitted task/intake/Verifier, excluding generated
bytecode caches from the reviewed snapshot while preserving the complete original snapshot.

## Runtime and hidden assets

Use pinned native CLI 0.162.1, requested gpt-6.1-sol/high, existing ChatGPT credential **reference**,
provider-only egress, no upstream Git history, no hidden tests/oracle/control logs in Agent mounts.
Credentials live only in a read-only input mount and ephemeral Codex home. Captured logs redact
credential values and withhold private reasoning; wire-byte hashes do not make the redacted stream
a complete private transcript. Model alias, reported tokens and self-assessment do not attest the
actual serving model or API bill.

Every new SWE task must pass actual baseline F2P-fail/P2P-pass and gold-all-pass controls under the
unchanged product Verifier limits: 128 MiB, 0.5 CPU, 30 seconds, read-only root and mounts, no network
or credentials. Dependencies/compiled extensions are warmed into a content-ID image offline.
Missing offline dependencies, HTTP-dependent checks and resource failures stay environment failures.
Agent limits: SWE 900 seconds/4 GiB/2 CPUs; HumanEval 300 seconds/1 GiB/2 CPUs.

Adapter corrections preserve all original failed controls, package identities and code. They only
recover pre-Agent environment failures; a digest-linked successor requires original Agent attempts
and fee both zero. No executed Agent is rerun. Corrections use existing build dependencies without
PEP517 build isolation, reuse the pinned Astropy5.1 image's already-installed dependencies instead
of redundantly rebuilding offline, preserve pytest `src/` lookup and ordinary source paths, use Python3.6-compatible
gzip, and request verbose/classic reporting from legacy pytest. Required IDs, hidden tests, gold
patches and acceptance thresholds stay identical. Sphinx preserves upstream test-file order; SymPy
materializes its runner/path helper. Complete test output is gzip/base64 encoded through bounded
Verifier stderr, then decoded and cross-checked by the pinned official upstream parser.

## Measurement

Use the [fixed failure rules](README.md#measurement-and-classification). Explicit final
`SAMESCALE_SELF_REPORT=PASS` is self PASS; missing/conflicting claims are UNKNOWN. False completion
requires self PASS and independent FAIL and is an additional flag, not an assertion of deception.
Per user instruction, final pre-Agent setup/admission failures are ENVIRONMENT_FAILURE even when
the underlying control failed by timeout. All rates use the fixed selected denominators: 30 overall, 25 SWE, 5 HumanEval. NOT_RUN and
NOT_VERIFIED never count as passes. Report both environment failure counts and actual execution
counts. Agent and independent-verification seconds come from actual process/manifests. Initial
setup timing is separate; engineering/correction effort is not included in Agent time. A negative
resume-derived setup measurement is projected as unknown while keeping its original evidence.

New attempts use native OTLP `codex.sse_event` / `response.completed` counts. A private collector
persists only token counts, event timestamps and conversation identifiers; raw telemetry body,
prompts, tool output, account/email and credentials are discarded. Distinct event timestamps count
even with identical usage; exact duplicates do not. The meter includes zero-output startup responses
absent from `turn.completed.usage`, and must cover native turn counts before further paid work.
The original six keep their original turn-based cost estimates, so this measurement difference
is explicitly disclosed rather than rewriting original observations.

Standard equivalent per million: uncached input $2, cached input $0.10, cache-write $2.50, output
$10. For an individual reported response above 272,000 input tokens, input/cache rates double
and output increases 1.5x. Cache subsets are not counted twice; output includes reasoning tokens.
[Official price source](https://developers.openai.com/api/docs/models/gpt-6.1-sol).
The 50ms monitor kills the owned Agent on a received threshold/error marker and prevents subsequent
dispatch. Billing is observed after response completion: an in-flight response can cross the
threshold before termination. This is an observed equivalent-spend stop, not a prepaid API limit.
Actual subscription billing and unreported provider usage remain unknown.

## Reproduction

Use the locked repository environment, Linux x64 Docker, pinned images/native binary and the
external original input/pilot roots (including the external pinned upstream harness venv). No
credentials are included in archives. On another host, recreate that venv using the pinned harness
requirements described in MIXED_PROTOCOL; keep its lexical path rather than resolving the Python
symlink outside its venv. Docker image layers are separate prerequisites, not embedded in raw archives.

One command reproduces the full execution on a **new external output root**, retaining the original
six and using the final corrected adapter for the same fixed 24. It costs money and yields new model
outputs; exact numeric reproduction uses the saved offline evidence, not new stochastic responses.

```bash
uv run --locked python -m scripts.swe_full_run --all \
  --input-root /absolute/external/swe-inputs \
  --output /absolute/external/new-full-run \
  --swe-pilot /absolute/external/retained-swe-pilot \
  --human-pilot /absolute/external/retained-human-pilot \
  --codex-vendor /absolute/codex/vendor/x86_64-unknown-linux-musl \
  --auth-file /absolute/existing/auth.json --limit-usd 20
```

Generate or verify all30 derived rows without Docker/provider calls:

```bash
uv run --locked python -m scripts.swe_full_report report \
  --root /absolute/external/full-run --swe-pilot /absolute/external/swe-pilot \
  --human-pilot /absolute/external/human-pilot
# Same arguments; replay verifies receipts/exports, rows, fees, files, modes and symlink text.
uv run --locked python -m scripts.swe_full_report replay \
  --root /absolute/external/full-run --swe-pilot /absolute/external/swe-pilot \
  --human-pilot /absolute/external/human-pilot
```

For this observed run the original, failed and corrected protocol snapshots accompany the evidence;
the final repository code consolidates reporting/path fixes. Recreating only the final code cannot
recreate historical intermediate wrapper failures. Append-only results and digest-linked corrections
preserve that distinction. Frozen admission policies contain absolute paths; exact offline projection
uses saved raw bytes without needing to change those policies. Re-execution of acceptance on a new
machine requires explicit relocation and pinned image availability and produces new receipts.
