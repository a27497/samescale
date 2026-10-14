# SWE-bench mixed-set preparation — 2026-10-14 (Asia/Shanghai)

**Fixed selection published; environment admission partial; real SWE Agent pilot BLOCKED.**

**Successor update: latest environment admission is now 3/3 PASS (0/3 failure).**
Sphinx's final correction passes reporting arguments directly through `tox ... --` to pytest,
adding only `-rA --color=no`. Its baseline evidences the expected F2P failure and all 44 P2P passes;
gold evidences all 45 required passes. No oracle/test/membership or acceptance threshold changed.
Four non-required aggregate failures remain; admission never claimed the entire suite passed.
Initial setup failure **3/3 (100%)** and every intervening failure remain preserved; the first
strict direct-command matcher refused before tests because the upstream command includes tox flags,
then the corrected one-command matcher ran actual controls. No result/marker was fabricated.
[Latest generated report](report-v2.json) · [latest external artifact receipt](artifact-receipt-v2.json).
The intermediate 2/3 report below retains its dated observation and is superseded by this update.

Latest raw archive: `/home/dev/.local/state/samescale-eval/swe-mixed-preflight-20261014-v2.tar.gz`, SHA-256 `31f5c9eb181bc1b870e6b0c4301f605d606bf6ebeb1c74d15b09cf1ba2b52fa5`.
The prior archive/receipts remain byte-identical. Full new inventory and six retained phase offline
replays PASS; 0 model/Docker/credential calls during review. Use replay label
`preflight-sphinx-direct-fixed` for the latest Sphinx evidence. REAL_CODEX remains unchanged/closed;
actual SWE Agent trial, rates/time/token/cost and mixed full estimates remain unknown/NOT_RUN.

The user canceled the unexecuted HumanEval-only full stage. The replacement contains 25 SWE-bench
Verified tasks plus HumanEval 122, 33, 153, 121 and 25. Original first-three HumanEval observations
remain unchanged and retain their standalone/native capture scope, not product-gate compliance.

Selection commit **`61b56e7fb4ad5932cbd27a49e9b5b351549a7193`**, PR #21 updated **2026-10-14T08:26:37Z**;
first Docker-control image pull began **2026-10-14T08:27:06.635120+00:00**. All IDs, upstream
revision, per-repository hash rule, distinct-repository pilot choice, base-license references and
OCI image digests were published before controls. **No membership changes or replacement.**
[Fixed mixed config](../../../evaluation/coding-agent/mixed-config.json) ·
[protocol, licensing boundaries, scope and reproduction](../../../evaluation/coding-agent/MIXED_PROTOCOL.md).

| Fixed SWE pilot | Latest environment admission | Agent self-report | Independent Agent acceptance | Agent time | Agent fee | Cached pull / baseline control / gold control |
| --- | --- | --- | --- | --- | --- | --- |
| astropy__astropy-8872 | PASS | NOT_RUN | NOT_RUN | 未知 | 未知 | 1.218 / 90.594 / 90.886s |
| sphinx-doc__sphinx-8120 | FAIL | NOT_RUN | NOT_RUN | 未知 | 未知 | 1.218 / 9.036 / 9.540s |
| sympy__sympy-20916 | PASS | NOT_RUN | NOT_RUN | 未知 | 未知 | 1.368 / 4.726 / 4.827s |

These control times are **not Agent timings**, do not include all host preparation/grading overhead,
and use cached images after the initial pulls. Astropy required 81 named checks (one F2P, 80 P2P),
SymPy required two (one F2P, one P2P); both baseline and gold controls satisfy the fixed rule. Sphinx
requires 45 named checks (one F2P, 44 P2P); positive named passing statuses remain missing, and
its gold aggregate still reports four failures. It remains **not admitted**; no inferred pass,
manual verdict correction, parser weakening or task replacement. Actual reference-control logs,
test patches and graders are external and separately bound.

## Failure rates, corrections and limits

- **Initial first-attempt setup/orchestration failure: 3/3 = 100%.** The wrapper resolved the
  virtualenv Python symlink to the host interpreter, losing its installed SWE-bench dependency.
  This is the campaign script's failure, not three demonstrated repository setup failures or Agent
  failures. Original bounded error receipts remain; the initial helper stderr was not saved by that
  first exception handler. Later exceptions save subprocess stdout/stderr; no raw Agent data was lost.
