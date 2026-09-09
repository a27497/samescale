# Attribution Analyst

The Analyst investigates existing HarnessLab evidence without changing the authority of
deterministic verifiers, curated gold, Judges, or experiment statistics. The original Fake-only
one-shot path remains supported; the current vertical slice adds an explicit real decision backend,
PostgreSQL investigations, and a minimal Workbench entry. Implementation remains keyless-tested,
and the bounded real-provider vertical slice completed on 2026-09-09. This does not convert
Analyst output into higher-authority experiment evidence or authorize regression execution.

## Closed tool surface

The injected backend can request exactly six strict structured actions:

1. `query_runs` — bounded persisted run filters and safe run DTOs.
2. `compare_cells` — existing ExperimentReport statistics and Comparability semantics.
3. `inspect_trace` — digest-verified Normalized Trace events only.
4. `inspect_failure` — persisted outcome, taxonomy, and safe verifier/result facts.
5. `get_task_contract` — the plan-bound subject-visible task contract and safe identities.
6. `get_ablation` — declared AblationSpec plus persisted paired statistics and limitations.

There is no SQL, path, filesystem, shell, Python, browser, provider, queue, cancellation, Harness,
Judge, or execution tool. Every identifier is checked against the bound experiment. Native private
transcripts, hidden verifier code, and oracle content are unavailable.

## Graph and backend

`AttributionGraph` uses LangGraph 1.2.11 `StateGraph` directly. Its local decide/tool/finalize loop
is capped at 8 decision iterations and 12 tool calls. Reaching either bound creates a structured
`LIMIT_REACHED` report. No checkpoint service is used.

`FakeAnalystBackend` is deterministic and keyless. `RealAnalystBackend` uses the existing Registry
provider/model profile resolution and ProviderAdapter; there is no second LLM SDK, hard-coded model,
endpoint, credential value, automatic retry, or Fake fallback. The profile must be enabled and allow
automation. Its identity, request timeout, output-token limit, and any usable price snapshot are
frozen in the investigation; resume rejects profile/configuration drift.

The provider returns only `{"decision": BackendDecision}`: a tools, final, or abstain decision.
`ProviderRequest.output_json_schema` supplies the closed schema. Responses, Chat Completions, and
Messages adapters forward it; strict provider schemas request scalar factual leaf values rather than
arbitrary JSON objects. The host parses strict typed JSON, checks every tool against the bound scope,
and validates all report assertions and citations. No free-text response is treated as a decision.
For `deepseek-official`, Responses sends `text.format` with `type`, `name`, and `schema` only;
other Responses providers retain `strict=true`. This uses the existing Responses adapter.
Final decisions may include a review-only proposed regression plan. Persisted trace and task text
remain untrusted evidence and cannot expand the tool surface.

## Citations and claims

Evidence catalog entries use stable logical identities, never paths: `run:<id>`,
`trace:<run>#event:<ordinal>`, `task:<id>@<version>`, `cell:<experiment>:<cell>`, and
`ablation:<experiment>:<ablation>`.

Every `VERIFIED_FACT` draft contains one or more `FactAssertion` values: a logical evidence
reference, one of the six tool namespaces, a bounded field path, the `EQ` operator, and an expected
JSON value. Trusted host validation resolves each path against the cited `EvidenceEntry.data_by_tool`
namespace and compares canonical JSON exactly. Missing references, wrong tool namespaces, missing
paths, and contradictory values reject the draft.

The backend cannot supply `VERIFIED_FACT` prose or citations separately. After all assertions pass,
the host derives citations and renders the authoritative statement canonically from the assertions.
Interpretations remain natural-language `HYPOTHESIS` claims and must name evidence needed to verify
or falsify them. Without controlled ablation, causal interpretation remains a hypothesis. A
controlled ablation may report only its observed structured fields; evidence tier, sample size, and
Comparability limitations remain visible and controlling.

The evidence hierarchy remains `L0 > L1 > L2`; Analyst output cannot alter PASS/FAIL, scores,
ground truth, Judge output, or capability denominators.

### Finalization rejection and repair

Provider JSON-schema conformance is necessary but not sufficient for factual validity: an LLM can
still choose a real evidence reference with the wrong tool namespace, field path, or scalar value.
The host therefore validates every final draft after parsing. An invalid final draft is never
published or silently edited. The session records only an allowlisted `FinalizationRejectionCode`;
raw exception text and provider output are not persisted as repair feedback.

If decision budget remains, the session pauses. A later explicit `resume` supplies the bounded
rejection codes plus a host-generated `valid_fact_assertions` catalog containing exact scalar
`evidence_ref/tool/field_path/expected_value` candidates and the in-scope proposal identifiers. The
model may synthesize a new final decision, but the unchanged host validator still decides whether
it is accepted. If no decision budget remains, or a later draft still fails when the bound is
exhausted, the session fails closed as `INVALID_ATTRIBUTION`. This is bounded semantic recovery,
not an automatic provider retry and not a relaxation of evidence rules.

## Persistence, resume, and approval

