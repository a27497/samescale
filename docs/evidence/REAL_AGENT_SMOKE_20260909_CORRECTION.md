# Real Agent smoke: effective-limit correction

Correction dated 2026-09-09. The original v6 report and all five frozen evidence files remain
unchanged. This note supplements [the accepted smoke](REAL_AGENT_SMOKE_20260909.md).

The accepted session `analyst-0be376756a4f447bbdeeb44a58b292b5` froze **4 decisions / 12 tools**,
as recorded in `real-agent-smoke-v6/session-summary.json` and the v6 input profile. Its report
rendered `4/8 decisions` because report metadata used the global default instead of the session's
effective decision ceiling. The correct interpretation is **4/4 decisions and 9/12 tool calls**.
This is a report-limit discrepancy; no additional requests are authorized or observed by this note.

New reports receive the effective limits from the investigation state. Existing report defaults,
recorded values, and canonical digests remain readable without rewriting historical evidence.
Regression coverage exercises independently lowered decision/tool ceilings and verifies the
original v6 report digest remains
`sha256:1733eace25488c8e435e2fd1f7d5e6d1ae7c676a047259ab3edc3dd6315c19b1`.

Other limits remain: the approval label is not an authenticated identity, the approved plan has
not been executed, and summed provider latency is not the complete investigation wall time.
