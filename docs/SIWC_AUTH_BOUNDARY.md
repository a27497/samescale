# SIWC applicability and trusted auth preparation — Phase 2.6

**OFFLINE ONLY / REAL_CODEX CLOSED.** Original Phase-2.6 acceptance used
main@1061ddd7b13288f27e6d0545c8d6f6467278073b. PR #11 subsequently merged the bounded source
license at main@ffeee1b366baa61f303ebf546f0287aae3ac9be1; it is integrated into Phase-2.6 source.
Final Git closeout now authorizes a readiness correction and PR #10 merge after exact-SHA acceptance,
not actual OAuth/account/model/quota RPC, credential read/import, refresh, inference or deployment.
The actual subscription route and complete live controls remain unverified.

## Official applicability audit (checked 2026-10-10)

[SIWC plan-usage overview](https://developers.openai.com/siwc/token-sharing-open-source)
describes optional plan access for open-source/local apps, including an individually self-hosted VM.
Paid or remotely hosted integrations follow a separate interest/approval path. The preserved
[original repository snapshot](qa/siwc-phase26-20261010/repository-eligibility.json) observed public
visibility and no root/detected license at main@1061ddd. PR #11 has since added the complete
Apache-2.0 source license and [explicit scope/exceptions](../LICENSE_SCOPE.md); GitHub detects
Apache-2.0 on the new main. This is an owner-authorized source decision, not an independent copyright
assignment or license for excluded artwork/material. The missing source-license observation is resolved;
intended local/self-hosted versus hosted use and SIWC eligibility still need confirmation. No registration
or interest request is filed. The original snapshot remains historical and is not current status. Account/workspace,
region/policy eligibility and applicable OpenAI approval remain NOT_CONFIRMED. CLI ChatGPT login is
not consent to this separate product registration. The existing website remains an unchanged read-only
surface; its presence does not authorize a hosted inference service.

[Registration and sign-in](https://developers.openai.com/siwc/token-sharing-open-source/sign-in)
uses dynamic_agent_client only to start registration. The issued client ID binds the validated subject
and selected workspace; future sign-ins reuse it. SameScale must use its own consistent app identity,
stable opaque host, exact 127.0.0.1 callback, fresh state/nonce/PKCE and returned scopes. ID-token
signature/issuer/audience/expiry/nonce and returning-account identity must validate before replacement.
Identity alone grants no plan access. The required plan permissions include offline_access,
resource.invoke and chatgpt.tokens.use.direct. No client secret or partner API key is required for
this public-client flow. Real OpenAI JWKS validation is **not implemented or verified** here.

[Accounts and sessions](https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions)
keeps registrations separate even for identical emails. Renewal must serialize rotating tokens;
selected account/client mappings cannot be mixed. The product double exercises explicit renewal and
revocation between authorizations, preserves credentials on simulated transient failure and clears
a confirmed unusable synthetic session. A consumed evaluation freezes its auth lifecycle: auth failure,
expiry or cancellation ends that attempt without refresh/retry, account substitution or billing fallback.
This deliberately restricts general recovery guidance for the separately authorized one-attempt policy.

[Token reference](https://developers.openai.com/siwc/token-sharing-open-source/token-reference)
describes one-hour access tokens, replaceable 30-day refresh tokens and earliest_refresh_at. The
adapter validates returned lifetime data and rejects an attempt whose authorization can expire during
its timeout. These are credential validity checks, not enforceable token-consumption or quota ceilings.
Access-token internal auth metadata stays opaque; no live token decoding occurred.

[Self-hosted VMs](https://developers.openai.com/siwc/token-sharing-open-source/self-hosted-vms)
requires creating the VM host ID before import, completing OAuth on the browser's local machine and
securely transferring the selected tool registration while retaining the VM's own host ID. Later renewal
belongs to the VM. The docs explicitly lack host-specific attribution/revocation for transferred sessions.
The offline model transfers only a locally issued synthetic object between memory sessions; its distinct
UUID host IDs persist under app-owned private directories. No credential transfer command or CLI auth
migration is implemented. Actual import/protected storage/lifecycle needs separate review and permission.
A host ID is an identifier, not authentication or key-possession proof.

## Frozen Runtime and the credential boundary

[SIWC app-server configuration](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server)
uses stdio, an OAuth bearer env_key and public https://api.openai.com/v1 Responses HTTP/SSE. clientInfo
identifies the app; model/list may be cached and does not prove entitlement. Only a completed turn
establishes that request's successful execution. Renewal with env_key requires a new app-server process
and thread resume. Passing that bearer into the existing Subject/app-server process would expose it
to tools and violates SameScale's boundary; this documented recipe is therefore **not enabled**.

[General app-server protocol](https://learn.chatgpt.com/docs/app-server) also offers experimental
chatgptAuthTokens; successful host refresh can cause an automatic request retry. Schema presence does
not establish SIWC routing/entitlement or isolate credentials from Subject. This adapter never invokes
that login/refresh RPC or uses it as an automatic retry bypass. Both frozen binaries 0.149.0 and 0.153.4
accepted initialize with clientInfo.name/title SameScale in separate hardened network-none containers
with empty disposable CODEX_HOME. Only initialize/initialized were sent; no auth/thread/turn RPC.
Existing local image IDs and frozen versions are retained; the development CLI is not the product Runtime.

The Phase-2.5 controller is reused in a separate PID/mount namespace. Only it owns the offline OAuth
issuer/session and bearer injection to its in-process Responses double. Subject sees unauthenticated
loopback requests and only its Workspace; its tools have denied network syscalls. Verifier gets readonly
final Workspace and hidden verifier assets. OAuth state, code, PKCE, ID/access/refresh credentials and
raw auth/response errors stay outside both. No ~/.codex reader, real importer, browser launcher, secret
environment injection, new Worker, outbound transport or public OAuth API exists. Safe receipts expose
only bounded source/status/counters, never registration/client/subject/host values or credentials.

The synthetic issuer uses private random HMAC signatures for fixture claims. This is an explicit
OAuth/ID-signature stand-in, **not an OpenAI JWT/JWKS verifier**. Only marked offline-siwc credentials
are accepted, and reflection is rejected before output. Repr and errors omit secret values. Stable host
files use owner-only directories/files and reject links, broad permissions and development auth paths.
Production storage, encrypted transport, revocation/refresh ownership and anti-exfiltration are separate
live gates; passing canary isolation cannot certify live credentials.

## Responses and execution controls

[Preview limitations](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations)
require store=false, stream=true and full input arrays over HTTP, omit previous_response_id and the
unsupported sampling/state/token/tool-limit fields, reject system messages, and constrain hosted tools.
The controller validates the SIWC contract before debit. Function/custom tools use namespaces or
additional_tools; unsupported tools are refused. The explicit adapter omits frozen CLI client_metadata, which is not established by the cited SIWC
contract, and supplies trusted originator attribution instead. Input/history, tools and limits are
unchanged; all other unsupported/unknown fields deny. No rejected request is retried. WebSocket continuation, API-key billing and backend-api routing are not
substitutes for the public SIWC route. Token/plan availability remains observational, with no credit purchase.

[Models and inference](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference)
requires account-specific model eligibility and consuming the stream through response.completed.
The offline double exercises failed/incomplete streams; neither is task acceptance. No model/catalog
request was made. Frozen CLI against this controller demonstrates only the measured offline compatibility.

[Errors and recovery](https://developers.openai.com/siwc/token-sharing-open-source/errors-and-recovery)
distinguishes user ineligibility, limits, unavailable usage, invalid authorization and unsupported routes.
The execution policy stops on these conditions instead of changing credentials/billing or retrying.
Raw error/detail text is untrusted and may contain credentials; this boundary keeps bounded codes and
failure evidence. Real serving/request-ID/error-shape coverage remains unverified. No available quota
is reserved, and no observational limit is advertised as a hard spending ceiling.

The original authorization, policy digest, single physical attempt, lease/file lock, fsynced request
debit, timeout, cancellation, sealed result and crash-recovery path remain. SIWC is an operator-only
optional protocol policy; default false is omitted from legacy policy serialization. Existing Fake and
Phase-2.5 receipts keep their schema/identity. New schema-2 receipts bind bounded synthetic auth metadata
and reject mutation. Incomplete attempts never redispatch; sealed evidence may recover without executing.

## First real authorization — independent gates

The bounded source-license decision is complete. The remaining live gates are unfulfilled:

1. Applicable SIWC OSS/local/self-hosted integration and account/workspace eligibility, including
   any OpenAI approval required for the intended integration and rights to material outside the source scope.
2. Explicit consent for a separate SameScale OAuth registration, real account/model/quota metadata reads,
   product credential handling and any secure VM import. Development CLI storage remains excluded.
3. Reviewed OpenAI JWKS validation and production credential storage/renewal/revocation ownership,
   verified TLS/egress and a trusted bearer boundary outside every Subject/tool/Verifier process.
4. Admitted frozen Runtime/provider route and observed model eligibility; complete request counting,
   refresh/retry paths, stream failure and cancellation control verified without unsafe bypasses.
5. Separate authorization for the exact admitted task/model/image/route, one physical attempt, timeout,
   request/turn bounds and failure retention. No repair, second attempt, extra credits or Phase 3 is implied.

Readiness reports `project_source_license` as integrated Apache-2.0 for original project source with
exceptions, separate brand rights and unchanged upstream third-party terms. It removes the obsolete
missing-license blocker; `siwc_applicability` remains `PENDING_ACCOUNT_AND_INTEGRATION_ELIGIBILITY`.
These are shipped source-license declarations, not a dynamic rights audit or account/entitlement probe.
All real account/OAuth/credential/runtime blockers and the unconditional execution denial remain.

This PR cannot satisfy the remaining live gates through fixtures or a toggled environment variable. REAL_CODEX
remains unconditionally denied before queue insertion. **STOP after authorized Git merge and exact-SHA
main CI; no real evaluation, deployment or Phase 3.**
