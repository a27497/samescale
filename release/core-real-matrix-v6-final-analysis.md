# Formal Matrix Final Statistical Analysis

This is a deterministic statistical readout of the frozen 630-row analysis dataset. It does not rerun, recover, or rejudge experiment evidence.

## Dataset integrity

- Validation: **PASS**
- Dataset SHA256: `sha256:d07f6c96e3bd7882137355cb8b5d2d5682e3d51bffcedce6292375d4a54bbd1d`
- Grain: 630 unique logical slots; 18 tasks × 5 repeats × 7 cells; 90 rows/cell.
- Frozen `effective_outcome=infra_failure` is reported as `infra_missing`; it is never counted as capability failure.
- Capability pass rate conditions on capability-evaluable results. Operational pass rate retains all 90 logical slots per cell.
- Primary, recovery, effective-outcome, and exact native-currency cost totals reconcile to the manifest.

## Cell-level results

| Cell | Pass | Fail | Evaluable | Infra | Cancelled | Capability pass rate (95% Wilson CI) | Operational pass rate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Direct GPT-5.6 Sol | 83 | 3 | 86 | 4 | 0 | 96.5% [90.2%, 98.8%] | 92.2% |
| Direct Qwen3.8-Max | 68 | 4 | 72 | 18 | 0 | 94.4% [86.6%, 97.8%] | 75.6% |
| Direct DeepSeek V4 Pro | 40 | 50 | 90 | 0 | 0 | 44.4% [34.6%, 54.7%] | 44.4% |
| Direct DeepSeek V4 Flash | 31 | 59 | 90 | 0 | 0 | 34.4% [25.4%, 44.7%] | 34.4% |
| Codex + GPT-5.6 medium | 65 | 21 | 86 | 3 | 1 | 75.6% [65.5%, 83.4%] | 72.2% |
| Codex + GPT-5.6 high | 47 | 38 | 85 | 4 | 1 | 55.3% [44.7%, 65.4%] | 52.2% |
| Claude Code + Qwen3.8-Max | 69 | 21 | 90 | 0 | 0 | 76.7% [66.9%, 84.2%] | 76.7% |

## GPT Harness Effect

Baseline: `model-gpt56-relay-responses`  
Variant: `harness-codex-gpt56-medium`

**CAPABILITY EFFECT** (both members capability-evaluable; equal task weighting):

- Complete pairs: 82/90 (91.1%); tasks with pairs: 18/18.
- Baseline/variant pass rates on complete pairs: 96.3% / 76.8%.
- Paired capability delta: -19.4%; 95% task-cluster bootstrap CI [-25.7%, -12.9%].
- Discordant pairs (fail→pass / pass→fail): 1 / 17; both pass/fail: 62 / 2; exact McNemar p=0.000144958 (secondary evidence).

**OPERATIONAL EFFECT** (all 90 pairs; infra/cancelled are non-pass):

- Baseline/variant operational pass rates: 92.2% / 72.2%.
- Paired operational delta: -20.0%; 95% task-cluster bootstrap CI [-28.9%, -11.1%].

Missingness: baseline/variant final infra rates 4.4% / 3.3%; exclusion flags baseline infra=4, variant infra=3, cancelled=1 (overlapping counts).
Task heterogeneity: 0 favor variant, 13 favor baseline, 5 tied, 0 without capability-complete pairs.
Paired primary latency: n=77/90; median variant−baseline=93,649 ms.

## Reasoning Effort Effect

Baseline: `harness-codex-gpt56-medium`  
Variant: `harness-codex-gpt56-high`

**CAPABILITY EFFECT** (both members capability-evaluable; equal task weighting):

- Complete pairs: 83/90 (92.2%); tasks with pairs: 18/18.
- Baseline/variant pass rates on complete pairs: 74.7% / 55.4%.
- Paired capability delta: -20.6%; 95% task-cluster bootstrap CI [-33.9%, -7.2%].
- Discordant pairs (fail→pass / pass→fail): 9 / 25; both pass/fail: 37 / 12; exact McNemar p=0.00904119 (secondary evidence).

**OPERATIONAL EFFECT** (all 90 pairs; infra/cancelled are non-pass):