- `preflight-corrected`: same three IDs ran actual tests, but native stderr markers were separated
  from stdout and the official parser saw no test region. **3/3 failed qualification**; logs retained.
- `preflight-merged`: real streams merged at the process as the official harness expects, with no
  synthetic markers. **Astropy/SymPy PASS; Sphinx FAIL**. A separately labeled Sphinx-only correction
  added reporting-only `PYTEST_ADDOPTS=-rA --color=no`; tox does not forward it, so positive named
  PASS statuses remain unavailable and Sphinx still fails. This correction is **one attempt**, not
  a new three-task pilot or a change to the fixed membership.
- **Latest admission failure: 1/3 = 33.3%; 2/3 environments admitted.** This does not overwrite the
  initial 100% failure rate. All control phases and exact code snapshots are retained outside Git.
- All 25 published images were found; **22 non-pilot environments have no local admission result**.
  A manifest is not proof of local test compatibility. Upstream/published runtime dependencies can
  differ from the original benchmark date; full test summaries can include non-required failures.
  PASS here means the required upstream F2P/P2P checks satisfy the stated admission rule.

## Real gate and full estimate

Existing `deny_real_execution()` returns **403 / REAL_EXECUTION_BLOCKED**, with credential isolation,
live route/quota/request controls and SIWC/account/OAuth lifecycle eligibility still unverified.
The product gate source is unchanged. Both new mixed real commands and the old paid entrypoint
invoke it before credential/root acquisition. Environment flags cannot override it. No alternative
provider, direct CLI, private login import or real dispatcher is introduced by this work.

**SWE Agent attempts 0; new model calls 0.** Agent self-report/independent pass rates, gap, token usage,
time, per-task fee and mixed 30-task full token/fee/time estimate are **UNKNOWN/NOT_RUN**, never
0%/100% or extrapolated from function tasks. The original HumanEval cost numbers keep their
original scope; they are not evidence for repository-task costs. Real trial would need existing gate
prerequisites/admitted task/runtime/one-attempt controls first, plus resolution of Sphinx admission.
**STOP here; no real pilot or mixed full run is authorized around those blockers.** Once three
actual gated SWE attempts exist, report their metrics and stop again for full-stage user confirmation.

## Evidence and reproduction

[Generated report](report.json) · [archive/digest/source receipts](artifact-receipt.json).
External archive: `/home/dev/.local/state/samescale-eval/swe-mixed-preflight-20261014.tar.gz` (3,458,471 bytes),
SHA-256 **`d0d3ce6cf532b554a785825a7196a41956f32de53c2543ac07b8998ae5c608e1`**. It contains the pinned dataset, original license notices,
base/gold raw logs, process/container receipts, frozen inputs, all correction phases and source
snapshots. External tooling/OCI image cache is not bundled. Raw evidence is not in Git; no model
credential/private reasoning is included. It is local separate storage, not a remote release asset.

```bash
# New keyless environment preparation; never starts an Agent:
bash evaluation/coding-agent/run-swe-preflight.sh /new/external/campaign /locked/upstream/python /original/humaneval/pilot-summary.json
# Saved archive review: no upstream toolchain, Docker, credential, model or code execution:
uv run --locked python -m scripts.swe_mixed_eval replay --root /unpacked/swe-mixed-20261014 --preflight-label preflight-merged
uv run --locked python -m scripts.swe_mixed_eval replay --root /unpacked/swe-mixed-20261014 --preflight-label preflight-sphinx-reported
uv run --locked python -m scripts.swe_mixed_eval gate
```

After extraction, complete inventory hashes and each phase's two identical offline replays **PASS**.
Each replay compares saved qualification with actual positive/negative graded evidence and its
file hashes, retaining unresolved failures. Original HumanEval replay still matches its frozen
summary byte-derived data; original archive SHA remains unchanged.

Focused keyless tests **43 PASS, one database integration case deselected**; changed Ruff/format,
strict mypy, Bash syntax and local documentation links **PASS**. Environment correction regressions
cover venv symlink preservation and actual stderr-marker/stdout-test ordering, plus zero/missing/gold
failure refusal and unconditional gate denial even with enablement vars. No existing database,
service, dependency lock, product gate or original dirty worktree change. Campaign control
containers removed; image caches remain outside Git. Remote CI is checked separately at the final
pushed head; local checks and keyless controls do not constitute a successful real Agent pilot.
