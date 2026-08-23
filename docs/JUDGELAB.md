# JudgeLab

JudgeLab is HarnessLab's calibrated L2 evaluation layer. It labels behavior, scores subjective
quality, and compares answers while preserving this authority:

`L0 deterministic ground truth > L1 repository-curated human gold > L2 LLM Judge`.

L2 may annotate evidence. It cannot change deterministic pass/fail, Hidden Verifier facts, Phase G
normalized/source outcomes, or capability denominators. `resolve_authority` encodes that priority
and constructs L0 override count as zero.

## Inputs and leakage boundary

`JudgeDefinition` freezes its public scaffold, modes, output schema, justification bound,
abstention, blinding, order-swap, and private-reasoning policies. Canonical JSON produces its
semantic digest. It contains no credential, gold, oracle, or Hidden Verifier content.

A suite has public `suite.yaml` and hidden `gold.yaml`. Their case-id sets match exactly but receive
separate digests; the overall suite identity binds both. Prompt construction accepts only a
`PublicCase`, never a full suite. Gold values, curator notes, deterministic expected outcomes,
oracle/verifier sentinels, and controlled source identity metadata cannot enter a provider request
or JudgeEvidence. Public candidates contain natural evaluation content rather than answer labels,
numeric answer keys, or probe markers. Mutating hidden gold while keeping public cases fixed cannot
change Judge request instructions or input bytes.

Candidate prose is untrusted data. The scaffold says so explicitly and candidates remain
delimited in user input. Adversarial text such as “ignore the rubric” is preserved as evidence,
not promoted to instruction. HarnessLab blinds metadata it controls; candidate text may still
self-identify, so Phase H makes no general self-preference-bias claim.

## Outputs and provider reuse

LABEL returns exactly `schema_version`, allowed `label`, and short public `reason`. SCORE returns
exactly `schema_version`, bounded `score` or null, `abstain`, and `reason`. PAIRWISE returns exactly
`schema_version`, LEFT/RIGHT/TIE/UNKNOWN `preference`, and `reason`. Parsing requires a bare UTF-8
JSON object, rejects duplicate keys and extra fields, enforces a byte bound, and rejects
`reasoning`, `analysis`, `scratchpad`, `thinking`, and `hidden_rationale`. Public `reason` is a
short justification, not chain of thought.

JudgeRunner reuses Phase D `ProviderAdapter`, `ProviderRequest`, `ProviderResult`, and
`ProviderFailureCategory`. One slot means one attempt; there is no automatic retry. Refusal is
`ABSTAINED`, malformed judgment is `JUDGE_OUTPUT_ERROR`, and transport failure is
`PROVIDER_ERROR`. The Judge call does not invoke DirectModelRunner, Direct Patch, a subject run, or
Hidden Verifier.

## Evidence, repetition, and bias probes

JudgeEvidence binds evaluation/calibration/cell/case/suite/definition/profile identities,
requested/observed Judge model, route/protocol, prompt hash, order, repeat, request/usage/latency,
response digest, parsed public judgment, outcome, and artifact identity. It excludes credentials,
raw HTTP, ambient auth, private reasoning, gold, curator notes, oracle, and verifier content.

The Core plan uses three explicit repeats. Each PAIRWISE repeat expands original A/B and swapped
B/A because the resolved `JudgeDefinition.order_swap_policy` requires it; a Judge cell cannot
override that policy. Planning rejects unsupported case modes before enqueue. The Judge sees
neutral Candidate A/B display labels and LEFT/RIGHT positions; parsing
canonicalizes back to stable A/B identity. The two requests are one gold trial. Disagreement is
position inconsistency and cannot be hidden by choosing the gold-matching order.

L1 TIE probes deliberately make one candidate longer without more substance. The report counts
longer-candidate preferences and exposes a verbosity-bias rate only over those probes. This does
not establish general-purpose bias presence or absence.

## Metrics and qualification

LABEL reports planned/valid/abstain/output/provider counts, accuracy, confusion matrix, directly
implemented macro F1, and repeat agreement. SCORE aggregates by median and reports coverage, MAE,
Spearman rho, and within-case dispersion. Undefined Spearman is null with a reason. PAIRWISE
reports planned/evaluable logical pairs, provider-infrastructure trials, coverage, gold/tie
accuracy, position-evaluable count and consistency, abstain/output-error rates, repeat agreement,
and verbosity results. Provider infrastructure reduces coverage and is excluded from Judge
accuracy, F1, repeat, position, and capability-error denominators. Abstention and output errors
remain Judge capability failures and cannot be diluted by provider failures.

The versioned policy binds coverage, label accuracy/F1, score MAE/Spearman, pairwise accuracy,
position/repeat consistency, abstain/error, and verbosity thresholds. The versioned Core rule is
`ALL_REQUIRED_CHECKS_PASS`: all checks pass for `QUALIFIED_FOR_SUITE`; any failed check yields
`NOT_QUALIFIED`. `LIMITED` remains reserved for a future explicitly versioned policy and is not
assigned in Phase H. The included gold calibrates machinery; it is not a large human study,
expert panel, inter-rater study, external validation, or universal reliability claim.

## Persistence, CLI, and smoke

Alembic `20260823_0004` adds `judge_calibration` and `judge_evaluation`. Logical slots are unique by
calibration/cell/case/repeat/order. Rows store plan/lifecycle, safe model identities, and artifact
references. The database artifact digest hashes the exact canonical JSON-plus-newline bytes written
to disk, independently of the embedded semantic evidence-content digest. Reports hash actual file
bytes before parsing, then verify semantic content and slot/suite/case/definition/profile identity;
whitespace, key-order, or content changes fail closed.

```text
harnesslab judge suite validate <suite>
harnesslab judge plan <calibration-spec>
harnesslab judge calibrate <calibration-spec>
harnesslab judge report <calibration-id>
```

Gate H uses deterministic Good and Biased/Unstable fake ProviderAdapters over the same 15-case
suite and 126 slots. Both traverse production prompt, runner, parser, artifact, PostgreSQL, reload,
metrics, qualification, and report code with no network. FakeJudge is explicitly a fixture adapter:
its deterministic behavior uses public fixture identity/configuration and never reads hidden gold.

`REAL_JUDGE_SMOKE=NOT_RUN` by default. A real call requires
`HARNESSLAB_ENABLE_REAL_JUDGE=1`, an explicit ModelProfile, and credential reference. Ambient
Codex/Claude/DSH login and unrelated keys are never used. Existing real Matrix/provider/harness
smoke statuses remain separate.
