# Evaluation methodology

Phase A establishes vocabulary and contracts only. None of the lanes, verifiers, execution engine,
or judges described below should be read as implemented.

## Evaluation lanes

- **M-Lane (Model-only Evaluation):** evaluate model capability through direct model execution,
  without a coding harness, while holding task conditions stable.
- **H-Lane (Harness):** compare harness behavior while holding requested model and task stable.
- **P-Lane (Paired Model-vs-Harness Evaluation):** compare direct-model execution with harness
  execution on controlled micro tasks where the necessary context and verifier are equivalent, in
  order to measure harness uplift.
- **J-Lane (JudgeLab):** calibrate and compare judging methods against stronger references.

## Evidence hierarchy

**Deterministic Ground Truth > Human Gold > LLM Judge.** Hidden tests, builds, lint, schemas,
explicit rules, and protected-file checks must not be overridden by an LLM's preference. Human
gold labels cover questions deterministic checks cannot settle. LLM judges are calibrated aids,
not an authority over reproducible facts.

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

## Repeated experiments and failure attribution

Single runs are samples, not stable rankings. Planned evaluation will repeat comparable cells and
report uncertainty. Infrastructure failures (service outage, sandbox startup, credential routing)
must be classified separately from model failures; otherwise platform reliability contaminates
model attribution.

## Judge calibration

A planned judge must be calibrated against deterministic and human-gold cases, checked for bias
and consistency, and prevented from overruling deterministic ground truth. Phase A provides only
the schema field and methodology boundary.
