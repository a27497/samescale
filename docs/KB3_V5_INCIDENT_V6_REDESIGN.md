# K-B3 V5 Incident Closure and V6 Bailian Redesign

V5 Attempt 1 is classified as `HARD_STOPPED_METHODOLOGY_SCHEDULING_DRIFT`.
The authoritative PostgreSQL queue contains 630 logical slots, of which 259 were acquired:
216 capability passes, 43 capability failures, zero infrastructure failures, and 371
unacquired slots. The schema-v1 queue drained cells in cell-major `slot_order`. No one
`(task_id, repeat_index)` block acquired all seven cells, so the formal salvage count is zero.
The append-only incident record is
`release/kb3-v5-attempt1-scheduling-incident.json`; the old rows, manifests, runtime tree,
ledger, and timestamps remain unchanged.

V6 is a new `core-real-matrix-v6` methodology-v2 experiment. It retains the 18-task Core
corpus, seven cells, five repeats, deterministic verifier authority, GPT Direct/Codex pairing,
and Codex medium/high ablation. Both Qwen subject cells move to existing Alibaba Bailian
registry profiles. No V6 subject route uses OpenCode.

The plan is built by `build_v6_plan()` and contains 90 deterministic task/repeat blocks. The
persisted plan owns block identities, seeded cell orders, provider availability, and all 630
slot identities. PostgreSQL persists the schedule as schema 2 plus the reordered `slot_order`;
claims therefore follow the frozen block schedule rather than schema-v1 cell order.

`BlockAwareDispatcher` is the production V6 coordinator. A later block may begin only after
all seven slots of the current block are durably represented, but it does not wait for all
seven to finish. Fixed global, lane, and provider caps are enforced before exact-slot claims.
Terminal slots are represented on resume and are never reclaimed. Live leases owned by another
coordinator stop dispatch. Every executable binding must present the frozen cell binding digest,
which prevents provider, model, Harness, reasoning, or credential-reference substitution.

The deterministic 630-slot simulation qualified concurrency 4 and concurrency 6. Both pass
schedule, queue, isolation, replay, cleanup, cancellation, and 8-vCPU/16-GiB resource checks.
Concurrency 6 is frozen because it is the faster passing profile, with maximum two Harness
workers, four Direct workers, two calls per provider family, and one Judge call.
The scheduler decisions use the production block coordinator, while fake-provider timing and
resource peaks are deterministic discrete-event models rather than observed production host
telemetry. Host telemetry confirmation therefore remains a prerequisite for canary dispatch.

Direct HTTP adapters use campaign-scoped clients keyed by exact route identity and credential
reference. Pools are bounded to two connections per key, disable redirects and environment
proxy inheritance, preserve per-request timeouts, and close deterministically. No semantic retry
is introduced. Stable Docker preflight and verifier-source caching were not added: both require
broader lifecycle plumbing to prove that endpoint drift and writable verifier state cannot be
hidden. Workspaces and subject containers remain per trial.

The preferred Judge candidate is Alibaba-hosted GLM-5.2 because it is independent of all V6
subject model families. Alibaba-hosted DeepSeek V4 Pro is frozen as a second candidate but
overlaps a subject family. Both pass the local OpenAI-compatible transport and strict public JSON
contract, but route identity, observed model, and real schema adherence still require the
preregistered one-call Judge canary. No OpenCode Judge route is retained.

The canary is preregistered but not authorized: one Direct Qwen call, one Claude+Qwen call, and
one preferred Judge call, with no retries. Exact public China (Beijing) base rates are recorded
in `release/core-real-matrix-v6-control.json`; account applicability, endpoint fingerprints,
credentials, deployed model IDs, promotions, tax/FX treatment, and a new V6 spend authorization
remain operator inputs. No canary or Matrix acquisition is started by this phase.
