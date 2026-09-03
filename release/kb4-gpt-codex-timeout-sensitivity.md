# K-B4.1 GPT/Codex timeout sensitivity

**READY_FOR_DISCORDANT_PAIR_ATTRIBUTION**

Persisted V6 evidence supports bounded later attribution; no new controlled execution is required before that review. The next phase is not started or authorized here.

## Frozen controls

All three cells freeze `gpt-5.6-sol` on the GPT relay Responses route. Direct/medium use medium effort; high uses high effort. The provider request timeout is 180 seconds; all 104 available Direct manifests confirm it. All 217 Codex manifests record a 180-second outer process execution limit. These are different timeout scopes. Task budget: 90 seconds; verifier: 15 seconds. The source-defined V6 plan contract declares 300 seconds per logical run and 2,000 output tokens per provider request, with turns/tools/requests/cost unavailable. These numbers are not evidence of one interchangeable execution deadline or of a Codex-wide token ceiling.

Manifest facts preserve requested/observed model, route, profile, controls, and primary/recovery identity. Comparison supplementation follows `experiment/report.py`; registry bindings must match the persisted V6 execution-binding digest. No plan or task-health execution is performed.

## Primary, recovery, and effective evidence

| Cell | Primary infra timeouts | Primary budget capability failures | Recovery infra timeouts | Recovery budget capability failures | All recoveries | Effective pass/fail | Infra/cancelled |
|---|---:|---:|---:|---:|---:|---:|---:|
| `model-gpt56-relay-responses` | 0 | 0 | 0 | 0 | 14 | 83/3 | 4/0 |
| `harness-codex-gpt56-medium` | 4 | 17 | 0 | 1 | 19 | 65/21 | 3/1 |
| `harness-codex-gpt56-high` | 1 | 27 | 0 | 6 | 19 | 47/38 | 4/1 |

Capability denominators stay 86 / 86 / 85; campaign-wide 599. Each cell has 90 planned slots. Infrastructure is excluded from capability; cancellations stay separate. Primary evidence is immutable. Zero Direct timeouts means zero observed in selected manifests, not a proven zero across the unobserved extra physical attempt. Across GPT/Codex, four extra physical primaries (1/2/1 by cell) plus one rejected high primary lack authoritative manifests: 269 of 274 recorded physical primaries are observable. Their unknown timeout facts are preserved, not imputed.

## Timeout-affected slots

| Cell | Task | Repeat (zero based) | Language/category | Recovery | Still missing capability |
|---|---|---:|---|---|---|
| `harness-codex-gpt56-medium` | `core-python-quota` | 0 | python / cache-collection-behavior | `verified_pass` | False |
| `harness-codex-gpt56-medium` | `core-python-settings-merge` | 0 | python / resource-lifecycle | `verified_pass` | False |
| `harness-codex-gpt56-high` | `micro-python-clamp` | 2 | python / targeted-bug-fix | `harness_error:protocol_error` | True |
| `harness-codex-gpt56-medium` | `core-java-deduplicate` | 4 | java / serialization-codec | `harness_error:protocol_error` | True |
| `harness-codex-gpt56-medium` | `micro-python-clamp` | 4 | python / targeted-bug-fix | `verified_pass` | False |

All five entered the authorized single recovery path. Three medium slots passed; one medium and one high slot exhausted recovery with protocol errors. There are zero recovery infrastructure timeouts. Two slots are historically timeout-affected and unresolved; their final category is protocol error. This is association, not causal attribution. Other final infrastructure gaps are Direct malformed responses (4), medium protocol errors (2), and high protocol errors (3).

## Matched evidence and formal eligibility

| Comparison | Primary complete | Effective complete | Timeout-affected unavailable | Other unavailable | Tasks with 5 effective complete pairs | Effective comparable/partial/not comparable | Formal eligible |
|---|---:|---:|---:|---:|---:|---|---|
| `model-gpt56-relay-responses` → `harness-codex-gpt56-medium` | 61/90 | 82/90 | 1 | 7 | 11/18 | 0/82/0 | False |
| `harness-codex-gpt56-medium` → `harness-codex-gpt56-high` | 60/90 | 83/90 | 2 | 5 | 13/18 | 42/0/41 | False |

GPT direct/medium is PARTIALLY_COMPARABLE because Codex does not expose observed model, Direct trace coverage is limited, and provider configuration evidence differs. Medium/high has 42 COMPARABLE complete pairs and 41 NOT_COMPARABLE complete pairs: the unchanged ablation engine blocks missing verifier execution identity (41), with asymmetric verifier execution/control status in 32. Both unexposed observed models remain informational under the operator-trusted ablation contract. No task has five formal eligible pairs. These existing control restrictions are separate from the two timeout-affected missing slots.

