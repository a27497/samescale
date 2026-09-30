# SameScale targeted UAT and Git closeout — 2026-09-30

[Latest independent Grok result](grok-targeted-uat.json) is **TARGETED_UAT=PASS**:
M1/M2/M3/N1/N2/P1 **PASS / CLOSED**, **NEW REGRESSION=NONE**. This result was supplied by
the user; no external report was fetched. [Acceptance summary](summary.json).

Public Demo `public-demo-20260930-9569db12e23a` remains **FIXTURE_OFFLINE / read-only**.
Offline Fake can run bounded computation without persistence or Provider/network calls.
Persistent Analyst sessions remain forbidden publicly and available in local/private workspaces.
Frozen release `REAL_JUDGE_SMOKE=VERIFIED`; current JudgeLab registry `NOT_RUN`.
These are distinct evidence scopes. No paid or real model execution was performed.

[Backend full](backend-public.json): **1722 PASS**, 0 failure/error/skip, reused from the same
unchanged source and isolated disposable migrated database; [original console result](backend-full.txt).
Frontend full **99 PASS**, typecheck and production build **PASS** were rerun during Git closeout.
Full-repository Ruff check/format (**748 files**) and mypy src/tests/scripts (**388 files**) **PASS**.
[Offline regression](offline-result.json): **73 PASS**, two identical replay passes, external /
Provider / model / Judge calls **0**. [Source inventory](source-inventory.json) binds delivered code.

[Evidence integrity](integrity-public.json): **451 protected files BEFORE == AFTER** during
full-suite acceptance. [Preservation](preservation.json): QA DB **23 tables / 68 rows**, Demo
response/identity/digest and service/env/Serve hashes unchanged. Disposable test DB removed.
Committed frozen evidence and the external Demo bundle retain original bytes and identities.

[Public Demo Gate](public-demo-gate.json): **12/12 PASS**, scope **Tailnet only**. A loopback
12/12 gate was additionally rerun during Git closeout. [Desktop/mobile browser acceptance](browser-public.json):
**58/58 PASS**, 1365×900 and 390×844, no page-script errors or horizontal overflow; screenshots
are in `browser/`. Session creation still returns `403 PUBLIC_DEMO_READ_ONLY`; only bounded
Offline Fake computation POSTs occur in this acceptance. Grok Tailnet QA is now user-reported verified.
**Public internet / sslip.io / trusted TLS remain NOT_VERIFIED**; Tailnet access is not public deployment.

[Git audit and exclusions](git-audit.json) records every original untracked file excluded from Git.
Raw service/Serve configuration, internal addresses, operator paths, JUnit, duplicate logs,
failed selector attempts and temporary scripts are preserved privately outside the repository.
Public successor receipts retain relevant results and original-receipt SHA256 references.
They do not replace or rewrite already committed frozen evidence. No new feature or deployment work.
