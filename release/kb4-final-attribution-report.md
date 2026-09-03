# K-B4 Final Attribution Report

**READY_FOR_KB4_FINAL_GATE** — evidence reconciliation only; K-B4 is not approved. Final Gate and K-C are NOT_RUN.

## 1. Evidence scope

The frozen V6 campaign contains 630 logical slots (18 tasks × 5 repeats × 7 cells), with 599 capability results, 29 infrastructure outcomes and two cancellations after bounded recovery. [F07]

Experiment `core-real-matrix-v6`; plan `sha256:c18afc7b003a379f3456b23649e6d161da55e4fb5a34b4702dffbff35fb3604a`; dataset `sha256:d07f6c96e3bd7882137355cb8b5d2d5682e3d51bffcedce6292375d4a54bbd1d`. The JSON binds exact source hashes and Analyst FactAssertion paths. This deterministic synthesis creates no new experimental evidence or statistics.

## 2. Core observed results

| Configuration | Planned | Pass/fail | Capability n | Capability pass rate | Infra | Cancelled | Missing capability | Recoveries |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| Direct GPT | 90 | 83/3 | 86 | 96.5% | 4 | 0 | 4 | 14 |
| Codex medium | 90 | 65/21 | 86 | 75.6% | 3 | 1 | 4 | 19 |
| Codex high | 90 | 47/38 | 85 | 55.3% | 4 | 1 | 5 | 19 |

Capability n is pass+fail; missing capability includes infrastructure and cancellations. Operational rates retain all planned slots. Primary/recovery outcomes, Wilson intervals and observed usage coverage remain in JSON; missing values stay null. These are frozen configuration observations, not a causal ranking. [F01–F03]

## 3. Direct GPT versus Codex medium

Direct GPT→Codex medium has 82/90 complete pairs, discordances 17/1 (left-pass/right-fail versus reverse), and a descriptive equal-task capability delta of -19.35 percentage points; formal eligibility is false. [F04]

All 82 Direct/medium complete pairs are PARTIALLY_COMPARABLE: observed model, provider configuration, and trace coverage limit interpretation. No causal Harness uplift is established.

## 4. Codex medium versus high reasoning

**ABLATION_EVIDENCE_PRESENT_WITH_LIMITATIONS**. The declared reasoning_effort treatment has real medium/high V6 observations and 42 comparable pairs, but no task has five comparable repeats. Its two comparable discordances favor medium; this supports bounded pair-level association, not a formal effect or verified mechanism. [F06]

Of 83 complete pairs, 42 are COMPARABLE and 41 NOT_COMPARABLE. Of 34 discordances, two are COMPARABLE (both medium PASS/high FAIL); 32 are NOT_COMPARABLE (23 medium PASS/high FAIL, nine reverse). The comparable cases are Java settings-merge repeat 0 and Python deduplicate repeat 2. Their task comparable n values are 2 and 4, and passing comparator trees are incomplete. No task reaches the five-comparable-repeat formal requirement. [F05–F06, F11]

### Frozen descriptive paired statistics

Deltas are variant minus baseline, in percentage points; capability deltas use equal task weighting. The original 50,000 task-cluster bootstrap replicates, seed 20260902, and secondary exact McNemar results are retained without recomputation.

| Baseline → variant | Capability delta [95% CI], pp | Operational delta [95% CI], pp | McNemar exact p |
|---|---|---|---:|
| Direct GPT → Codex medium | -19.35 [-25.74, -12.87] | -20.00 [-28.89, -11.11] | 0.000144958496 |
| Codex medium → Codex high | -20.56 [-33.89, -7.22] | -20.00 [-32.22, -7.78] | 0.009041185491 |

These estimates include partially/not-comparable complete observations. Their intervals and p-values do not override Comparability or establish a formal Harness/reasoning effect. Row-weighted deltas, separate operational estimands, overlapping exclusion flags and paired latency coverage remain inspectable in JSON. Controlled-attribution claims: **0**. [F04–F06]

## 5. Timeout sensitivity

5 primary infrastructure timeouts were observed; 3 recovered to capability evidence and 2 remain unresolved with final protocol errors. 5 physical-primary timeout facts remain unknown. [F08]

All five observed primary infrastructure timeouts and most trace-proven capability budget exhaustions cluster within one second of the recorded 180-second Codex process boundary. This is a duration observation, not evidence that more time would change results. [F09]

The five timeouts comprise four medium and one high observation. All five entered one bounded recovery; three medium slots passed, while medium Java deduplicate repeat 4 and high Python clamp repeat 2 ended with protocol errors. Across GPT/Codex, 269 of 274 physical primaries have authoritative timeout facts. The provider-request, Codex-process, task, verifier and plan deadlines have different scopes (180/180/90/15/300 seconds); provider metadata is not proof of a Codex-wide token ceiling.

