# Acceptance Plan P0-0 / P0-1 local QA — 2026-10-18 (Asia/Shanghai)

Base: `e491090b748bfab653466cf2e3fe8f03220bcc64`; isolated branch
`codex/acceptance-plan-p0-20261018`. All new evidence here is **SYNTHETIC_ONLY**.
This is feature QA, not a MiniShop result or independent acceptance receipt. Live milestone state
belongs to [CURRENT_MILESTONE](../../../CURRENT_MILESTONE.md); [product contract](../../ACCEPTANCE_PLANS.md).

## Observed results

| Check | Actual result |
| --- | --- |
| `tests/test_acceptance_plans.py` | 32 passed, zero skipped: sources, manual fallback, edited provenance, confirmation/freeze/revision, duplicate/concurrent mutation, restart, snapshot/plan corruption, permissions, public Demo, input/storage caps, no execution, interrupted publication recovery |
| CodeSnapshot + ExternalEvidence/P1 | 142 + 32 + 20 = 194 passed; synthetic sandbox mocks only |
| Isolated PostgreSQL regressions | 103 passed: local plans 75, health 2, CI routing/workflow 25, DTO privacy 1; migrations applied only to the newly owned disposable test DB |
| `scripts/ci_s3.sh` | 277 passed in a network namespace with loopback down; two offline Replay passes and all five frozen golden hashes unchanged; [result](offline-result.json) |
| Full Vitest | 294 passed in 23 files, including 14 new scope UI tests; final snapshot wording check 10 passed; final scope error-state checks 14 passed |
| Frontend production build | TypeScript and Vite passed; locked dependencies unchanged |
| Python static checks | Ruff check/format 928 files; mypy 477 files passed |
| Real browser | Chrome 153.0.8010.52, 1440×1050 desktop, 26/26 checks; [report](browser-report.json) |
| Protected evidence | 442/442 repository protected files unchanged; [summary](integrity-summary.json). No diffs in old snapshot/external/worker/TaskStore/task/release/evidence/recruiter paths. |

Counts overlap between targeted and offline runs; they are not added into a fabricated unique total.
[Test summary](test-summary.json) preserves the initial failed run separately.

Browser used the built frontend and real FastAPI on an owned loopback port, independent temporary
scope/evidence stores and two opaque text-only snapshots. No production DB or source was required.
The Prompt “给我做一个轻量电商系统，命名为 MiniShop” is synthetic input, not the historical delivered
MiniShop source. The failure fixture is separately corrupted only after selection to test server refusal.
After an actual API process stop/start, the same saved plan digest was read again. Snapshot detail
entry and ambiguous/manual draft were exercised in additional browser checks. Screenshots contain
only synthetic content; no credential value, private path, real code or historical receipt is published.

Runtime guards rejected subprocess/subject, Provider/network and physical Verifier boundaries.
All attempt counters stayed **0** in the scope browser service; acceptance tests also install named
runtime/transport guards. No Agent/LLM/Provider/Judge/Verifier campaign or real subject code was executed.
These zero counters concern the scope feature and its guarded local tests. Remote standard Fast CI
separately runs existing synthetic Tier-B baseline/oracle fixtures via `execute_verifier`; it is not
a zero-process or zero-synthetic-fixture-execution run and does not touch real MiniShop assets.
The PostgreSQL container was test infrastructure only, with a unique name and dynamically allocated
loopback port. Only that newly owned container was removed after its checks.

## Screenshots

- [Permission refusal](01-permission-denied.png)
- [MiniShop draft: original quotes, ambiguity and five unapproved suggestions](02-draft.png)
- [Confirmed frozen version: three separate status dimensions](03-frozen.png)
- [Prior frozen event while a new revision exists](04-history.png)
- [Corrupt synthetic snapshot binding refused](05-corrupt-snapshot.png)
- [Ambiguous Prompt and manually added unapproved candidate](06-manual-fallback.png)

The full-page screenshots were visually inspected; no horizontal overflow at 1440px and no browser
runtime errors/external requests in the final main browser run. This is not human visual approval,
mobile acceptance, comprehensive accessibility certification or cross-browser coverage.

## Corrections and limitations

The first cross-module run had **247 passed, 2 failed, 1 error**. The failures identified the missing
new test entry in `.github/ci-core-shards.json`; the error was a health test run without a disposable
DB. The shard was registered and the 103-test isolated DB/CI run passed without weakening assertions.
Initial lint found formatting/localized punctuation, then mypy found the interruption test's use of
an unexported imported module; these were corrected. The publication test led to atomic first-directory
publication so an interrupted first write cannot strand a visible empty plan.

Browser harness preparation had attempts before fixture/build/server readiness, one owned-port
collision, a hidden snapshot-directory lookup error and an assertion before SPA navigation completed.
Those attempts were incomplete, not passes; readiness/path/wait handling was corrected and the final
main 23 checks plus 3 restart/entry/manual checks completed. Old QA directories remain separate from
final evidence. No product service/container was stopped for these corrections.

No DB migration added; real MiniShop/C05/C13/1.2.0 qualification, physical Verifiers, new live Agent
runs, full release, mobile and non-Chromium checks were **NOT_RUN**. Public sharing, pre-registration,
authenticated named-human review, privileged filesystem rollback resistance and distributed locking
are not claimed. The shared-operator, 0700/0400 owned-file, bounded single-host POSIX journal reuses
the existing private architecture. CI status and exact pushed PR head are separate remote observations.


Remote push CI on `493852f451c9ec1e06258291db45de4fd7373051` found a real concurrency defect:
[full shard 1](https://github.com/a27497/samescale/actions/runs/39067762931/job/117498893086)
had 1 failed / 222 passed (`test_idempotency_and_concurrent_writers`); the same PR-triggered shard
passed, exposing scheduling dependence. Store inventory scanned staging paths before acquiring the
publication flock, so a concurrent rename/removal could produce a false integrity error. The fix
moves the inventory scan inside that lock and adds a deterministic test that a competing descriptor
cannot acquire the lock at scan time. The original assertion is preserved and failure diagnostics
now report status/error codes. Final focused and offline verification are recorded above; initial
CI failure is retained, not relabeled as a pass. UI/browser behavior is unchanged by this lock fix.
