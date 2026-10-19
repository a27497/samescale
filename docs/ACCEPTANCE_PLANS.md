# Acceptance Plan — P0-0 / P0-1 contract

## Audit and reuse

| Existing boundary | Reuse / gap |
| --- | --- |
| `CodeSnapshotPanel` / `code_snapshots.service.read` | Existing immutable `code-snapshot-v1` identity, full inventory/content/serialization checks; add detail-to-scope link. No upload, restoration or source execution during binding. |
| `ExternalEvidenceView` / `code-only-v1` | Keep external records, source approval, receipts, export and Replay unchanged. A scope is not an ExternalRecord. |
| `LocalPlansView` / `/api/local-plans` | Existing PostgreSQL plans bind admitted TaskStore packages and runtime configurations. They cannot represent natural-language scope. Keep `/plans`; add `/acceptance-plans`. |
| `local_plans.tasks.inspect_task` / TaskStore | Prior independently bound qualification/validation is required. Scope approval does not call import or create admission. |
| `local_operator` / `Private` | Reuse loopback host, same-origin, bearer, JSON and public-Demo refusal. Shared operator credential authenticates a workspace operator, not a named human. |
| `local_execution` / Worker | Authorization consumes local execution plan identities. New scope journal has no worker dispatch, model, shell, Docker or verifier operation. |
| Persistence | Reuse canonical SHA-256, bounded owned files, no-link checks and POSIX flock patterns. Separate opt-in store avoids schema migration and old evidence writes. |

## Product journey and state

Select a saved snapshot (or follow its detail link), unlock the private workspace, enter the original
Prompt, create a draft, review each source/ambiguity/candidate, save edits and decisions with reasons,
explicitly confirm the approved scope, then explicitly freeze. Reopen by ID after refresh/restart;
operator credentials must be entered again. Read all prior events and frozen versions. Revision starts
a new draft version and resets decisions, requiring renewed review. Original Prompt and snapshot
binding never change in this plan; a different original Prompt requires a new plan.

| State / operation | Contract |
| --- | --- |
| DRAFT / REVIEW or ADD | Editable; every mutation appends before/after reconstructable history with reason, authenticated operator class, server time, request identity and prior digest. |
| DRAFT → CONFIRMED | Explicit acknowledgement of scope only; at least one approved clause. Pending/rejected clauses are retained and excluded from failure criteria. |
| CONFIRMED → FROZEN | Separate explicit freeze acknowledgement. Neither state permits editing; freeze before starting a revision. |
| FROZEN → DRAFT v+1 | Preserve all original events and frozen bytes, link parent frozen digest, reset decisions. |
| Any state / execution | Always disabled; no admitted task, qualified/bound Verifier, receipt or business verdict is generated. |

All plans are `POST_DELIVERY_AUDIT`. Snapshot availability is checked at binding and every mutation;
historical scope remains readable with an explicit unavailable/changed binding warning if the snapshot
later becomes unreadable. All reads verify journal serialization, identity, chain and fixed authority.
The UI shows plan state, Verifier status and actual result separately. `NO_QUALIFIED_BOUND_VERIFIER`
means authoritative acceptance is unavailable; `NOT_RUN` means no actual result.

## Sources and finite extraction

`EXPLICIT_IN_PROMPT` is assigned only by a narrow full-sentence rule: the exact supported Chinese
commerce naming sentence (for example “给我做一个轻量电商系统，命名为 MiniShop”). It retains exact quote
substrings. Name and broad direction have source support; “轻量” has unresolved scope. Product list,
cart, order, inventory and payment are `SUGGESTED_ONLY`, never automatically approved requirements.
Negation, additional sentences and other unsupported wording fall back to `AMBIGUOUS` and manual
writing. This deliberately favors missed extraction over invented requirements; it is not semantic NLP.

