# MVP Phase 2 — keyless local Worker acceptance — 2026-10-09

Base `main@304c516e274d094888e3205666419cd3811d0912`, both baseline workflows SUCCESS.
Worktree/branch `codex/product-mvp-phase2-20261009`. This receipt concerns local acceptance;
candidate SHA, Draft PR and exact-SHA remote CI are reported separately at publication.
No real Agent/Provider/Codex executable/login quota/model/Judge or paid execution was used.
Grok remains **NOT_CONFIRMED**. No merge, production migration, deployment or website change.

## Implemented and observed

Private UI → saved single-slot plan → separate exact plan/slot/budget confirmation → append-only
authorization + durable queue → independent Worker claim → real network-none Fake subject
container → actual final Workspace/change digests + sanitized JSONL/normalized Trace → separate
read-only/network-none hidden verifier → immutable bound result/Episode → refresh/restart reads.
Two Worker claimers take one attempt. A consumed attempt is never requeued or restarted, even if
nothing launched. The control API was also tested in an independent non-root readonly container
with no Docker socket/privilege and subprocess denial sentinels; Worker is a separate process.

Actual Fake solve changes one file, collects 6 normalized events and **3/3 independent checks**.
Wrong-workspace Fake claims success but makes no actual change; independent verification fails.
Subject and verifier timeout stay unverified. Real process crashes after claim, during a running
subject, and after an actual sealed result recover as interrupted/interrupted/recorded pass,
respectively, without a second launch. Active cancellation stops the real container; tampering
with actual Trace/Workspace bytes returns 409 with no substitute result.

## Verification

| Check | Result / evidence |
| --- | --- |
| Phase-2 API/queue contracts | 21 PASS: independent confirmation, frozen budgets, zero-cost mode, unauthorized real mode, concurrent/idempotent requests, permissions, drift/expiry, conservative lease recovery and append-only DB guards |
| Backend/compatibility | 195 PASS in final combined run; includes Phase-1 planning, legacy queue/executor safety, Episode readers, registry/harness, health/distribution/release and CI contracts |
| Existing Codex boundary | 15 PASS (35 deselected): argv, flags, secret-free diagnostics, timeout/cancellation and cleanup-failure handling; no live runtime doctor or model call |
| Real keyless Docker E2E | 9 PASS: solve, failed task, subject/verifier timeout, active cancel, and 3 actual process-crash points plus forged sealed verdict rejection; actual independent baseline-fail/oracle-pass fixture admission |
| Frontend | 202 PASS, including 8 new execution tests; typecheck and isolated production build PASS |
| Browser | 39 PASS on final built application / actual API / disposable DB / separate CLI Worker, Chromium 153.0.8010.12, 1440px; no mocked results, no external network; [receipt](browser.json) and screenshots below |
| Persistence restart | 4 PASS after restarting only the disposable DB/API: unchanged plan, authorization, result/Episode and consumed single attempt; [receipt](restart.json) |
| Static checks | Full Ruff lint/format and mypy (410 source files) PASS; whitespace PASS |
| Frozen offline regression | 73 PASS; two historical replay passes with five byte-identical outputs, zero external/model/Provider/Judge calls and no subject/verifier execution in this separate offline gate |
| Protection | Original UI-2 17 dirty changes / 1,494 file hashes, all 7 prior worktree HEAD/status/diff/files, 14 prior services / 437 readonly mounted files unchanged |

The counts are distinct within each row; reruns are not added. API/queue tests deny processes and
external HTTP at their boundary. Docker E2E executes trusted fixture code and independent verifiers;
it is separate from the offline gate, which executes neither. The first final browser restart
attempt raced readiness and stopped at connection refused; adding an explicit read-only readiness
wait passed. Initial path-contract and fixture-probe implementation failures were corrected before
final acceptance; no task/result expectation was relaxed. A [portable original failed-Workspace bundle](fake-rejected-bundle/manifest.json) contains actual
Trace, Workspace and separate verifier stdout/manifest. The existing strict Episode reader reproduced
its browser Episode identity byte-for-byte with zero execution; hidden verifier/oracle source is not
included. Final source identities and evidence
bindings are recorded in [acceptance.json](acceptance.json), with the protection receipt.

## Review screenshots

- [Queued after independent authorization](queued.png)
- [Real keyless Workspace + independent pass](verified-pass.png)
- [Self report rejected by independent verifier](verified-fail.png)
- [Tampered saved evidence rejected](tampered-evidence.png)

White/Cobalt and existing `/plans` hierarchy are retained. Visual inspection is local desktop QA;
mobile, other browsers, physical devices, full accessibility/human UAT and Grok final independent
reassessment were not performed.

## Limits and stopping point

Only server-approved Fake clamp fixtures run. No real task's production admission, serving model,
Codex executable/protocol, credential/Provider egress, token/USD hard cap, production Worker/DB
roles/operational topology, VM-grade isolation, retention/disk quota or production Compose acceptance
is claimed. Subject timeout is separate from verifier timeout and queue/preparation duration.
No existing Episode identities/results were rewritten. Complete export, public website cases and
Phase 3 remain outside this delivery. See [operator setup / first-real authorization prerequisites](../../LOCAL_EXECUTION.md).
After commit/push/Draft PR/exact-SHA CI handoff: **STOP**. Do not merge, deploy or start a real run.
