# D1 Configuration Decision — frozen protocol

The user selected the historical S1 **Official Codex** configuration as current and the
historical S1 **Claude Code** configuration as candidate. The two real DEVELOPMENT tasks are
LectureLens B (`lecturelens-analysis-progress-stream-reconnect@1.0.0`) and A
(`lecturelens-embedded-subtitle-language-metadata@1.0.1`). The original source commits,
starting workspace, task packages, independent verifier, oracle, prompt and configuration
identities are inherited byte for byte from the qualified S1 completion freeze. S1 runs are
historical references and do not count as D1 trials.

[`campaign.json`](campaign.json) binds the exact 20 trial identities, task and configuration
revisions, invocation controls, image and source digests, fixed ordering, failure taxonomy and
decision vocabulary. [`phase-authorization.json`](phase-authorization.json) binds one execution
identity per trial. [`operator.py`](operator.py) checks those identities before each dispatch and
records immutable per-trial output outside the repository. A temporary copy of the freeze and
operator passed keyless verification before the official files were written. The final freeze
passed the same verification; source/credential value exposure scan passed without persisting
credential values.

The fixed run contract is **2 configurations × 2 tasks × 5 trials = 20**. Each trial starts
from the same task package workspace and has one attempt, zero operator retries, no resume,
fallback or Judge, one subject at a time, a 600-second subject timeout, and a 300-second
independent verifier timeout. The 6000 output-token value is a declaration, not a cumulative
session hard cap. Monetary cost and a session token hard cap are `NOT_AVAILABLE`; observed
usage/cost must not be inferred from the declaration. A verified task failure remains in the
series; an infrastructure, protocol, authentication, control, evidence or cleanup failure
stops the series with the remaining trials marked `NOT_RUN`.

The comparison is limited to these tasks, versions, environment, budget and configurations.
Model, Provider, Harness, prompt and tool differences prevent a Harness-causal conclusion.
Only independent verifier outcomes count as verified success. The frozen vocabulary is
`KEEP CURRENT`, `SWITCH SUPPORTED BY CURRENT EVIDENCE`, `INSUFFICIENT EVIDENCE`, or
`INVALID COMPARISON`; no global ranking is authorized.

Historical S1 operator modules and 67 source files remain in the original, separate
integration worktree and are hash-bound in this freeze. The D1 operator must run from that
checkout with `PYTHONPATH=src:.`; it refuses source drift. Full per-trial bundles remain under
`/home/dev/artifacts/samescale-d1-20260923/`. This is a local campaign dependency; the frozen
protocol is inspectable here, while the historical operator tree is not redistributed by this
candidate branch.

Status at freeze: **20 planned; 0 D1 runs executed.** Later receipts must be added without
editing the frozen files or counting historical S1 runs as D1 trials.

## Run result and stopping point

The frozen schedule started two trials and stopped at the predeclared hard-failure boundary.
[Machine-readable result](result.json) is rebuilt by `uv run --locked python scripts/report_d1.py
--check` from the original external trial bundles. Compact, digest-bound [trial 00](receipts/00.json)
and [trial 01](receipts/01.json) receipts are copied here; no source result was rewritten.

| Trial | Outcome | Independent verifier | Subject duration |
| --- | --- | --- | --- |
| B × Official Codex, trial 1 | `verified_pass` | 20/20 checks | 224.417 s |
| B × Claude Code, trial 1 | `harness_error / NOT_VERIFIED` | `NOT_RUN` | 601.327 s |

The remaining **18/20 planned trials are `NOT_RUN`**. The [acceptance audit](ACCEPTANCE_AUDIT.md)
closes the bounded D1 decision as **COMPLETE / `INSUFFICIENT EVIDENCE`** with every planned slot
accounted for; the 20-run campaign itself was not fully executed. This decision does not support a switch,
ranking, or causal Model/Harness claim. Consistency, a five-trial median and comparable steps per
verified success are `NOT_VERIFIED`; observed cost per verified success is `NOT_AVAILABLE`.

The Claude process reached the frozen 600-second subject timeout. It produced no independently
verified workspace outcome; 0 changed files and unknown usage are retained. The observed boundary
belongs to the evaluation contract. Why the session did not finish is `UNKNOWN`; Model, Harness
and Tool failure are `NOT_ESTABLISHED`. The original cleanup receipt remains `FAIL` because five
empty scratch directories remained. A separate [post-stop cleanup](post-stop-cleanup.json) removed
only those empty directories, with **0 files deleted**, no remaining campaign container/network,
and original result/receipt bytes unchanged. No Agent retry, verifier run, or changed protocol.

The exact freeze commit `6792663ffa18420d16e757317d9e343fe9505b9a` passed
[Fast CI](https://github.com/a27497/samescale/actions/runs/35819575364) and
[Offline CI](https://github.com/a27497/samescale/actions/runs/35819575362).
Those keyless checks verify the product baseline; they do not fill D1's 18 missing trials.
The original result's `BLOCKED_BEFORE_D1_ACCEPTANCE` label remains unchanged as a historical
stopping record. The later acceptance audit separates that hard-stop fact from decision closeout;
it did not dispatch more trials or revise any result. D2 uses separate historical natural evidence.