- Baseline/variant operational pass rates: 72.2% / 52.2%.
- Paired operational delta: -20.0%; 95% task-cluster bootstrap CI [-32.2%, -7.8%].

Missingness: baseline/variant final infra rates 3.3% / 4.4%; exclusion flags baseline infra=3, variant infra=4, cancelled=1 (overlapping counts).
Task heterogeneity: 4 favor variant, 12 favor baseline, 2 tied, 0 without capability-complete pairs.
Paired primary latency: n=90/90; median variant−baseline=3,876 ms.

## Qwen Harness Effect

Baseline: `model-qwen38-alibaba-bailian-chat`  
Variant: `harness-claude-qwen38-alibaba-bailian`

**CAPABILITY EFFECT** (both members capability-evaluable; equal task weighting):

- Complete pairs: 72/90 (80.0%); tasks with pairs: 16/18.
- Baseline/variant pass rates on complete pairs: 94.4% / 88.9%.
- Paired capability delta: -11.9%; 95% task-cluster bootstrap CI [-30.6%, 4.1%].
- Discordant pairs (fail→pass / pass→fail): 4 / 8; both pass/fail: 60 / 0; exact McNemar p=0.387695 (secondary evidence).

**OPERATIONAL EFFECT** (all 90 pairs; infra/cancelled are non-pass):

- Baseline/variant operational pass rates: 75.6% / 76.7%.
- Paired operational delta: 1.1%; 95% task-cluster bootstrap CI [-11.1%, 11.1%].

Missingness: baseline/variant final infra rates 20.0% / 0.0%; exclusion flags baseline infra=18, variant infra=0, cancelled=0 (overlapping counts).
Task heterogeneity: 3 favor variant, 5 favor baseline, 8 tied, 2 without capability-complete pairs.
Paired primary latency: n=67/90; median variant−baseline=28,510 ms.
- **Infrastructure reliability changes the practical conclusion** under the prespecified materiality rule.

## Direct route/model comparison

> Direct-model comparisons are model/provider-route comparisons. Model identity and provider/route are confounded, so they must not be presented as clean causal model effects.

| Route/model combination | Capability pass rate | 95% Wilson CI | Operational pass rate | Final infra rate |
| --- | --- | --- | --- | --- |
| Direct GPT-5.6 Sol | 96.5% | [90.2%, 98.8%] | 92.2% | 4.4% |
| Direct Qwen3.8-Max | 94.4% | [86.6%, 97.8%] | 75.6% | 20.0% |
| Direct DeepSeek V4 Pro | 44.4% | [34.6%, 54.7%] | 44.4% | 0.0% |
| Direct DeepSeek V4 Flash | 34.4% | [25.4%, 44.7%] | 34.4% | 0.0% |

## Repeat stability

| Cell | Tasks ≥2 evaluable | Mixed tasks | Mixed-task rate | Mean within-task sample variance | Median task pass fraction |
| --- | --- | --- | --- | --- | --- |
| Direct GPT-5.6 Sol | 18 | 1 | 5.6% | 0.017 | 100.0% |
| Direct Qwen3.8-Max | 15 | 3 | 20.0% | 0.047 | 100.0% |
| Direct DeepSeek V4 Pro | 18 | 7 | 38.9% | 0.100 | 40.0% |
| Direct DeepSeek V4 Flash | 18 | 7 | 38.9% | 0.106 | 30.0% |
| Codex + GPT-5.6 medium | 18 | 16 | 88.9% | 0.213 | 80.0% |
| Codex + GPT-5.6 high | 18 | 11 | 61.1% | 0.160 | 50.0% |
| Claude Code + Qwen3.8-Max | 18 | 6 | 33.3% | 0.072 | 100.0% |

Only capability-evaluable repeats enter these stability metrics. Individual task results have at most five repeats and should not be overinterpreted.

## Infrastructure and recovery