Exact task/repeat and paired-slot identities drive all joins. Missing pairs remain visible; per-task coverage and every ComparabilityEngine reason are in JSON. Coverage and eligibility are distinct: recovery never upgrades controls. The prior 82/90 and 83/90 complete-pair readouts remain reproducible as observed end-to-end configuration performance. Their effect labels and existing intervals do not prove controlled Harness uplift or reasoning causation. No new significance tests or counterfactual scores are computed.

Timeout censoring removes a small, explicit subset of usable matches. It limits exhaustive five-repeat coverage and requires excluding those identities from later capability-pair review, but does not block bounded descriptive review of the remaining observations. Other missingness and comparability limits also remain; random missingness and population-wide representativeness are not established.

## Duration at the actual boundary

- `harness-codex-gpt56-medium` primary infrastructure: n=4; duration min/median/max = 180630/180681.0/180711 ms; 4 within ±1,000 ms of 180,000 ms.
- `harness-codex-gpt56-medium` primary capability: n=17; duration min/median/max = 180624/180695/181740 ms; 16 within ±1,000 ms of 180,000 ms.
- `harness-codex-gpt56-medium` recovery capability: n=1; duration min/median/max = 180597/180597/180597 ms; 1 within ±1,000 ms of 180,000 ms.
- `harness-codex-gpt56-high` primary infrastructure: n=1; duration min/median/max = 180737/180737/180737 ms; 1 within ±1,000 ms of 180,000 ms.
- `harness-codex-gpt56-high` primary capability: n=27; duration min/median/max = 180586/180713/181737 ms; 26 within ±1,000 ms of 180,000 ms.
- `harness-codex-gpt56-high` recovery capability: n=6; duration min/median/max = 180606/180648.0/180708 ms; 6 within ±1,000 ms of 180,000 ms.

These persisted process durations establish boundary clustering only. Queue/logical-run start–finish windows are not substituted for attempt duration. Provider/tool phase allocation and relay waiting inside Codex are unavailable; the relay audit has 73 selected Direct matches and zero Codex matches, so relay residuals cannot be computed.

## Limits and reproducibility

**INSUFFICIENT_EVIDENCE_FOR_COUNTERFACTUAL**: existing evidence cannot establish that a model would pass with longer time, that high reasoning caused expiry, that timeout caused the capability difference, or that increasing time would improve score. No new execution is necessary for the next bounded evidence review; a future causal timeout question would require a separately authorized controlled treatment.

- Only digest-bound selected authoritative attempts are counted. Four extra physical primary attempts (Direct 1, medium 2, high 1) have no selected manifest, and one high selected primary manifest was rejected for control mismatch. Thus 269 of 274 recorded physical primaries have authoritative manifests; timeout facts for the other five are NOT_VERIFIED. Counts are observed minima, not a complete physical-attempt census.
- Known timeout-related censoring is historical association: two unresolved slots now end in protocol_error, not a timeout category. It is not proof that timeout caused missingness or capability differences.
- Trace-proven execution_budget_exhausted remains capability failure under the frozen budget; it is not missingness and is never removed or recovered for sensitivity.
- The 300-second plan wall-time contract, 90-second task budget, 180-second provider request timeout, 180-second Codex outer process deadline, and 15-second verifier timeout have distinct scopes. Recorded provider metadata does not prove an enforced Codex-wide output-token cap.
- Direct HTTP timeout is a transport phase timeout, not the Codex outer process deadline. Near-boundary duration (absolute difference <=1000ms) is a descriptive diagnostic, not a significance test or a timeout detector.
- Formal eligibility uses five COMPARABLE capability pairs per task. Complete pairs alone do not establish comparability; prior effect labels are descriptive frozen system/configuration observations.
- No longer-timeout treatment, complete Codex provider-call timing, or random missingness evidence exists. Longer-budget pass outcomes, relay causation, and reasoning-caused timeouts cannot be concluded.
- Bounded later review can proceed with these limitations; this status does not authorize that next phase or any real execution.

Reproduce (requires the persisted evidence tree; `--evidence-root` can relocate it):

```sh
uv run --locked python -m scripts.analyze_kb4_timeout_sensitivity --check
```

The JSON includes source byte digests, safe attempt facts, all 270 slot identities, exact pair ledgers, task/language/category distributions, prior comparison readouts, and campaign reconciliation. `--check` validates structure/reconciliation and compares both generated files byte for byte. No source artifact is rewritten. Provider/Harness/Judge/Matrix calls: **0**. Discordant attribution, real ablation, K-C, Full Release CI, and expensive qualification regeneration: **NOT RUN**.