The existing CLI `harnesslab analyst analyze` remains a keyless one-shot path that atomically writes
validated `report.json` and `report.md`. Investigation sessions instead persist in PostgreSQL's
single `analyst_session` table (migration `20260908_0007`). Session creation reads the bound scope,
freezes goal/profile/limits, and makes no model request.

Each `resume` advances at most one new decision, or finishes an already persisted pending decision.
The graph commits a decision reservation before ProviderAdapter invocation and a tool reservation
before each evidence read. Results and completed calls are committed individually. All mutations,
including proposal edits and approval, share a connection-owned PostgreSQL advisory lock; a second
concurrent resume is rejected. Disconnect releases the lock. This requires direct/session-pooled
PostgreSQL connections, not a transaction-pooling proxy.

Resume never resets the goal, scope, evidence, decisions, tools, request budget or recorded usage.
Completed calls are keyed by normalized arguments and reused across decisions. Pending batches
resume after completed calls; an interrupted ambiguous call is marked `INTERRUPTED` and is not
silently re-executed. Failed and timed-out calls also remain recorded and consume the limit. These
are cached observations within one investigation; a fresh investigation is needed to intentionally
re-read changed evidence or retry the exact same failed call. Tools time out after 10 seconds.

Metadata records provider/model/route, the profile's timeout/output cap, per-decision latency,
observed model and tokens, and estimated USD cost when a matching `ProviderPricing` snapshot and
usage are available. Historical subscription/non-price snapshots do not establish a dollar rate.
`request_count` counts observed ProviderAdapter invocations, not proof of remote delivery;
`request_budget_used` includes interrupted reservations. An unobservable invocation count, token,
latency or cost total stays null/unknown. The decision limit also bounds charged request attempts.
Failed decisions additionally persist `usage[].failure`: a bounded category, HTTP status when
observed, allowlisted response status, timeout phase/read stage, and incomplete reason when known.
`request_id_sha256` is the SHA-256 of the UTF-8 request ID (at most 300 characters), prefixed with
`sha256:`; compare it to the same digest of a provider-side ID for correlation. Raw request IDs,
headers, response bodies, exception messages/chains and unknown response-status text are excluded.
The public session view exposes these facts alongside `BACKEND_DECISION_FAILED`. Historical usage
without failure metadata remains readable; no old row is backfilled and no reservation is refunded.
A process loss between response and journal commit can leave usage unknown; it never refunds the
reservation. Real investigations require explicit immutable `spend_limits`: `provider_requests` (1–8 and no
higher than the decision limit), `output_tokens_per_request`, `input_bytes_per_request` (up to
256,000), `cumulative_tokens`, `timeout_seconds`, and optional positive `usd`. Output and timeout
ceilings cannot exceed the Registry profile defaults. The journal needs no new migration.
Existing real sessions without these limits remain readable but cannot invoke; no budget or old
usage is backfilled. Limits cannot be raised through resume, proposal edits or approval.

Before every ProviderAdapter invocation, the existing journal commits its request reservation plus
`CallResourceCeiling` and known-price cost reservation. Commit failure prevents invocation;
interruption/failure never refunds request budget. Observed usage stays separate from reservations.
Unknown or inconsistent token accounting blocks further calls; with a USD ceiling, unknown cost
also blocks. Reaching request, output, input-byte or timeout limits blocks another call. A token/USD
ceiling must accommodate both prior observed usage and the next complete worst-case reservation.

Input bytes mean the UTF-8 serialized host input envelope, including instructions and the strict
output schema, not just the evidence text. Bytes are never converted into guessed tokens. The
existing Registry model's KNOWN context window supplies the conservative input-token upper bound;
add the session output cap for the next total-token reservation. This deliberately over-reserves
when the context window includes output tokens. Missing context metadata is BLOCKED. The bound
assumes the selected route honors its declared context/output limits; an observed bound violation
blocks continuation. This is not a guarantee against a provider misbilling or ignoring its contract.
Pricing uses existing `ProviderPricing`, `PricingAvailability`, and budget cost arithmetic. A USD
ceiling requires KNOWN pricing matching the frozen route exactly; no inferred or subscription price.

Proposed regression plans specify an objective, in-scope tasks/cells, returned evidence references,
acceptance criteria, and bounded repeat count. Both model proposals and operator edits are host
validated. Approval requires the displayed session-scoped content digest and scope digest. Editing
content clears approval; a stale digest or another session's approval is rejected. Approvals carry
`execution_authorized: false`. They cannot enqueue experiments or invoke any external system.
The reviewer label is a local operator assertion, not authenticated identity or security acceptance.

## Workbench/API

The existing Workbench adds `/analyst`: choose an experiment, goal, Fake/real backend, registered
profile, and lower limits if desired. Create/load/refresh never invokes a model. Resume is explicit,
one step at a time; the page shows usage, tool outcomes, evidence, facts, hypotheses, limitations,
and a proposal editor with digest-bound approval. Saved sessions are listed per experiment (100
maximum); refreshing the page reopens persisted state.

Under `/api/workbench/analyst`:

