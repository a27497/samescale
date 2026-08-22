# Evaluation methodology

Phase A establishes vocabulary and contracts. Phase B implements deterministic task validation,
Phase C isolates untrusted workspace verification, Phase D implements the first M-Lane direct
model path, and Phase E implements the Codex H-Lane. P/J lanes, the comparability engine,
experiment execution engine, and judges remain design-only.

## Evaluation lanes

- **M-Lane (Model-only Evaluation):** evaluate model capability through direct model execution,
  without a coding harness, while holding task conditions stable. Phase D supplies deterministic
  subject-visible text and accepts only a strict JSON patch; the model receives no tools, hidden
  verifier, or oracle.
- **H-Lane (Harness Evaluation):** evaluate a coding harness through its tools and workspace while
  holding the requested model, task, and verifier facts stable. Phase E records the Codex runtime,
  frozen profile, safe trajectory, and final workspace, then delegates correctness exclusively to
  the isolated hidden verifier.
- **P-Lane (Paired Model-vs-Harness Evaluation):** compare direct-model execution with harness
  execution on controlled micro tasks where the necessary context and verifier are equivalent, in
  order to measure harness uplift.
- **J-Lane (JudgeLab):** calibrate and compare judging methods against stronger references.

## Evidence hierarchy

**Deterministic Ground Truth > Human Gold > LLM Judge.** Hidden tests, builds, lint, schemas,
explicit rules, and protected-file checks must not be overridden by an LLM's preference. Human
gold labels cover questions deterministic checks cannot settle. LLM judges are calibrated aids,
not an authority over reproducible facts.

## Deterministic task polarity

A Phase B task package is accepted only when the untouched baseline fails its hidden verifier and
a separately materialized oracle overlay passes. This baseline-fail/oracle-pass rule detects
vacuous tests and broken reference solutions before the task can become evaluation evidence.
Verifier reports may contain bounded partial scores and per-check outcomes; a score is evidence,
not permission to reinterpret a failing verifier as a pass.

Malformed verifier output, timeout, non-zero verifier exit, or protected-file mutation fails
closed and remains distinguishable from an ordinary subject result. Phase B executes only trusted
repository fixtures on the host. It does not claim sandbox isolation for untrusted code.

## Outcome and trajectory

Outcome evidence asks whether the final artifact is correct. Trajectory evidence asks how the
system reached it: tool calls, retries, edits, costs, and policy compliance. A successful outcome
does not erase a problematic trajectory, and an efficient trajectory does not turn an incorrect
artifact into a success.

## Comparability

A comparison is meaningful only when task/version, workspace digest, prompt hash, verifier
version, provider route/protocol, harness version/configuration, reasoning budget, network policy,
sandbox image, and judge definition are recorded or controlled. Phase A contracts preserve these
facts but do not implement a comparability engine.

Requested model is the model identifier sent by the experiment definition. Observed model is the
identity reported or otherwise evidenced during the run. They can differ because aliases,
routing, fallbacks, or provider changes exist, so the Run contract stores them separately.

Phase D preserves both identities in direct-model evidence. A missing observed identity does not
invalidate an otherwise completed invocation; a mismatch remains explicit evidence for later
comparability analysis.

Phase E applies the same separation to Codex. If native JSONL does not expose the routed model,
`observed_model` remains null with `not_exposed` status; HarnessLab never copies the requested
identity into an observed field. This is evidence collection, not the Phase F comparability engine.

## H-Lane outcome authority

Codex public messages, native file-change events, and process exit status describe trajectory, not
task correctness. HarnessLab hashes the real workspace before and after Codex, scans artifacts for
run credentials, and sends the final workspace to the isolated deterministic verifier. Thus an
agent message claiming success followed by `turn.completed` and exit zero can still produce
`VERIFIED_FAIL`. Harness failures remain separate from verifier failures.

## Repeated experiments and failure attribution

Single runs are samples, not stable rankings. Planned evaluation will repeat comparable cells and
report uncertainty. Infrastructure failures (service outage, sandbox startup, credential routing)
must be classified separately from model failures; otherwise platform reliability contaminates
model attribution.

## Judge calibration

A planned judge must be calibrated against deterministic and human-gold cases, checked for bias
and consistency, and prevented from overruling deterministic ground truth. Phase A provides only
the schema field and methodology boundary.
