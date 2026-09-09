# First-application technical closeout, 2026-09-09

This delivery integrates the existing Phase L and real Analyst work on main baseline
`3335668f4f11e384a9f99fb0a8692f07d8937902`. Its exact delivery identity is the containing Git commit;
check that commit's CI instead of reusing old main/tag results. Human ownership and complete
runtime restoration are not accepted by this report.

## Corrections

1. Reports previously hardcoded global 8/12 limits even when a session froze lower values. The
   regression first failed for 2/3 and 4/1 limits. Effective limits now travel from graph state into
   report metadata and Markdown. Old report defaults and the accepted v6 digest remain unchanged.
2. A real browser rehearsal collected 104 evidence entries and the default UI submitted all of
   them, exceeding the proposal's 100-reference contract (HTTP 422). The UI now defaults to cited
   evidence where available and exposes the selected bounded references. The backend cap is retained.
3. The same browser run found horizontal overflow from long identifiers and form controls. Scoped
   Analyst styles constrain controls and wrap text; the evidence catalog is collapsible. Desktop
   and mobile were checked after these changes, with no overflow.
4. The blueprint now reflects HL-BLUEPRINT-2026-09-05's first-application route. The historical
   phase map remains historical. [Application material](../FIRST_APPLICATION.md) supplies a bounded
   demo and capability draft without asserting unverified personal authorship.

## Verification

- Full backend: **1279 passed in 785.07 seconds**, zero failed/skipped, fresh isolated PostgreSQL.
- Frontend: **43 passed**; TypeScript check and Vite production build passed.
- Ruff lint/format, mypy, and Git whitespace checks passed.
- Browser: real HTTP against the local API and cloned V6 database; Fake completed with 2 decisions,
  6 tools and zero provider requests. Save, review-only approve, reload and retained state passed.
  Viewports: 1440x1000 and 390x844, no page errors or horizontal overflow.
- Frozen real-smoke artifact hashes, final-report structured facts, original live-output match,
  proposal/approval binding, and usage sums passed. No frozen output was overwritten.

Commands: locked `pytest -q` for the entire backend; `npm test` and `npm run build` in frontend;
locked Ruff/mypy plus `git diff --check`. Local raw logs, JUnit XML, browser assertions and screenshots
are in `/home/dev/harnesslab-first-application-20260909/`. Original historical real artifacts remain
under `docs/evidence/real-agent-smoke-v6/` with a separate effective-limit correction note.

The full backend run exercised the final Python change. Frontend-only reference/layout fixes were
subsequently checked with the complete frontend suite, type/build checks and the browser rehearsal.

## Runtime evidence limitation discovered during setup

The inspected default DB has 1404 runs and no Analyst sessions; the integration DB has 2034 runs
and no Analyst sessions. The accepted real session was also absent from the inspected provider
compatibility database. Its frozen files remain valid artifacts, but its persisted database row is
not currently recovered. The source and timing of that discrepancy are **NOT_VERIFIED**.

The default mixed historical experiment list also rejects a legacy plan identity; V6 itself is
readable. The demonstration has a separate database copy containing V6 only. Source databases and
on-disk evidence are unchanged. Demo row statistics do not redefine the accepted release dataset.

The demonstration is therefore **frozen real evidence review plus separate Fake interaction**, not
a claim of new real execution or original-session restoration. The automated reviewer label in the
demo is explicitly `automated-keyless-rehearsal`, not human ownership evidence.

## Remaining boundaries

Human A/B/C ownership checkpoints remain pending. F5 orphan-process cancellation, H-Lane protected
files, authenticated reviewer identity, and security acceptance remain limitations. No paid campaign,
Matrix rerun, production deployment, new release tag, public repository conversion, or external
application submission was performed as part of this technical closeout.
