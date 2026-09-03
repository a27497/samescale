# K-B4.2 Discordant pair failure attribution

**READY_FOR_BADCASE_FREEZE**

Analysis only. Exact task/version/repeat and paired-slot identity determine discordance. Frozen outcomes, primary/recovery evidence, and comparability are retained. No final BadCases are selected or frozen.

## Counts and eligibility

| Comparison | Complete | Left PASS/right FAIL | Left FAIL/right PASS | Discordances by comparable/partial/not comparable | Missing (timeout-affected) |
|---|---:|---:|---:|---|---:|
| `gpt56-relay-direct-vs-codex` | 82/90 | 17 | 1 | 0/18/0 | 8 (1) |
| `codex-gpt56-reasoning-effort` | 83/90 | 25 | 9 | 2/0/32 | 7 (2) |

Direct/medium: all 82 complete pairs are PARTIALLY_COMPARABLE. Medium/high: 42 complete pairs are COMPARABLE and 41 NOT_COMPARABLE. Among discordances, the two comparable cases both favor medium; the 32 not-comparable cases split 23 medium-pass/high-fail and 9 medium-fail/high-pass. Both comparisons retain formal eligibility=false. Missing pairs are exclusions, never capability failures.

## Evidence-supported diagnosis

- **OBSERVED_FACT:** Direct/medium has 16 execution-budget failures and 2 verifier-backed failures. Medium/high has 32 execution-budget failures and 2 verifier-backed failures. All budget failures retain the native `Timeout` class with CAPABILITY scope and `execution_budget_exhausted` subtype; they are not infrastructure outcomes or eligible verifier-backed BadCases.
- **OBSERVED_FACT:** High `core-java-settings-merge`, repeat 0, left its workspace unchanged. Its verifier failed `normalizes`, `preserves-order`, `duplicate-rejected`, and `invalid-rejected` (score 0.2). The trace has thread/turn start, one public agent message, and turn completion; no commands or edits. The agent's workspace-unavailable statement is an unverified self-report, not an established runtime cause. Native taxonomy: `No Modification`.
- **OBSERVED_FACT:** Direct `core-python-deduplicate` repeat 0, medium repeat 4, and high repeat 2 each fail only `empty-key-rejected` (score 0.8). Their bound source edits accept empty keys; four other ledger checks pass. Native taxonomy: `Test Failure`. Two Codex traces issue local assertions accepting empty keys, but shell exit zero and public self-report cannot prove every local assertion ran or passed.
- **DIAGNOSTIC_ASSOCIATION:** Budget exhaustion dominates selected discordances. This is not proof that timeout, relay waiting, or reasoning effort caused the observed capability difference.
- **ATTRIBUTION_HYPOTHESIS:** Empty-key acceptance may reflect a specification interpretation gap: the public instruction defines non-empty-key behavior but does not expressly require empty-key rejection, while the frozen verifier does. Frozen instruction, code edits, and public check commands can corroborate the observation; causal verification would need a separately authorized explicit-contract control. No private reasoning is inferred and no score is changed.

## Controlled pair-level evidence and integrity limits

The two frozen COMPARABLE discordances are medium/high `core-java-settings-merge` repeat 0 and `core-python-deduplicate` repeat 2. They support recorded pair-level contrasts under the same operator-trusted route, with reasoning effort as the declared treatment. Repository semantics limit this to controlled-ablation association, not proof of a mechanism or a formal reasoning-effort effect. Their passing medium workspace/verifier bundles are currently incomplete, further limiting trajectory audit. **CONTROLLED_ATTRIBUTION claims: 0.** Partial and not-comparable pairs contribute none.

All 95 unique discordant member manifests and available trace files were digest-checked. Of these, 17 workspace trees and 9 verifier trees fail their recorded directory digests. Recorded missing files are compiled `.pyc`/`.class` artifacts; available source-file bindings and verifier stdout digests still match. This does not establish when or why the files disappeared. Missing files are neither recreated nor ignored in complete-bundle eligibility. The machine-readable ledger preserves every mismatch separately from immutable capability/comparability results.

## Ranked BadCase candidates (not final selections)

| Review rank | Candidate | Cell/task/repeat | Verifier finding | Suitability |
|---|---|---|---|---|
| 1 | `kb4-candidate-ab5922b348dbc889` | `harness-codex-gpt56-high` / `core-java-settings-merge` / 0 | normalizes, preserves-order, duplicate-rejected, invalid-rejected | `READY_FOR_REVIEW` |
| 2 | `kb4-candidate-93e0206579a4fa92` | `harness-codex-gpt56-high` / `core-python-deduplicate` / 2 | empty-key-rejected | `READY_FOR_REVIEW` |
| 3 | `kb4-candidate-4d16e08b5834b3fb` | `model-gpt56-relay-responses` / `core-python-deduplicate` / 0 | empty-key-rejected | `READY_FOR_REVIEW` |
| Held | `kb4-candidate-d010ad8e7a9a9e42` | `harness-codex-gpt56-medium` / `core-python-deduplicate` / 4 | empty-key-rejected | `HOLD_INTEGRITY_MISMATCH` |

Three candidates have intact failure bundles; the medium Python candidate is held because compiled bytecode is absent from its workspace/verifier trees. Ranking favors the distinct unchanged-workspace case, then structured edit/tool evidence. The eligible candidates span only two failure signatures; the two Python cases are related, not three distinct mechanisms. Direct's explanation uses verifier and source diff because it has no agent trace. All Python cases retain the public-contract limitation above.

**No new external execution is required before factual BadCase review/freezing of eligible evidence.** The held case would need exact original artifact recovery, not a replacement run. This candidate set does not select the final three or modify `release/badcases.json`.

## Reproduction and boundaries

```sh
uv run --locked python -m scripts.analyze_kb4_discordant_pairs --check
```

The JSON records source hashes, all discordances/concordances/exclusions, per-member verifier checks, trace ordinals/command hashes, source diffs, immutable primary/recovery identities, comparability reasons, task evidence tiers, hypotheses, candidate eligibility, and reconciliation. `--check` rebuilds from persisted artifacts and compares JSON/Markdown byte for byte. Individual files can be audited even where directory completeness is limited.

- Every GPT direct/medium complete pair remains PARTIALLY_COMPARABLE; no Harness-uplift causal attribution is permitted.
- Only two of the 34 medium/high discordances are COMPARABLE; the other 32 must never contribute controlled claims. Formal eligibility remains false for both comparisons.
- Known current tree mismatches are retained without repair. Missing .pyc/.class paths match recorded inventories, but their absence is not proof of when or why loss occurred; no binary reconstruction is attempted.
- Verifier stdout has its own immutable digest binding even when a containing verifier tree is incomplete; report-level facts remain distinguishable from complete-bundle eligibility.
- The four candidate records provide only two distinct verifier failure signatures. One candidate is held for integrity; do not pretend three distinct engineering mechanisms have been found.
- Direct lacks agent traces; Codex streams lack complete provider timing and private reasoning. Five physical primary timeout facts remain unknown under K-B4.1.
- No compile/build failure is established among these verifier-backed failures. Nonzero git commands are ancillary tool facts, not causes of the behavioral failure. Issued self-check syntax does not prove checks actually passed.
- New external execution is not required for the three intact candidates. The integrity-held candidate needs exact original artifact recovery, not a replacement experiment. Canonical final BadCases remain unchanged.

**NOT RUN:** provider/Harness/Judge/Matrix calls (all 0), real ablation, final BadCase freeze, final K-B4 Attribution Report, K-C, Full Release CI, and qualification regeneration.