- `POST /sessions`: create, keyless for both backends.
- `GET /sessions?experiment_id=...` and `GET /sessions/{id}`: persisted projections only.
- `POST /sessions/{id}/resume`: one bounded step; real requires `confirm_real: true` and server
  environment `HARNESSLAB_ANALYST_REAL_ENABLED=1`. The server default is disabled.
- `GET /sessions/{id}/preflight`: keyless REAL_AGENT_SMOKE snapshot; never reserves or invokes.
- `PUT /sessions/{id}/proposal`: validate and replace a review-only proposal; changed content
  invalidates approval.
- `POST /sessions/{id}/approval`: record reviewer label, exact `scope_digest` and `proposal_digest`.

All session responses pass a strict public DTO. Runtime configuration/credential values and raw
model responses are not returned or journaled. Known credential echoes and invalid decisions are
rejected. Errors expose bounded codes, not provider exception text.

## Keyless REAL_AGENT_SMOKE preflight

Workbench offers **Check smoke preflight** after creating a budgeted real session. The GET endpoint
returns READY/BLOCKED with reasons, session/preflight/scope/profile digests, provider/model/route,
credential/base-URL reference SET/MISSING status (never values), structured-output schema digest,
evidence scope and goal, all decision/tool/spend ceilings, next input bytes, context-token bound,
pricing basis, observed totals, request budget used and execution gates. READY means prepared for
separate authorization; it is not itself live evidence. The 2026-09-09 accepted live smoke is
recorded separately under `docs/evidence/REAL_AGENT_SMOKE_20260909.md`. The server flag may still be
off. Neither this snapshot nor a regression approval authorizes a call. Resume
rechecks the same bounds and current Registry/scope under the existing session lock.

For current operator-supplied metadata, optionally set `HARNESSLAB_REGISTRY_SPEND_METADATA` to a
repository-local JSON file with exactly these mappings:

- `model_context_windows`: existing Registry model ID → confirmed positive context-token upper
  bound. Confirm it applies to the selected route; do not guess it from text length. This fills the
  existing ModelDefinition context fields. Defaults remain NOT_AVAILABLE.
- `profile_pricing_references`: existing Registry profile ID → repository-local JSON path containing
  the existing `ProviderPricing` contract: exact `route_identity`, KNOWN `availability`, input/output
  USD per million tokens, per-request USD, and preferably a dated `evidence_reference`.

Use new current config files, never overwrite frozen `release/` pricing/evidence. Model context,
pricing snapshot, profile controls and endpoint configuration are frozen in the session identity;
changes block existing sessions rather than silently rebinding their budget. Pricing file content
changes invalidate the full frozen profile digest even when the path is unchanged. The metadata is
operator-provided planning evidence, not a live provider verification or permission grant.

Before a separately authorized smoke, supply the exact profile ID/digests, one existing experiment
and public goal, confirmed Registry context bound, request/tool/decision budgets, per-request
input/output/timeout ceilings, cumulative token ceiling and optional USD ceiling with matching
KNOWN pricing. Start with at most 3 decisions/3 requests/6 tools if appropriate; the token and USD
amounts depend on the chosen profile's confirmed bounds and prices and are not supplied by defaults.
Review the resulting preflight digest, then separately authorize Analyst-only calls. Preserve
localhost serving, server `HARNESSLAB_ANALYST_REAL_ENABLED=1`, and explicit per-step confirmation.

Keyless tests cover dynamic choices, bounds/reservations, unknown usage, failure/timeout/interruption,
resume without refunds/replay, missing old-session budgets, pricing/context/profile drift, public
preflight/API and frontend contracts. Fake remains deterministic. Fast CI includes these focused
contracts; no full A-K invocation is added. This batch performs no real Provider/Harness/Judge/Matrix
invocation. Security acceptance remains NOT_VERIFIED; F5 and the H-Lane gap remain untouched.

## Live acceptance — 2026-09-09

The accepted bounded session `analyst-0be376756a4f447bbdeeb44a58b292b5` reached `COMPLETED` after
4 provider decisions and 9 read-only tool calls over `core-real-matrix-v6`. Observed totals were
176,632 tokens and USD 0.09146104 under a USD 0.60 hard ceiling. The canonical report digest is
`sha256:1733eace25488c8e435e2fd1f7d5e6d1ae7c676a047259ab3edc3dd6315c19b1`; the validated proposal
digest is `sha256:24eec75a37c2695d39c1383b64208fa57ef56f3ef606873c75e3291aaa4b7820`. Approval is digest-bound
and `execution_authorized=false`.

The final session used task, run, cell-comparison, failure and ablation tools. It did not select
`inspect_trace`; separate real v3/v5 trajectories did execute `inspect_trace` and remain retained
as tool-selection evidence. The accepted report makes no Codex-vs-Claude superiority claim for
`core-java-deduplicate` because the relevant evidence tiers and infrastructure/budget losses do not
support a formal pairwise conclusion. See [the frozen live evidence](evidence/REAL_AGENT_SMOKE_20260909.md).
