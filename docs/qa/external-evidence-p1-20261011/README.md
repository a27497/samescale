# External evidence P1 acceptance — 2026-10-11

Baseline `main@de55277b8cb0f931c9b57184aa5b68dadec0263c`, independent clean branch
`codex/external-evidence-p1-20261011`. This closes the corrupt-sibling list/UI blocker and the
manual first-intake setup blocker. It adds neither execution nor automatic source approval.
[Machine receipt](acceptance.json) binds tested source/test/workflow bytes.

## Repairs and observed results

P1-A: each validated record yields `AVAILABLE`; malformed record/Workspace/receipt yields its existing
identity, `CORRUPT`, and a fixed integrity reason, without source labels or acceptance from damaged
metadata. Missing records and known sensitive content are refused. Healthy sibling detail/export
remain usable; all-corrupt stores retain visible rows. A new app reads the same state after actual
restart. Corrupt detail/export and Verifier admission stay closed. No new Verifier process ran.
Global authentication, policy, ownership/read permissions, links/special files, structure/capacity
errors still reject access. A global refusal never becomes a warning or empty list.

UI concurrent reads use settled results. A transient list failure does not prevent a known healthy
detail from opening; a notice says the list is unavailable, not empty. Global denials still block
and clear the private view. Late route responses cannot overwrite the current record. A corrupt
export clears stale detail/acceptance. Damaged identities wrap on mobile.

P1-B: the [copyable host Quickstart](../../EXTERNAL_EVIDENCE_QUICKSTART.md), README entry, page guidance,
and `harnesslab external-evidence check` cover setup and distinct failure causes. The checker is
read-only: policy/path metadata only, no source content, record/pin qualification, writes, Agent,
Verifier, OAuth or account RPC. The authenticated API exposes the same safe report; no paths,
credentials or exception strings. Missing source locations warn but cannot strand healthy stored
records. [Four actual CLI cases](configuration-cli.json) distinguish missing policy, no approved
sources, unsafe policy permissions and configured metadata (even with corrupt stored records).

## Actual first-use journey

A new locked Python environment and `npm ci`/production build were used in this worktree. Only
`docker compose -p samescale-p1-20261011 up -d --wait postgres` created a new pinned PostgreSQL
container/volume/network on loopback 58691; Alembic migrated only that fresh test database.
A separate 0700 private evidence root/store and 0600 policy were created. A host API on loopback
58690 used a synthetic local operator credential. Its audit guard denied child processes, outbound
connections other than this database, and credential-file access. No rejection was recorded.
Standard Compose API forwarding/mount support was not added or claimed.

| Browser step | Observed result / remaining human action |
| --- | --- |
| Open the private product, follow external-evidence navigation | No evidence request before unlock; inline Quickstart explains CLI/configuration and host boundary |
| Missing policy, wrong operator, then empty policy | Targeted setup/permission errors; `NO_APPROVED_SOURCES` is distinct and import disabled |
| Make the policy 0644 | Visible `EVIDENCE_POLICY_PERMISSION`, no private view; operator fixes 0600 |
| Review approved historical source and its two final files | Existing bundle/Workspace pins compared to retained approved constants; human privacy/rights and pairing review remains required |
| Select source and explicit consent, import | Historical source identity/pins retained; original Episode remains NOT_VERIFIED; independent retained 5/5 is readable |
| Inspect coverage/diagnosis | Tool exits/actual route/model/usage/request count remain unknown; origin NOT_ATTESTED; synthetic incomplete source cannot borrow historical results |
| Download, retain digest separately, two guarded terminal replays | Same byte outputs, PASS for integrity, zero Agent/Verifier/external calls; no new task qualification |
| Controlled pin mismatch / sensitive fixture | Distinct safe 409 reasons and page guidance, no new record written |
| Mix healthy history and damaged synthetic Workspace | Healthy list/detail/export succeed; corrupt row has fixed reason, no verdict; damaged detail/export 409 |
| Restart only temporary API | Persistent mixed states retained; unfinished staging ignored, no new execution |
| Make store globally unsafe | Whole view refused, not per-row suppression |
| Damage the historical **stored test copy**, leave approved source frozen | Two corrupt rows visible, no empty/pass/detail fallback; mobile layout fits |

[Chromium receipt](browser.json): **26 checks PASS**, desktop 1440×1000 and mobile 390×844,
cached Chromium build 1243 / Playwright 1.58.2, actual browser against the new private host API.
Only same-origin loopback requests allowed; zero browser exceptions/external requests/execution
routes. Operator credential absent from browser storage. Export excludes raw sessions/commands,
credentials, hidden verifier/oracle and server paths. The stored-copy corruption is synthetic fault
injection, not a claim that the immutable historical source is damaged.

- [First-use guide](01-first-use-guide.png)
- [Policy permission](04-policy-permission.png)
- [Pin mismatch](05-pin-mismatch.png)
- [Sensitive rejection](06-sensitive-rejection.png)
- [Mixed records + unchanged NOT_VERIFIED / 5/5](09-mixed-records.png)
- [Corrupt detail refused](10-corrupt-detail.png)
- [Global storage refused](12-global-storage-refusal.png)
- [All records corrupt](13-all-corrupt.png) / [mobile](14-mobile.png)

## Regression, protection and limits

**162 backend compatibility cases PASS**: external evidence + new P1 boundaries, subscription denial,
SIWC contract and CI workflow contracts. **223 frontend tests PASS**, types and production build PASS.
Full Ruff/check/format PASS; mypy PASS (428 source files). Both Fast CI manifests include the new
bounded P1 suite. Exact pushed-head Push/PR Fast/Offline CI is a separate Git handoff observation.

[Historical offline regression](offline-regression.json): **73 checks PASS**, two identical replays
in a network namespace without routes, zero model/Provider/Judge/Agent/Verifier execution. Historical
Hook 5/5 is read, never rerun. There is no new approved real record: **FRESH_CASE_PENDING**.
Pattern rejection is not universal privacy detection. New source identity, pairing, manual privacy/IP
review, explicit approval, independent pins and local permission setup remain operator responsibilities.
Binary/large workspaces, private rollouts, auto collection, remote/multi-user intake and SIWC remain
outside scope. No automatic repair, reapproval or subscription takeover. **REAL_CODEX is CLOSED**.

[Protection receipt](protection.json): all **14 prior worktrees**, UI-2 **17 dirty entries**, **58 existing
containers**, **419 frozen files**, auth metadata and **364 website files/head/status** unchanged.
No auth content read, existing DB access/migration, deployment or website change. Only the new API
and isolated database/container/volume/network were removed. Earlier acceptance/evidence is unchanged.
Test-launch/fixture/type corrections and the initial mobile overflow failure are recorded in
`acceptance.json`; failing runs are not counted as passes. Stop after normal commit/push and Draft PR,
with exact-SHA CI; no merge or Phase 3.
