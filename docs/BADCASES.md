# Core BadCases

Phase K-B4.3: **three real verifier-backed V6 BadCases frozen** in the canonical
[`release/badcases.json`](../release/badcases.json). The compact
[`kb4-badcase-freeze.json`](../release/kb4-badcase-freeze.json) binds the accepted K-B4.2
source digests, exact selection, and canonical model digest. It is a reconciliation receipt,
not a second BadCase payload.

| Stable slot | Accepted candidate | Cell / task / repeat | Factual diagnosis |
|---|---|---|---|
| badcase-1 | kb4-candidate-ab5922b348dbc889 | harness-codex-gpt56-high / core-java-settings-merge / 0 | No Modification; four verifier checks fail, score 0.2 |
| badcase-2 | kb4-candidate-93e0206579a4fa92 | harness-codex-gpt56-high / core-python-deduplicate / 2 | Test Failure; empty-key-rejected fails, four checks pass, score 0.8 |
| badcase-3 | kb4-candidate-4d16e08b5834b3fb | model-gpt56-relay-responses / core-python-deduplicate / 0 | Test Failure; empty-key-rejected fails, four checks pass, score 0.8 |

All tasks are version 1.0.2. Canonical run identities name the logical experiment run;
`frozen_evidence.execution_run_identity` identifies the physical `-a1` attempt. All three
selected observations use primary evidence and have no recovery attempt. The records retain
task digests, slot/repeat, profile identities, artifact bindings, complete verifier checks,
source differences, safe trace facts, and frozen comparability context.

Each classification is **OBSERVED_FACT**, with `root_cause: null`. The Java trace records no
commands or edits; its workspace-unavailable self-report does not establish a runtime cause.
The Python implementations accept an empty key. Their public instruction describes non-empty
keys without expressly requiring empty-key rejection, while the frozen verifier requires it.
Specification interpretation remains an explicit **ATTRIBUTION_HYPOTHESIS**, with evidence
needed to verify or falsify it. No private reasoning or controlled causal attribution is claimed.

The two Python cases share a failure signature: three cases do not establish three mechanisms.
Direct has no normalized agent trace and carries no invented trajectory facts. Its explanation
rests on the verifier and final source diff. The two high-Codex cases retain COMPARABLE paired
context with integrity-limited passing counterparts; the Direct pair is PARTIALLY_COMPARABLE.
The selected failures' own required bundles are intact. The held medium/Python/repeat-4 candidate
`kb4-candidate-d010ad8e7a9a9e42` is excluded, and missing historical artifacts are not repaired.

## Deterministic verification

```sh
uv run --locked python -m scripts.freeze_kb4_badcases --check
```

This reopens the original persisted failure bundles under
`/home/dev/harnesslab-evidence/core-real-matrix-v6` (override with `--evidence-root`), verifies
manifest/file/tree digests and identities, and compares canonical JSON and the receipt byte for
byte. It never executes a subject or verifier. Missing or changed selected evidence blocks the
check; it cannot trigger substitution or a replacement run. Generation accepts only the original
placeholder file or the identical frozen payload and refuses to overwrite drifted BadCases.

Portable CI separately verifies the schema, exact accepted selection, repository source hashes,
logical reference bindings, verifier facts, and canonical/receipt bytes without claiming access
to external original files. The original bundle audit was performed during this freeze.
K-B4.1 and K-B4.2 artifacts remain historical snapshots at their accepted commits. To reproduce
K-B4.2's original full `--check`, use its accepted checkout; its old BadCase/doc source hashes
remain preserved, while successor tests bind their authorized replacements.

Timeout Sensitivity and Discordant Pair Attribution are complete. The three BadCases are frozen.
The Final Attribution Report and K-B4 Final Gate are not complete; K-C is not started. No new
external execution, real ablation, Full Release CI, or qualification regeneration occurred here.
