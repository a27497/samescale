# Evaluation Methodology v2

Evaluation Methodology v2 is the active policy for new HarnessLab experiments. Its canonical,
strict artifact is `release/evaluation-methodology-v2.json`; the artifact digest is computed from
canonical JSON and is persisted in every schema-v2 experiment plan. Historical schema-v1 plans,
including `core-real-matrix-v3`, keep their original bytes, digest, logical slots, evidence, and
resume behavior.

## Scope and evidence boundary

The current 18 tasks are `TIER_A_MICRO_CONTRACT`: cheap, deterministic micro-contract tasks. They
are useful for fast controlled evaluation but are not a universal coding-agent benchmark. Future
task packages can be separately versioned as `TIER_B_REPO_ENGINEERING` or
`TIER_C_LONG_HORIZON_AGENTIC`; adding a tier does not reinterpret existing task evidence.

Task identity remains content-addressed. A task change that alters semantics requires a new task
version. Methodology v2 does not rewrite any task, frozen plan, persisted run, or evidence file.

## Evaluation modes

| Mode | Repeats | Intended use |
|---|---:|---|
| `QUICK` | 1 | Breadth-first representative comparison at minimum cost |
| `INFORMAL` | 3 | Selected important pairs and ablations for portfolio reporting |
| `FORMAL_EXHAUSTIVE` | 5 | Expensive preregistered research-grade execution |

The mode is explicit in every schema-v2 plan. Its repeat count is enforced during planning; n=5
is not mechanically required for unrelated comparisons. Repetition tiering remains per task:
unrelated tasks are never pooled to manufacture a higher evidence tier.

The primary portfolio metric is `PASS_AT_1`. Repeated trials additionally report
`TRIAL_SUCCESS_RATE`. Wilson intervals remain available for capability proportions, exact paired
binary methods remain McNemar-compatible, and paired continuous analysis continues to operate on
exact task/repeat differences with deterministic bootstrap summaries. Three or five trials do not
imply a precise per-task population estimate.

## Comparison types

Methodology v2 freezes four claim classes:

- `END_TO_END_SYSTEM_COMPARISON` permits model, harness, and provider differences but supports
  system-level claims only. It never supports a pure harness-uplift claim.
- `MODEL_COMPARISON` declares model identity as the treatment while holding harness/scaffold,
  task, provider, budget, and network controls fixed.
- `HARNESS_UPLIFT` declares harness/profile as the treatment while holding model, provider route,
  task/context/verifier, budget, and network controls fixed.
- `CONTROLLED_ABLATION` permits exactly one named treatment dimension to change.

GPT direct versus Codex GPT medium and Qwen direct versus Claude Code with the same Qwen/provider
are intended harness comparisons only when their persisted controls actually satisfy the harness
uplift contract. Codex medium versus Codex high is a `reasoning_effort` controlled ablation.
DeepSeek V4 Pro direct versus DeepSeek Harness with V4 Flash is an end-to-end system comparison,
not pure harness uplift, because model identity differs.

Provider identity and model identity are separate controls. Replacing an unavailable provider is
never allowed under the same experiment identity; a changed provider route or profile changes
slot/plan identity and is rejected as substitution when recovering an existing treatment.

Verifier control and verifier execution are distinct evidence. The verifier control identity is
frozen by the task/experiment plan before subject execution and is the hard control used for model
and harness comparisons. The verifier execution identity proves that the verifier actually ran;
it may be `NOT_EXECUTED` for an early capability terminal such as subject-output error, refusal, or
execution-budget exhaustion. Missing execution does not invent correctness and does not remove a
controlled failure from paired capability analysis. When execution exists, disagreement with the
frozen verifier definition or between executed verifier runtime identities is a blocking integrity
failure. Historical evidence without a frozen verifier control remains conservative.

## Keyless task health gate

Before a schema-v2 paid experiment can be planned, every selected task undergoes five baseline
verifier runs and five oracle runs:

- the untouched baseline must fail;
- the oracle overlay must pass;
- normalized terminal facts must be identical across all five repetitions; and
- task, workspace, verifier, and oracle identities must remain stable.

Duration is not a deterministic terminal fact, but pass state, score, checks, summary, category,
exit behavior, output identities, and workspace/verifier identities are. Instability fails closed
as a task-health error. These checks use local deterministic verifiers and make no model call.

## Cost-aware funnel

The default funnel is:

1. `PREFLIGHT`: validate identities, task health, routes, budgets, and schedule without execution.
2. `SMOKE`: n=1 over a small representative subset.
3. `BREADTH`: n=1 over every selected task.
4. `INFORMAL`: n=3 over selected critical pairs or ablations.
5. `FORMAL`: n=5 only for preregistered important comparisons or explicit exhaustive mode.
6. `DISCRIMINATIVE_STRESS`: optional, separately versioned future extension.

Every stage ends in an explicit `GO` or `STOP`. There is no automatic promotion.

## Default portfolio projection