| Cell | Primary infra | Primary infra rate | Recovery attempted | Recovered evaluable | Recovery resolution rate | Final infra |
| --- | --- | --- | --- | --- | --- | --- |
| Direct GPT-5.6 Sol | 14 | 15.6% | 14 | 10 | 71.4% | 4 |
| Direct Qwen3.8-Max | 23 | 25.6% | 23 | 5 | 21.7% | 18 |
| Direct DeepSeek V4 Pro | 1 | 1.1% | 1 | 1 | 100.0% | 0 |
| Direct DeepSeek V4 Flash | 1 | 1.1% | 1 | 1 | 100.0% | 0 |
| Codex + GPT-5.6 medium | 19 | 21.1% | 19 | 16 | 84.2% | 3 |
| Codex + GPT-5.6 high | 19 | 21.1% | 19 | 15 | 78.9% | 4 |
| Claude Code + Qwen3.8-Max | 2 | 2.2% | 2 | 2 | 100.0% | 0 |

A recovered `capability_fail` is an infrastructure resolution because it produced evaluable capability evidence; it is not a capability success.

## Latency

| Cell | Primary n | Median ms | P25 ms | P75 ms | P90 ms | Mean ms | Recovery n | Recovery median ms | Recovery P90 ms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Direct GPT-5.6 Sol | 77 | 14,971 | 10,438 | 27,580 | 51,956 | 23,421 | 10 | 7,132 | 51,258 |
| Direct Qwen3.8-Max | 67 | 44,698 | 18,972 | 74,404 | 115,759 | 52,019 | 5 | 149,843 | 167,568 |
| Direct DeepSeek V4 Pro | 90 | 29,973 | 13,454 | 38,697 | 42,936 | 27,082 | 1 | 39,807 | 39,807 |
| Direct DeepSeek V4 Flash | 90 | 17,590 | 12,853 | 19,546 | 20,598 | 14,949 | 1 | 18,850 | 18,850 |
| Codex + GPT-5.6 medium | 90 | 108,294 | 64,825 | 174,242 | 180,697 | 111,042 | 19 | 69,714 | 127,016 |
| Codex + GPT-5.6 high | 90 | 121,862 | 78,187 | 180,643 | 180,741 | 120,854 | 19 | 121,088 | 180,657 |
| Claude Code + Qwen3.8-Max | 90 | 86,911 | 56,779 | 156,240 | 181,260 | 102,229 | 2 | 130,576 | 171,235 |

Missing latency is not zero-filled. Recovery latency is separate; no total effective latency is fabricated.

## Usage

### Primary usage

| Cell | Observed n | Median input | Median output | Mean input | Mean output | Total input | Total output |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Direct GPT-5.6 Sol | 77 | 340 | 396 | 348.2 | 599.5 | 26,813 | 46,164 |
| Direct Qwen3.8-Max | 67 | 377 | 1,679 | 382.1 | 1,954.7 | 25,600 | 130,964 |
| Direct DeepSeek V4 Pro | 90 | 436 | 2,000 | 435.8 | 1,462.1 | 39,225 | 131,589 |
| Direct DeepSeek V4 Flash | 90 | 436 | 2,000 | 435.8 | 1,597.9 | 39,225 | 143,807 |
| Codex + GPT-5.6 medium | 54 | 98,220 | 1,744 | 104,503.4 | 2,088.5 | 5,643,186 | 112,777 |
| Codex + GPT-5.6 high | 44 | 96,988 | 2,230 | 107,624.1 | 2,710.6 | 4,735,462 | 119,267 |
| Claude Code + Qwen3.8-Max | 71 | 174 | 2,742 | 189.9 | 3,091.5 | 13,485 | 219,494 |

### Recovery usage

| Cell | Observed n | Median input | Median output | Total input | Total output |
| --- | --- | --- | --- | --- | --- |
| Direct GPT-5.6 Sol | 10 | 304 | 192 | 3,142 | 3,152 |
| Direct Qwen3.8-Max | 5 | 377 | 5,908 | 1,925 | 29,157 |
| Direct DeepSeek V4 Pro | 1 | 424 | 2,000 | 424 | 2,000 |
| Direct DeepSeek V4 Flash | 1 | 424 | 2,000 | 424 | 2,000 |
| Codex + GPT-5.6 medium | 15 | 96,221 | 1,428 | 1,454,554 | 23,983 |
| Codex + GPT-5.6 high | 9 | 94,786 | 1,671 | 884,741 | 17,056 |
| Claude Code + Qwen3.8-Max | 1 | 232 | 3,174 | 232 | 3,174 |

Missing usage is not added as zero. Cached-token semantics may differ between Harness and Direct routes; comparisons of cached, cache-write, and reasoning tokens are descriptive.