Manual clauses begin `SUGGESTED_ONLY`. Approving a suggestion, resolving an ambiguity or changing an
explicit clause's text yields `USER_APPROVED_ADDITION`, preserving the original source, text and quote.
Only unchanged rule-extracted text can retain `EXPLICIT_IN_PROMPT`; the API does not accept client
source labels. Decisions are PENDING / APPROVED / REJECTED. Every decision/change requires a reason;
server review times and event snapshots preserve confirmation history. An approved clause is scope,
not a qualified check. Uncovered requirements remain explicit and are never inferred from source code.

`source` records provenance, not approval in the selected version. REVISE preserves that provenance
(including `USER_APPROVED_ADDITION`), resets every `decision` to PENDING and clears the new version's
review time/reason. The UI labels inherited additions as “历史批准的新增范围（本版本未批准）” until
renewed approval, and shows the original candidate source separately. Only `decision=APPROVED`
labels an addition “本版本已批准的新增范围” and includes it in the version's approved count. Review
times/reasons describe the selected event's version; earlier approvals remain in their original
history events. Selecting v1 history shows v1's decision/time, never v2's. No event rewriting or
extraction-rule expansion is involved; unsupported Prompts still require manual fallback.

## Persistence, privacy and limits

Configure `HARNESSLAB_ACCEPTANCE_PLAN_STORE` as a new canonical, owned 0700 directory **outside**
repository, evidence, task, runtime and artifact roots, plus the existing private evidence policy and
operator token. For a private host API, retain the existing snapshot setup described in
[CodeSnapshot setup](CODE_SNAPSHOTS.md), then set, for example:

```sh
export HARNESSLAB_ACCEPTANCE_PLAN_STORE=/absolute/private/acceptance-plans
# Existing HARNESSLAB_EXTERNAL_EVIDENCE_POLICY and operator token remain server-side.
# Start the private host API using the existing developer setup; no Worker is needed.
```

The directory must be newly dedicated or an existing owned 0700 scope store; do not point it at
old evidence or a running deployment's data. Use `/acceptance-plans` → unlock → select a saved
snapshot → enter Prompt → save draft. Use the per-item reason/decision controls before confirmation.
A fresh API process reading the same store restores the exact journal without a database.
The store contains 0400 canonical JSON events, published atomically after fsync and
serialized with flock across processes. A stale expected digest is rejected (409); an identical request
ID/payload returns the original event; reuse with different payload is rejected. No database migration.
At most 1,000 plans, 256 events/plan, 64 clauses/plan, 16,000 Prompt characters, 96KB request body,
512KB event and 128MB store; capacity errors preserve prior events. Back up the entire private store.
Hashes detect changed bytes/links, not malicious privileged restoration of an older whole store or
human authorship. No distributed storage, multi-user RBAC or globally exactly-once execution claim.

Prompt and review text stay in memory and private server storage; never use URL query text, browser
storage, public Demo or request logging. API errors do not reflect bodies and all scope responses use
`Cache-Control: no-store`. Known credential patterns reuse the existing input safety filter (not
universal DLP). Do not paste credentials. Route URLs contain opaque IDs only (snapshot selector may
use the snapshot ID). Production hosting, retention policies and public sharing are outside P0-1.

## Eight verifiable scenarios

1. MiniShop sentence: name/direction have original quotes; five feature suggestions remain excluded.
2. Unsupported/negated Prompt: ambiguous manual fallback, no invented explicit requirements.
3. Edit/approve a suggestion or explicit clause: addition identity plus original suggestion/quote,
   before/after text, reason and server time survive reload; rejection/pending remain excluded.
4. Confirm then freeze; edits refused; revision creates v2 with pending review; v1 bytes remain intact.
5. Repeated identical submission is idempotent; differing payload reuse and concurrent stale writers
   fail; refreshed/restarted API reads the same digest and version history.
6. Missing, wrong-content-identity or corrupted snapshot fails binding without writing snapshot or
   scope; later corruption leaves historical scope inspectable but prevents new mutations.
7. Missing/incorrect operator, foreign origin, public Demo and unsafe/oversized input fail closed
   without reflecting Prompt; denied requests cannot execute or create admission.
8. Every state separates scope confirmation, missing qualified Verifier and NOT_RUN; attempts to
   execute are rejected. Test guards forbid Provider, subprocess, subject and physical Verifier calls.
