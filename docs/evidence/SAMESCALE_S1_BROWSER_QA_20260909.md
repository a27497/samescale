# SameScale S1 Browser QA — 2026-09-09

This is a dated local verification record for the S1 source delivered in the same commit.
It is not a new model campaign or evidence of engineering/model performance. Live milestone state
belongs to [Current Milestone](../../CURRENT_MILESTONE.md).

## Environment and inputs

- Built Vue application served by the existing `harnesslab serve` command on loopback port 8011.
- Chromium 151.0.7922.34, Playwright 1.62.0 from a temporary uv tool environment; repository Python
  and npm dependencies/locks were unchanged.
- Desktop 1440 × 1000 and mobile viewport 390 × 844; reduced motion enabled.
- Offline and historical examples used the actual local API, including the frozen-file digest checks.
- Current Fake sessions used the actual API and a new disposable PostgreSQL 18 container migrated
  through `20260908_0007`. The synthetic `samescale-s1-browser-fixture` experiment was built with
  the existing `basic_spec`/`build_experiment_plan`/`enqueue_plan` test helpers. Its single queued
  task was never executed; a `queued` fact is not a failure result or a pass.
- The server ran with `HARNESSLAB_ANALYST_REAL_ENABLED=0`. No Real decision, Harness, Judge,
  worker, or production service was launched. Approval used a visibly unverified local label.

## Observed checks

| Interaction | Observation |
| --- | --- |
| `/` entry | Redirected to `/analyst`; SameScale document title; primary investigation navigation; advanced area collapsed |
| Keyboard offline launch | Enter ran the graph; report received focus; 2 decisions, 2 tools, 0 Provider requests |
| Report navigation | Section controls focused their headings; citation revealed and focused exact tool data/digest; return control focused the originating citation |
| Historical example | Actual frozen report loaded with provenance and trace/limit caveats; citations resolved; no resume/approval controls |
| Injected historical failure | Browser interception returned HTTP 409; old report disappeared; no Fake fallback; explicit retry used the actual API and recovered |
| Persisted Fake | Created a new session without invoking a model; first step saved; full browser reload retained Decisions 1/8; second step reached COMPLETED with a report |
| Proposal review | Saved through actual API; approval recorded `execution_authorized=false`; editing the objective disabled approval until saving the changed proposal |
| Legacy `/overview` | Direct route remained accessible; advanced navigation automatically expanded |
| Mobile | Menu and Escape worked; report/citations and current-session setup remained usable; Real creation stayed disabled without an explicit token budget |
| Layout/runtime | No document horizontal overflow in tested desktop/mobile home, report, or session states; no uncaught page exceptions |

The initial approval exercise used parentheses in its reviewer label and was rejected by the
existing backend pattern. S1 now shows the permitted characters and disables invalid submissions;
the backend contract is unchanged. A frontend regression covers the invalid and valid labels.
An initial browser assertion also raced an asynchronous create response when an older session was
already visible; the assertion was corrected to wait for the new session's zero decision count.
The final browser run passed all seven grouped checks.

This is Chromium desktop/mobile-viewport QA, not physical-device, Safari, Firefox, or independent
screen-reader certification. Live Real/paid execution was intentionally NOT_RUN; keyless unit and
PostgreSQL checks cover the preserved confirmation, failure, scope, budget, and approval contracts.

## Visual evidence

The screenshots were inspected for hierarchy, content clipping, and readability. They contain only
synthetic offline data; they do not replace the behavioral assertions above.

[Desktop entry](samescale-s1/desktop-entry.png) ·
[Desktop report](samescale-s1/desktop-report.png) ·
[Mobile report](samescale-s1/mobile-report.png)

Local development artifacts are retained under `artifacts/samescale-s1/`: `browser_qa.py`,
`browser.log`, `results.json`, build/test logs, and additional screenshots. This ignored directory
is local scratch evidence, not part of the distributed package or a portable prerequisite.
The dated screenshots above are committed with this record.