The recommended planning-only portfolio uses all seven current system cells across the 18 Tier-A
tasks at n=1, producing 126 breadth slots. It then uses the existing nine representative tasks at
n=3 for three critical questions:

1. GPT direct versus Codex medium;
2. Qwen direct versus Claude Code + Qwen; and
3. Codex medium versus Codex high.

Those comparisons contain 162 pair memberships but only 135 unique logical subject slots because
Codex medium participates in two comparisons. Forty-five repeat-0 slots are already part of the
breadth stage. The critical stage therefore adds 90 unique slots, for 216 projected subject runs
in total.

Compared with the 630-slot exhaustive design, the default portfolio removes 414 subject runs, a
65.7% reduction. Reuse is identity-based; no capability result is selected or rerun to improve a
score.

## Blocked interleaved scheduling

`BLOCKED_INTERLEAVED_SCHEDULING` replaces provider-lane-first execution for new schema-v2 plans.
The block key is `(task_id, repeat_index)`. Blocks are ordered breadth-first by repeat and task; all
eligible cells inside a block use a deterministic permutation derived from `schedule_seed` and the
block identity. Plans persist:

- `schedule_seed`;
- the digest-bound block identity;
- the cell execution order; and
- the ordered logical slot IDs.

Changing the seed changes order but not logical slot identity. A worker therefore encounters a
cross-cell block before moving to another task/repeat instead of exhausting one provider lane.

Provider availability is checked before a block is eligible for acquisition. If any required
provider is unavailable, the block is `PROVIDER_UNAVAILABLE`, yields no executable slot IDs, and
pauses as a block. The policy neither substitutes another provider nor silently executes the
remaining treatments and creates time/quota confounding.

## Budget contract

Schema-v2 plans persist one canonical budget contract with these dimensions:

- `max_wall_time`;
- `max_output_tokens`;
- `max_model_turns`;
- `max_tool_calls`;
- `max_provider_requests`; and
- `max_cost`.

Each dimension is `ENFORCED`, `OBSERVED_ONLY`, or `NOT_AVAILABLE`. An unavailable dimension has no
invented numeric value. Formal pairs and ablations require the same complete budget-contract
identity. A wall-clock timeout alone is not a complete fairness claim.

## Capability, cost, and operational denominators

Reports may present capability success, pass@1, trial success rate, latency, tokens, model turns,
tool calls, provider requests, explicit cost, and cost per successful task when the corresponding
evidence is trustworthy. Missing observations are `NOT_AVAILABLE`, never zero.

Cost claims require immutable input/usage and pricing evidence. A pricing snapshot is planning
metadata and cannot retroactively price historical evidence.

The capability denominator remains:

```text
capability_n = capability_pass + capability_fail
```

Infrastructure outcomes stay excluded, but every report must show `planned`, `capability_n`,
`infra_count`, `missing_count`, and `recovery_attempt_count`. This keeps operational reliability
visible beside capability.

Provider-declared output-budget exhaustion is capability evidence. For OpenAI Responses this
requires the persisted bounded reason `max_output_tokens`; absent or unknown incomplete reasons
remain infrastructure and are never guessed retroactively. A Harness wall-clock timeout is also
capability evidence only when bounded safe trace evidence proves model startup, tool execution,
completed healthy progress, no retry or structured provider failure, and expiry without a terminal
event. Otherwise it remains an infrastructure timeout. These v2.1 interpretations do not rewrite
the original manifest or its source taxonomy.

## Infrastructure recovery

Capability-terminal slots are immutable and never retry-eligible. This includes verified failure,
subject-output error, execution-budget exhaustion, and every other typed capability outcome.

An infrastructure failure may authorize at most one recovery attempt. Authorization binds the
original logical slot and immutable original-attempt identity into a new recovery-attempt identity;
it never overwrites the original evidence. Recovery cannot be triggered by a poor score and has no
semantic retry or fallback. A second infrastructure failure becomes
`INFRA_RECOVERY_EXHAUSTED`.

## Judge funnel

Judge calibration starts with `JUDGE_PILOT`, a frozen 21-slot subset. `JUDGE_FORMAL` remains the
63-slot calibration and requires an explicit decision after the pilot proves route operation,
usable strict schema conformance, sufficient coverage, and absence of a deterministic
infrastructure blocker. Outputs cannot be used to relax the Judge schema. Judge capability
failures remain valid calibration evidence.

## Historical compatibility

`core-real-matrix-v3` remains a valid `FORMAL_EXHAUSTIVE_MODE` historical/research-grade design:
7 cells × 18 tasks × 5 repeats = 630 logical slots, with plan digest
`sha256:5b91aea8c2cf812e911358b3a39f75d8d0eada153188c219eaf5176d3b3b107d`.

Methodology v2 does not migrate, shrink, rewrite, or reinterpret that experiment. Schema-v1 plans
remain readable and resumable through the same queue/report/Workbench readers; new experiments
may use schema-v2 plans with explicit methodology identity.
