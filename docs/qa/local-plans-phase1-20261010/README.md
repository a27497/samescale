# Phase-1 local planning acceptance — 2026-10-10

Base `eb115417772bc36063afd6151c0d6da449ab7883`, independent branch
`codex/product-mvp-phase1-20261010`. Base main Fast CI
[37967471260](https://github.com/a27497/samescale/actions/runs/37967471260) and Offline Regression
[37967471294](https://github.com/a27497/samescale/actions/runs/37967471294) were rechecked SUCCESS.
Publication/exact candidate SHA CI is reported separately in the Draft PR; it is PENDING at this
pre-publication document snapshot. No merge, deployment or Phase 2 is authorized.

The implemented path is **trusted local TaskPackage → managed Custom snapshot/inspection → one
compatible Codex configuration → local preflight → explicit plan-only confirmation → immutable
PostgreSQL plan → refresh and process-restart reads**, with current drift shown beside the original.
There is one task, one target and one planned slot; no fake second Cell. Legacy two-configuration
experiments are unchanged. Policy-approved local image metadata is read without image pull/CLI.
No task Python, Worker, Agent, Provider, Judge or Verifier is executed; no paid execution authorization
is stored. The execution API is permanently closed in Phase 1.

| Check | Observed result / evidence |
| --- | --- |
| Backend and legacy compatibility | 157 distinct tests PASS: local plans (75), local model configuration/planning bindings, Registry, Custom Task Store/CLI/API, CI and product-distribution contracts; [log](backend-compatibility.txt) |
| Phase-1 safety | 75 tests PASS on final source; external HTTP/process launch is forbidden by sentinels, image metadata stub explicitly labeled; permissions, unsafe paths/files, admission, drift, budget, concurrent duplicates, malformed JSON/confirmation, corruption and both append-only DB triggers; [log](phase1-safety.txt) |
| Frontend | 194/194 across 16 files PASS, includes old 179 and 15 Phase-1 cases; [log](frontend-tests.txt); Vue typecheck + isolated Vite production build PASS |
| Python/whitespace | Full Ruff check/format, 396-file mypy and `git diff --check` PASS; [mypy](python-types.txt) |
| Actual browser | Chromium 153.0.8010.12, actual built Vue + loopback API + isolated migrated PostgreSQL, 1366/1440px; 30 checks PASS, no normal runtime/console error or external browser request; [receipt](browser.json) |
| Real process restart | Dedicated API stopped/restarted with the same test DB: exact saved SHA, current revalidation, zero Run/Episode and no execution authorization; 3 checks PASS; [receipt](restart.json) |
| Offline protection | Network namespace with no route/loopback down, 73 tests PASS, two saved-run replays with all five byte-identical outputs, zero subject/verifier/model/Provider/Judge calls; [receipt](offline-regression.json) |
| Workspace/services | Original UI-2 17 dirty changes/1,494 checked files unchanged; six original worktrees' HEAD/status/diff/file hashes match; 14 existing services and 437 read-only mounted files unchanged; [receipt](protection.json) |
| Disposable data only | New test PostgreSQL upgraded to 0011; historical experiment/run/attempt/lease/reservation counts remain zero in this disposable DB; [receipt](isolated-db.json). This is not a production row-hash audit. Existing databases were not queried/migrated/written. |

Browser source admission/behavior evidence is **explicitly synthetic** from
`tests/local_plan_helpers.py`, with a verifier that raises if invoked. This checks the planning
contract, not behavioral validity of a real engineering task. Real existing task qualification is
an operator-owned external prerequisite; structure or synthetic test success must never qualify a
real task. The approval record, current policy and runtime identities are all bound independently.

The first browser script used an ambiguous all-button selector after the technical disclosure added
copy buttons; it was narrowed to the actual disabled execution control. A restart probe originally
arrived before the new process was ready; the final probe waits for `/status`. CI mirror/expected
command contracts were aligned with the newly required suites; a physical-trigger test was fixed to
use only its own rolled-back UUID rows alongside browser fixtures. Export validation then exposed
Registry's HTTP-only credential alias: dedicated canonical frozen snapshot types now preserve API
JSON → typed reader → identity hashing, without altering the historical Registry API. Corrected
checks were rerun; intermediate failures remain in the task's temporary audit logs, not represented
as additional passes or product evidence.

Review images: [saved 1366](saved-1366.png), [saved 1440](saved-1440.png),
[stale 1440](stale-1440.png), [restarted 1440](restarted-1440.png). Screenshots were inspected for the
retained white/Cobalt layout, clear plan-only boundary, blocking reasons and preserved original.
The [saved plan example](saved-plan-example.json) is an API-exported, digest-validated synthetic
planning snapshot, not a Run/Episode or real model result. [Source binding](source-binding.json)
records changed runtime/test/CI bytes, the tested application code digest and built asset hashes.
[Browser script](browser-check.cjs) and [restart script](browser-restart-check.cjs) require explicit
loopback/test-fixture parameters and the existing Playwright installation; they add no dependency.

Limits: Grok final independent reassessment remains **NOT_CONFIRMED**. No live Provider/credential
use/balance/protocol probe, actual Codex CLI launch, real Verifier isolation, real task execution,
Worker claim/cancellation, enforced token/cost cap, reserved quota, remote import, multi-user/SaaS,
production Compose mount/socket setup, mobile/non-Chromium or full screen-reader acceptance was run.
Wall-time timeout support is a future existing-runner requirement; USD/token figures are reference
estimates. Phase-1 confirmation never authorizes Phase-2 execution. See
[operator setup](../../LOCAL_PLANNING.md) and [Phase-2 interface gaps](../../PROJECT_BLUEPRINT.md#phase-2-的具体接口与缺口规划不启动).

STOP after the authorized commit/push/Draft-PR/exact-SHA CI handoff. Do not enter Phase 2.