## 6. Failure taxonomy and trace diagnosis

Direct/medium discordances contain 16 native Timeout and two Test Failure observations; medium/high contain 32 Timeout, one No Modification and one Test Failure. Trace-proven execution_budget_exhausted stays capability failure; infrastructure/protocol gaps remain excluded. [F10]

K-B4.2 inspected 95 unique discordant members and retained 17 workspace-tree and nine verifier-tree mismatches, with independently matching available source/trace/verifier-output bindings. [F11]

Deterministic verifier/build/source evidence outranks structured tool evidence, which outranks agent self-report. The Java agent's workspace-unavailable statement does not prove a runtime cause; incidental git errors and issued local-check syntax do not supersede verifier failure. Direct's lack of an agent trace remains explicit.

## 7. Three factual BadCases

The canonical payload is [badcases.json](badcases.json), bound by [kb4-badcase-freeze.json](kb4-badcase-freeze.json). No cases are reselected or rewritten.

- **badcase-1** (VERIFIED_FACT): harness-codex-gpt56-high / core-java-settings-merge@1.0.2 / repeat 0: No Modification, deterministic verifier score 0.2. The workspace is unchanged. The deterministic verifier fails normalizes, preserves-order, duplicate-rejected, and invalid-rejected; input-unchanged passes. Classification remains OBSERVED_FACT and root_cause is null. Evidence `run:run-c2e4e8b22b0696a1c080f57deee651e363390f8a7a7ca7ac22a8042895d5591a`, `sha256:f2f4a1fd5bd9351589cdb7c844f587ed79b88051aa49b0a4e5d5249bbadaa8ba`; canonical `/slots/0`. Trace: `REPORTED`. Lesson: Check that the required implementation changed and inspect deterministic verifier results before declaring completion. This is an engineering safeguard, not a verified remedy for the unknown cause. Limits: The failure bundle is intact, but the passing comparison member has a tree-integrity limitation. Frozen comparability is retained; complete paired-trajectory audit and causal attribution are not claimed. [B01]
- **badcase-2** (VERIFIED_FACT): harness-codex-gpt56-high / core-python-deduplicate@1.0.2 / repeat 2: Test Failure, deterministic verifier score 0.8. The deterministic verifier fails empty-key-rejected (score 0.8); first-records, identical-retry-idempotent, conflict-rejected, and conflict-preserves-original pass. The digest-bound events.py implementation stores an empty key and returns True. Classification remains OBSERVED_FACT and root_cause is null. Evidence `run:run-d2fdf5b3e14b70f4e00c6c73496a5b64252a3d38c7bf25bb7d19a23d1674ae00`, `sha256:be7fc1d19b70ebe03fc1cb761a46d510d7ea2a0f245b87bdb84db7daf64f7d36`; canonical `/slots/1`. Trace: `REPORTED`. Lesson: Review public contract and boundary-case checks together before interpreting the failure. Explicit empty-key expectations are a proposed engineering clarification, not a proven causal remedy; the frozen task and verifier remain unchanged. Limits: The public instruction specifies non-empty-key behavior without expressly requiring empty-key rejection; the frozen verifier does require rejection. This limitation does not alter the frozen score. The failure bundle is intact, but the passing comparison member has a tree-integrity limitation. Frozen comparability is retained; complete paired-trajectory audit and causal attribution are not claimed. [B02]
- **badcase-3** (VERIFIED_FACT): model-gpt56-relay-responses / core-python-deduplicate@1.0.2 / repeat 0: Test Failure, deterministic verifier score 0.8. The deterministic verifier fails empty-key-rejected (score 0.8); first-records, identical-retry-idempotent, conflict-rejected, and conflict-preserves-original pass. The digest-bound events.py implementation stores an empty key and returns True. Classification remains OBSERVED_FACT and root_cause is null. Evidence `run:run-4b9f1267620233e0656eeba898ed4cde10ff55d1a3303dfc3bdfc4e3cbab89e4`, `sha256:1a5945444b5ba2d0d9c1709c058af738ca3d9474afda22424cc7fbf01349758d`; canonical `/slots/2`. Trace: `NOT_REPORTED`. Lesson: Review public contract and boundary-case checks together before interpreting the failure. Explicit empty-key expectations are a proposed engineering clarification, not a proven causal remedy; the frozen task and verifier remain unchanged. Limits: The public instruction specifies non-empty-key behavior without expressly requiring empty-key rejection; the frozen verifier does require rejection. This limitation does not alter the frozen score. Direct has no normalized agent trace. No command, edit sequence, or private reasoning is reconstructed; the factual explanation uses verifier output and the final source diff. The failure bundle is intact, but the passing comparison member has a tree-integrity limitation. Frozen comparability is retained; complete paired-trajectory audit and causal attribution are not claimed. [B03]

