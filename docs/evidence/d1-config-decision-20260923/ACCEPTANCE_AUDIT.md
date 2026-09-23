# D1 acceptance audit — 2026-09-23

**COMPLETE / INSUFFICIENT EVIDENCE** is the closeout of the bounded decision, not completion
of the planned 20-run campaign. This audit changes no frozen protocol, trial receipt, source
bundle, or `result.json`. The earlier `BLOCKED_BEFORE_D1_ACCEPTANCE` label in that immutable
result is retained as the original stopping record. The latest user instruction clarifies that
acceptance requires complete *slot status accounting* and an evidence-bounded decision, not
dispatch of every slot after a frozen hard-stop condition.

| Acceptance check | Observed evidence | Verdict |
| --- | --- | --- |
| Fixed `2 configs × 2 tasks × 5 trials` | `campaign.json` has 20 unique scheduled identities; `result.json` has exactly indices 0–19 | PASS |
| Every planned slot has a state | 1 `verified_pass`, 1 `harness_error / NOT_VERIFIED`, 18 `NOT_RUN` | PASS |
| Verified outcome has independent verifier evidence | Trial 00 receipt and original external verifier manifest/report: 20/20 checks, exit 0, no timeout | PASS |
| Unknowns are preserved | Trial 01 verifier `NOT_RUN`, usage `UNKNOWN`; cost `NOT_AVAILABLE`; root cause `UNKNOWN` | PASS |
| Decision is within frozen scope | `INSUFFICIENT EVIDENCE`; two tasks, environment, versions, budget and configs only | PASS |

Only **2/20** trials were attempted. The frozen stop rule prevented the other 18 dispatches;
they are not inferred outcomes. Consistency, five-trial median latency and comparable steps per
verified success remain `NOT_VERIFIED`; observed cost per verified success is `NOT_AVAILABLE`.
The one verified success does not support switching or a global comparison. Trial 01 reached
the 600-second evaluation timeout; its Model/Harness/Tool root cause is not established.

Read-only audit inputs: [`campaign.json`](campaign.json), [`result.json`](result.json),
[`receipts/00.json`](receipts/00.json), [`receipts/01.json`](receipts/01.json), and the
digest-bound original bundle under `/home/dev/artifacts/samescale-d1-20260923/campaign-00/`.
The original verifier manifest identifies a network-isolated verifier run with exit 0 and the
trial receipt records 20/20 checks. Full original bundles are local private dependencies;
the portable receipt here is not an independent rerun.
