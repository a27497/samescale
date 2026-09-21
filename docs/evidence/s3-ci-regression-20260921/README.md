# Phase S3 — CI Regression Integration

2026-09-21. Local exact staged-tree acceptance PASS; GitHub SHA acceptance pending.

## Contract

The ordinary push/pull_request [workflow](../../../.github/workflows/offline-regression.yml)
and local verification use exactly the same entry:

```bash
uv sync --locked
bash scripts/ci_s3.sh /tmp/s3-regression-new
```

Linux, a provisioned locked `.venv`, and passwordless `sudo`, `unshare`, `setpriv` are required.
Dependency provisioning and GitHub checkout/log transport use the network outside the test
boundary. Regression runs in a fresh network namespace with only down loopback, no routes,
a clean environment and temporary HOME, as the original non-root user with no-new-privileges.
Missing isolation fails closed; there is no online fallback. The S2 replay subprocess additionally
denies socket/process operations with its audit hook. No credentials, database, Docker, subject CLI,
Provider/model/Claude/Judge or real benchmark workflow is used. Recorded commands and verifier code
are data only and are never executed.

[Runner](../../../scripts/verify_s3_regression.py) pins the original S2 archive and inputs digest,
checks the five committed S2 golden outputs, extracts only the validated archive, runs two independent
CLI replays, and requires both complete output inventories to match every frozen byte digest.
It then runs the S2 and S3 adversarial suites, requiring nonzero collection, critical test families,
no failures/errors/skips, and a successful test process. PASS is written only after every gate.
The workflow fails on a nonzero exit and records a SHA-bound result, JUnit and replay receipts in its Actions log and job summary.
The complete JSON/Markdown replay outputs are already pinned in the repository; CI records their
verified digests. No artifact quota or artifact deletion is required.
Frozen anchors must be reviewed explicitly for intentional contract changes; never regenerate them
to repair a failing CI run.

| Regression | Fail-closed evidence |
| --- | --- |
| Evidence/digest drift | Pinned ZIP/inputs, complete file inventory and per-file/tree digests; missing/tampered/extra/path/symlink cases |
| Replay inconsistency | Manifest/receipt/projection/verifier cross-checks, two replay passes, full golden JSON/Markdown/output inventory |
| Trace/schema/parser | Native→normalized equality; injected Codex and Claude parser drift, unsupported schema and terminal/ordinal cases |
| Changed-files attribution | Baseline/output reconstruction, declared changed-path contradictions, frozen read/edit/shell-mention distinction |
| Failure taxonomy | Frozen timeout/NOT_VERIFIED/NOT_RUN semantics, inconsistent taxonomy, altered output rejected even if self-consistent |
| Acceptance integrity | Missing/zero/skipped/failed/error test evidence rejected; mandatory ordinary CI entry with no secrets |

S2 [final report](../s2-offline-replay-20260921/README.md) and all original bundle bytes are retained.
S1 remains **PARTIAL REAL BENCHMARK / BLOCKED**: 2/16 cells executed, one Codex recorded verified pass,
one Claude timeout / NOT_VERIFIED with verifier NOT_RUN, 14 NOT_RUN. No ability ranking, full
configuration comparison, paired efficiency result or Harness causal attribution is supported.
Offline regression validates saved facts and implementation consistency, not a fresh model or verifier run.

## Initial observations

[First preflight](initial-local-result.json) failed closed because proc/sysfs in this container did
not reflect the new namespace as expected. The corrected check queries the namespace's kernel
interface flags; no test/model execution occurred before the failed boundary check.
[First complete local check](local-result-64.json): 64 tests passed, two byte-identical replay passes.
Final isolated tree: [65 passed](local-pytest.txt), [result](local-result.json),
[JUnit](local-pytest.xml). Both CLI passes match every frozen output digest.
[Ruff](ruff.txt) and [format](format.txt) passed; [mypy](mypy.txt) passed for 368 source files.
The [initial mypy failure](initial-mypy.txt) was a test import that was not explicitly exported;
the test now imports its parser from the defining module. Final regression includes that correction.
[Implementation pins](implementation-sha256.json) identify the exact staged implementation.
[Preservation](preservation.json): 2083 original files unchanged; only S3 additions to the two live
scope documents. All unrelated dirty work and historical evidence retained.

S3 only. No S4, PR, main merge or deployment.

The first GitHub attempt [35642692424](https://github.com/a27497/samescale/actions/runs/35642692424)
ran the offline gate successfully ([65-test receipt](initial-github-regression-result.json)), but
artifact storage quota rejected the upload, so the whole workflow correctly remained FAILED.
[Failure record](artifact-quota-failure.json) and [job metadata](initial-github-run.json) are retained.
The successor records the same evidence in Actions logs/summary, with no historical artifact deletion.

Quota-independent successor: [65 local tests PASS](successor-local-pytest.txt),
[result](successor-local-result.json), [final implementation pins](implementation-final-sha256.json),
[summary step check](summary-step-check.json). GitHub successor acceptance pending.