Java's trace contains no commands or edits. High Python has public edit/check evidence; Direct Python has verifier/source evidence only. All root causes remain null; the three cases represent two failure signatures. A factual failure does not establish a causal mechanism, Harness uplift or a formal reasoning-effort effect. These shared limits and the case-specific limits are bound in the JSON ledger.

## 8. Attribution claim ledger

Every JSON claim carries a stable ID, level, human-readable statement, native VerifiedFact assertions/canonical rendering, evidence references, limitations and causal-language permission=false. Repository OBSERVED_FACT BadCases map to VERIFIED_FACT assertion semantics without upgrading attribution.

- **F06 — DIAGNOSTIC_ASSOCIATION:** The declared reasoning_effort treatment has real medium/high V6 observations and 42 comparable pairs, but no task has five comparable repeats. Its two comparable discordances favor medium; this supports bounded pair-level association, not a formal effect or verified mechanism.
- **A01 — DIAGNOSTIC_ASSOCIATION:** Execution-budget exhaustion dominates the selected discordances (16/18 Direct/medium; 32/34 medium/high). This is a diagnostic association, not proof that timeout or reasoning effort caused the capability difference.
- **H01 — ATTRIBUTION_HYPOTHESIS:** A public-contract interpretation gap may explain repeated empty-key acceptance. The instruction specifies behavior for non-empty keys without expressly requiring rejection of empty keys, while the frozen verifier requires ValueError. This does not establish the model's private reasoning or invalidate frozen scores.
  Required evidence: Review the frozen subject instruction, contract, bound source edits and public local-check commands. A causal test would require separately authorized explicit-contract control versus original-contract treatment; none is needed to freeze a factual verifier-failure case with this limitation.
- **CONTROLLED_ATTRIBUTION: 0.** COMPARABLE pair-level contrasts remain controlled-ablation associations with their original small-n and integrity limits.

## 9. Limitations and forbidden claims

- All 82 Direct/medium complete pairs are PARTIALLY_COMPARABLE: observed model, provider configuration, and trace coverage limit interpretation. No causal Harness uplift is established.
- Medium/high has 42 COMPARABLE and 41 NOT_COMPARABLE complete pairs; no task has five comparable repeats and formal eligibility is false. The 41 excluded controls cannot contribute controlled claims.
- The two COMPARABLE discordances support recorded pair-level contrasts under the operator-trusted route, not a causal mechanism or population-wide reasoning-effort effect. Their passing comparator trees are integrity-limited.
- Direct lacks an equivalent agent trace. Private reasoning and complete Codex provider-call timing are unavailable; no reasoning reconstruction or relay-phase causal claim is possible.
- Five physical-primary timeout facts are unknown (four extra attempts plus one rejected primary); timeout counts are observed minima. Missingness is not established as random.
- The three BadCases span two failure signatures. Python specification interpretation remains a hypothesis, and every canonical root_cause remains null.
- No longer-timeout treatment exists. Longer budgets improving results, reasoning causing expiry, or timeout causing the capability delta are unsupported counterfactual claims.
- The corpus is 18 Tier-A micro-contract tasks with at most five repeats per task. Descriptive configuration results do not establish universal coding capability or population-wide causal rankings.
- Capability uses pass+fail; operational pass rates retain planned slots. Infra/cancelled and missing usage remain explicit, never zero-filled into capability or usage. Existing cost estimates are accounting, not billing truth.
- K-B4.2's 17 workspace and 9 verifier-tree mismatches remain historical audit limitations; this report does not repair or reclassify them. K-B4.3 independently verified the selected failures' required bundles.

## 10. K-B4 requirement reconciliation

| Requirement | Evidence status | Claims |
|---|---|---|
| Codex medium/high reasoning ablation | ABLATION_EVIDENCE_PRESENT_WITH_LIMITATIONS | F05, F06 |
| Three real verifier-backed BadCases | FROZEN_VERIFIED | B01, B02, B03 |
| Failure taxonomy | EVIDENCE_PRESENT | F10, A01 |
| Trace diagnosis | EVIDENCE_PRESENT_WITH_LIMITATIONS | F11, B01, B02, B03 |
| Attribution report | REPORT_COMPLETE | F01, F02, F03, F04, F05, F06, F07, F08, F09, F10, F11, A01, B01, B02, B03, H01 |

These statuses reconcile available evidence; they do not approve K-B4 or authorize its Final Gate.

Reproduce:

```sh
uv run --locked python -m scripts.build_kb4_final_attribution --check
```

**NOT RUN:** provider, Harness, Judge, Matrix, ablation and Analyst LLM calls (all zero); subject reruns; qualification regeneration; Full Release CI; K-B4 Final Gate; K-C.