## Cost and efficiency

All figures use **HarnessLab conservative estimated accounting**, not invoice or billing truth. No USD↔CNY conversion is performed.

| Cell | Currency | Total | Mean/slot | Mean/evaluable | Cost/capability pass | Cost/operational pass |
| --- | --- | --- | --- | --- | --- | --- |
| Direct GPT-5.6 Sol | USD | 1.897755300 | 0.021086170 | 0.022066922 | 0.022864522 | 0.022864522 |
| Direct Qwen3.8-Max | CNY | 41.794656000 | 0.464385067 | 0.580481333 | 0.614627294 | 0.614627294 |
| Direct DeepSeek V4 Pro | USD | 0.581349120 | 0.006459435 | 0.006459435 | 0.014533728 | 0.014533728 |
| Direct DeepSeek V4 Flash | USD | 0.209910800 | 0.002332342 | 0.002332342 | 0.006771316 | 0.006771316 |
| Codex + GPT-5.6 medium | USD | 6.575490000 | 0.073061000 | 0.076459186 | 0.101161385 | 0.101161385 |
| Codex + GPT-5.6 high | USD | 7.631442300 | 0.084793803 | 0.089781674 | 0.162371113 | 0.162371113 |
| Claude Code + Qwen3.8-Max | CNY | 52.513104000 | 0.583478933 | 0.583478933 | 0.761059478 | 0.761059478 |

Manifest-reconciled totals: USD 16.895947520; CNY 94.307760000.

Paired cost deltas per logical slot:

| Comparison | Currency | Baseline mean/slot | Variant mean/slot | Delta/slot | Multiplier | Operational pass-rate delta |
| --- | --- | --- | --- | --- | --- | --- |
| GPT Harness Effect | USD | 0.021086170 | 0.073061000 | 0.051974830 | 3.465× | -20.0% |
| Reasoning Effort Effect | USD | 0.073061000 | 0.084793803 | 0.011732803 | 1.161× | -20.0% |
| Qwen Harness Effect | CNY | 0.464385067 | 0.583478933 | 0.119093867 | 1.256× | 1.1% |

## Cancelled rows

The two frozen cancellations are excluded from capability estimands and retained as non-passes in operational estimands. They were not rerun.

| Cell | Task | Repeat | Slot ID |
| --- | --- | --- | --- |
| harness-codex-gpt56-high | core-java-feature-flag | 0 | `sha256:703591dddf316db4eb546818e05682a66cd1587293e43170a068f9a86825e8dd` |
| harness-codex-gpt56-medium | core-java-feature-flag | 0 | `sha256:da86e48c1a599999bbbb68f5c8ccca1ce19474dcf4d20502b377311bca8232f3` |

## Limitations

- Capability comparisons condition on both paired rows being evaluable and can therefore differ from operational comparisons that retain infrastructure failures and cancellations.
- Task-cluster bootstrap intervals resample the 18 task clusters with replacement and use equal task weighting; they do not treat 90 rows as independent IID observations.
- Exact McNemar p-values are secondary evidence and are not the sole significance criterion.
- Direct-route comparisons confound model identity with provider/route and are descriptive, not clean causal model effects.
- Each task has five repeats at most; task-level heterogeneity is descriptive and individual tasks should not be overinterpreted.
- Primary and recovery latency/usage coverage is incomplete in some cells; missing values are not zero-filled.
- Harness and Direct cached-token semantics may differ. Frozen conservative cost estimates are not billing truth.

## Mechanical conclusions

- GPT Harness Effect: observed capability delta -19.4% (95% task-cluster bootstrap CI [-25.7%, -12.9%]); operational delta -20.0% (95% task-cluster bootstrap CI [-28.9%, -11.1%]).
- Reasoning Effort Effect: observed capability delta -20.6% (95% task-cluster bootstrap CI [-33.9%, -7.2%]); operational delta -20.0% (95% task-cluster bootstrap CI [-32.2%, -7.8%]).
- Qwen Harness Effect: observed capability delta -11.9% (95% task-cluster bootstrap CI [-30.6%, 4.1%]); operational delta 1.1% (95% task-cluster bootstrap CI [-11.1%, 11.1%]).
