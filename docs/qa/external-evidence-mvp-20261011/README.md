# External saved Codex evidence MVP acceptance — 2026-10-11

Base `main@5c363e245c25ebe3fbf6784f95952e32452c6878`; independent branch/worktree
`codex/external-codex-evidence-20261011`. This delivery is private opt-in saved evidence intake,
independent Workspace verification and offline replay. No Agent is rerun. REAL_CODEX stays closed;
SIWC/account/authentication, Phase 3, deployment, merge and existing database migration are excluded.

The explicitly approved saved real source is
[the immutable 2026-10-07 native-hook case](../../evidence/real-codex-native-hook-20261007/README.md).
Its 12 events, original unverified source classification / NOT_VERIFIED Episode, final two-file
Workspace and **historical independent 5/5** are imported through the actual private API and browser.
The original source files and verifier result are unchanged; the saved 5/5 is not a new Agent or
Verifier run. Missing tool exits, actual model/route/usage/cost and origin authenticity stay unknown.
Controlled partial hooks, provided JSONL streams and task/admission/Workspace failures are synthetic.

Acceptance:

- **120 focused cases PASS**: 32 external intake/privacy/integrity cases, one Docker acceptance case
  and existing Hook/Episode/Verifier/CI-contract cases. A later pre-write credential-pattern guard
  was additionally covered by the same 32 external cases.
- The Docker case observes five actual network-disabled Verifier invocations in its final batch:
  trusted baseline-fail/oracle-pass admission; separately supplied baseline fails 3 checks, oracle
  passes 3, forced timeout remains NOT_VERIFIED/zero checks. All supplied runs are **synthetic**;
  no Codex/Subject/model runs. Original records are byte-preserved; completed repetition is idempotent,
  and an interrupted attempt refuses retry.
- **208 compatibility cases PASS** against a new migrated disposable tmpfs PostgreSQL; the only new
  database/container was removed. Fake planning/Worker/control, subscription denial, SIWC offline
  contracts, packaging and lifecycle regressions pass. No existing database is accessed/migrated.
- **208 frontend tests PASS**, type/build PASS. **15 actual Chromium checks PASS**, including explicit
  consent, real history vs synthetic, 5/5 vs original NOT_VERIFIED, unknown fields, download, credentials
  absent from storage/export, reload, mobile width, integrity failure and zero external/browser errors.
- **73 existing offline regression cases PASS** in an isolated network namespace. Two historical runs
  replay twice into identical golden outputs; zero external/Provider/model/Judge calls and no Subject
  or Verifier execution. The new exported record also replays twice into identical outputs under the
  network/process audit guard, with its digest retained outside the export.
- Full Ruff/format and mypy (**427 source files**) PASS. CI adds the new offline/API and UI suites to
  both existing Fast CI variants without changing their isolation or required checks.

Initial development failures were corrected and retained as limitations of those initial runs:
missing frontend locale import caused zero collection/build failure; an unattached unit form needed
explicit submit rather than click; an oracle fixture directory collided with the reserved hidden-asset
name; Fast CI mirror/expected-list contracts initially differed; inserting navigation before the
existing first item broke its test. These are not counted as passes. The final suites above passed.
Original historical Episode `unverified` was initially mistaken for the declared archival classification;
the importer now retains original classification independently and rejects known synthetic relabeling.

Final display correction after initial Head `65cbb03f48de5bdb69e5549010d305c5021a6dad`: a provided
JSONL/partial-hook record with no original Episode now explicitly says none was supplied, rather than
using the retained-Episode caption. **209 frontend cases**, including the new absence case, and build
pass. [Supplemental source-bound receipt](episode-absence.json). Initial acceptance/source hashes and
browser observations above retain their original scope; backend evidence and stored verdicts are unchanged.

[Machine-readable acceptance](acceptance.json) · [Browser receipt](browser.json) ·
[Desktop](historical-real.png) · [Mobile](mobile.png) · [Unverified fixture](unverified.png).
The [browser script](browser-check.cjs) requires a separately prepared disposable evidence store,
loopback URL and locally installed Playwright via environment; its tamper operation affects only that
explicit test store. No browser or verifier permissions are added to a public API. Git/CI facts are
reported separately after normal push and a **Draft** PR. No merge is authorized. STOP at handoff.
