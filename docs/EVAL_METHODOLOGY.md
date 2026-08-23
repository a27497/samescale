# Evaluation methodology

Phase A establishes vocabulary and contracts. Phase B implements deterministic task validation,
Phase C isolates untrusted workspace verification, Phase D implements the first M-Lane direct
model path, Phase E implements the Codex H-Lane, and Phase F adds Claude/DeepSeek H-Lanes plus
deterministic evidence comparability. Phase G implements the experiment engine, repeated-run
statistics, P-Lane pairing, and controlled ablation. Judges remain design-only.

## Evaluation lanes

- **M-Lane (Model-only Evaluation):** evaluate model capability through direct model execution,
  without a coding harness, while holding task conditions stable. Phase D supplies deterministic
  subject-visible text and accepts only a strict JSON patch; the model receives no tools, hidden
  verifier, or oracle.
- **H-Lane (Harness Evaluation):** evaluate a coding harness through its tools and workspace while
  holding the requested model, task, and verifier facts stable. Phases E/F record frozen runtime,
  profile, safe trajectory coverage, and final workspace, then delegate correctness exclusively
  to the isolated hidden verifier.
- **P-Lane (Paired Model-vs-Harness Evaluation):** compare direct-model execution with harness
  execution on controlled micro tasks where the necessary context and verifier are equivalent, in
  order to measure harness uplift. Phase G pairs exact task/repeat slots and requires the Phase F
  Comparability result before a pair can enter formal statistics.
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

A comparison is meaningful only when task/version/digest, input workspace, context, verifier,
requested and observed model, provider route, resource budget, network policy, harness/profile,
prompt, and trace coverage are explicit. Phase F implements a deterministic assessment of these
facts; it does not infer absent identities.

For `HARNESS_UPLIFT`, task/workspace/context/verifier/model/route/budget/network fields are hard
controls, while harness/profile/prompt differences are intended treatments. A missing observed
model yields `PARTIALLY_COMPARABLE`; a known observed-model mismatch yields `NOT_COMPARABLE`.
Incomplete trace coverage limits trace-dependent attribution but does not erase final correctness.
`MODEL_COMPARISON` treats requested/observed model differences as its declared treatment.

Requested model is the model identifier sent by the experiment definition. Observed model is the
identity reported or otherwise evidenced during the run. They can differ because aliases,
routing, fallbacks, or provider changes exist, so the Run contract stores them separately.

Phase D preserves both identities in direct-model evidence. A missing observed identity does not
invalidate an otherwise completed invocation; a mismatch remains explicit evidence for later
comparability analysis.

Phase E applies the same separation to Codex. If native JSONL does not expose the routed model,
`observed_model` remains null with `not_exposed` status; HarnessLab never copies the requested
identity into an observed field. Phase F consumes this evidence without guessing the missing value.

## H-Lane outcome authority

Codex, Claude, and DeepSeek public messages, native file-change events, and process exit status
describe trajectory, not task correctness. HarnessLab hashes the real workspace before and after
the harness, scans artifacts for
run credentials, and sends the final workspace to the isolated deterministic verifier. Thus an
agent message claiming success followed by `turn.completed` and exit zero can still produce
`VERIFIED_FAIL`. Harness failures remain separate from verifier failures.

## Repeated experiments and failure attribution

Single runs are samples, not stable rankings. Phase G labels one valid capability observation
per intended task `SMOKE`, at least three per task `INFORMAL`, and at least five per task `FORMAL`
when controls are valid. Observations from unrelated tasks are never pooled to upgrade this tier.
An n=1-per-task smoke cannot enter formal ranking, paired claims, or confidence-interval
conclusions. Formal paired evidence similarly requires five `COMPARABLE` pairs per intended task.

Infrastructure failures (service outage, sandbox startup, credential routing, worker, verifier,
or artifact failure) are classified separately from capability failures. The capability success
rate denominator is capability passes plus capability failures, never all planned slots. A
five-slot cell with one infrastructure failure reports planned=5, capability n=4, and infra=1
without a replacement run.

Harness configuration, authentication, timeout, process, protocol, profile-violation, and artifact
failures are infrastructure/control failures rather than subject capability failures. Only a
Harness model-turn failure enters the capability-failure denominator; cancellation remains its own
disclosed outcome.

Phase G reports Wilson 95% intervals for binary capability outcomes. The standard pass@k estimator
is calculated per task and macro-aggregated; n<k is `NOT_AVAILABLE`. Continuous latency, token,
tool, and step evidence includes count, p50, p95, and deterministic bootstrap intervals when
meaningful. Paired binary evidence uses the exact two-sided binomial test over McNemar
discordances; paired continuous evidence resamples exact task/repeat differences.

`NOT_COMPARABLE` pairs remain execution evidence but are excluded from formal uplift, causal, and
ranking claims. `PARTIALLY_COMPARABLE` pairs remain explicitly limited exploratory evidence. Cost
is `NOT_AVAILABLE`, not zero, unless immutable evidence provides a trustworthy explicit value.

## Judge calibration

A planned judge must be calibrated against deterministic and human-gold cases, checked for bias
and consistency, and prevented from overruling deterministic ground truth. Phase A provides only
the schema field and methodology boundary.
