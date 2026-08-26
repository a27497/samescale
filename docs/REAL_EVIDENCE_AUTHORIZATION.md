# Real Evidence Authorization

Phase K-B1-R4 stop state: `PHASE_K_B1_R4_OUTPUT_BUDGET_SEMANTICS_REPAIR_KEYLESS`.

Three real top-level v1 K-B1 attempts occurred before this redesign. On the first, call 1 invoked the configured GPT relay successfully and completed with requested and observed model `gpt-5.6-sol` in approximately 16,773 ms; the overall smoke then aborted with `INFRASTRUCTURE` because the non-root Hidden Verifier could not read restrictive host bind mounts. The K-B1-R1 permission-portability repair addressed that infrastructure defect.

On the second attempt, the same frozen call 1 aborted with `PROVIDER_FAILURE`, provider failure `timeout`, and latency approximately 90,454 ms. It had no status code, response status, or observed model. Calls 2-8 were not run and there was no retry within that attempt. The then-current evidence did not capture the timeout subtype, so `TIMEOUT_PHASE=NOT_AVAILABLE`; the supported conclusion is only `INTERMITTENT_OR_UNCLASSIFIED_PROVIDER_TIMEOUT`, not relay outage, read timeout, model latency regression, provider outage, or network failure.

On the third attempt, call 1 requested and observed `gpt-5.6-sol`, completed in 10,947 ms, reached a successful verifier sandbox, and produced `verifier_passed=false`, `verifier_score=0.8`, and `outcome=verified_fail`. This is one smoke observation, not a model aggregate. Call 2, Qwen through the v1 Bailian route, returned HTTP 403 `AUTHENTICATION`; calls 3-8 were `NOT_RUN`.

The v1 plan identities and all three attempt facts are preserved in `release/history/core-real-v1.json`, anchored to authoritative commit `45e83d735cee48d9a29361da5964cee83d048a42`, exact Git blobs, byte digests, and canonical plan digests. Operator-local execution paths and artifacts are not imported. The Token Plan Lite mismatch was an operator/provider-contract mismatch; it is not evidence that Qwen itself failed.

After R3, one authorized v2 smoke attempt executed two top-level launches and then stopped fail-closed. Call 1 requested and observed `gpt-5.6-sol`, completed in 45,137 ms, and produced `verifier_passed=false`, `verifier_score=0.8`, `outcome=verified_fail`; this is one smoke observation, not aggregate model performance. Call 2 reached the fixed OpenCode Go Messages route for `qwen3.8-max`, returned a request ID, and ended after 60,131 ms with `response_status=max_tokens`. The pre-R4 adapter normalized that configured output-budget exhaustion as `incomplete_response`, which the smoke control plane mapped to `SCHEMA_MISMATCH`; calls 3-8 were `NOT_RUN`, with no retry or fallback. Safe attempt facts are preserved in `release/history/core-real-v2-attempt-1.json`.

After R4, a second authorized v2 smoke attempt executed four top-level launches and stopped fail-closed. The direct GPT relay observation was `verified_fail` at score 0.8; Qwen through OpenCode Go Messages and DeepSeek through its official route were each `verified_pass` at score 1.0. Codex-medium then ended as `INFRASTRUCTURE` before a durable Codex call artifact was produced; calls 5-8 were `NOT_RUN`, with no retry or fallback. Keyless diagnostics do not support attributing that failure to egress provisioning, outer-container creation, the security profile, cleanup, static strict-config parsing, or the GPT provider. Safe facts and exact plan/receipt digests are preserved in `release/history/core-real-v2-attempt-2.json`.

K-B1-R4 is a keyless semantics repair and makes zero real calls. A provider response that reaches the configured output-token budget through Messages `max_tokens` or Chat Completions `length` now preserves its public result, observed model when exposed, usage, request ID, and stop reason so the existing subject-output contract decides capability. Invalid/truncated direct-patch output therefore becomes `SUBJECT_OUTPUT_ERROR` rather than provider infrastructure failure. A true context-window overflow remains `INCOMPLETE_RESPONSE`. The 2,000-token subject budget, 90-second timeout, eight-call order, 14,256-token smoke ceiling, no-retry rule, and no-fallback rule are unchanged. OpenCode Go automated benchmark use remains operator-confirmed (`OPENCODE_GO_AUTOMATED_BENCHMARK_PERMISSION=OPERATOR_CONFIRMED_PROVIDER_PERMISSION`); the 630-run Matrix and 63 Judge calls still require later authorization.

## Frozen Core scope

- Corpus: `harnesslab-core-18-v1`, 18 tasks (6 Python, 6 Java, 6 TypeScript).
- Seven Matrix cells; five repetitions per task; 90 planned runs per cell.
- Model-only: `gpt-5.6-sol` through an operator-trusted Responses-compatible relay, `qwen3.8-max` through the fixed OpenCode Go Messages endpoint `https://opencode.ai/zen/go/v1/messages`, and non-thinking `deepseek-v4-pro` through DeepSeek's first-party Chat Completions API.
- Harness: Codex `gpt-5.6-sol` medium/high through the same relay, Claude Code Harness × `qwen3.8-max` through the same fixed OpenCode Go route, and DeepSeek Harness E1 × `deepseek-v4-flash` through DeepSeek official. DeepSeek E2 remains `DEFERRED_NOT_VERIFIED`.
- Judge: `glm-5.2` through fixed OpenCode Go Chat Completions endpoint `https://opencode.ai/zen/go/v1/chat/completions` and `core-calibration@1.0.0` repeat three. No documented thinking-disable control is frozen: `JUDGE_THINKING_CONTROL=PROVIDER_DEFAULT_NOT_EXPLICITLY_CONFIGURED`.

OpenCode Go is `THIRD_PARTY_INFERENCE_PLATFORM`, with `provider_id=opencode-go`, `provider_display_name=OpenCode Go`, and `inference_provider=OpenCode Go`. Requested model names identify routed requests; observed identity still requires response evidence. The contracts make no Qwen, Zhipu, Alibaba, or other upstream first-party provenance claim. The selected official route snapshot is frozen in `release/opencode-go-route-snapshot.json` from the public OpenCode Go documentation without a live model-catalog probe.

## Exact execution ceiling

| Scope | Count |
| --- | ---: |
| Subject runs | 630 |
| Direct-model runs | 270 |
| Codex Harness runs | 180 |
| Claude Code runs | 90 |
| DeepSeek Harness E1 runs | 90 |
| Judge calls | 63 |
| Top-level external calls / harness launches | 693 |
| Ablation paired observations | 90 |
| Subject maximum output tokens | 1,260,000 |
| Judge maximum output tokens | 16,128 |
| Total maximum output tokens | 1,276,128 |

The 360 Harness launches may issue internal provider requests whose count is `NOT_CALCULATED_UNTIL_REAL_SMOKE`. Monetary cost is `NOT_CALCULATED_UNTIL_REAL_SMOKE_USAGE_AND_RELAY_PRICE`; no relay price table or usage evidence is frozen. Per-subject maximum output is 2,000 tokens and timeout is 90 seconds. Judge maximum output is 256 tokens per call.

V2 configuration references are only `HARNESSLAB_GPT56_RELAY_BASE_URL`, `HARNESSLAB_GPT56_RELAY_API_KEY`, `HARNESSLAB_OPENCODE_GO_API_KEY`, and `DEEPSEEK_API_KEY`. Values must not enter Git, argv, logs, traces, manifests, reports, or evidence artifacts. Presence diagnostics print only `VAR=SET` or `VAR=MISSING`.

Direct Qwen uses Anthropic-style `x-api-key` authentication. Claude Code receives the fixed literal `ANTHROPIC_BASE_URL=https://opencode.ai/zen/go`, the resolved OpenCode Go credential only as `ANTHROPIC_API_KEY`, and `ANTHROPIC_MODEL=qwen3.8-max`; it does not inherit ambient `ANTHROPIC_AUTH_TOKEN`. Claude Code constructs `/v1/messages`, so the base deliberately omits `/v1`. Judge uses `Authorization: Bearer` and sends neither Bailian `enable_thinking` nor private reasoning content into persisted/parsing evidence.

The GPT mapping is `VERIFIED_BY_OPERATOR`; its upstream first-party provenance is `NOT_INDEPENDENTLY_VERIFIED`. It must be described as `gpt-5.6-sol via operator-trusted OpenAI-compatible relay`, never as OpenAI first-party or an OpenAI official API.

## Pair and ablation

The configured P-Lane `gpt56-relay-direct-vs-codex` uses direct `gpt-5.6-sol` and Codex medium through the same declared relay/Responses route. This is `CONFIGURED_NOT_VERIFIED`, not `COMPARABLE`: K-B1 must establish the actual route and observed-model evidence, then the ComparabilityEngine decides. If it does not return `COMPARABLE`, release policy is `NO_HARNESS_UPLIFT_CLAIM`.

The `codex-gpt56-reasoning-effort` ablation compares Codex medium with Codex high, changing only `reasoning_effort`. It is `CONFIGURED_NOT_RUN`, plans 90 paired observations and formal per-task n=5 evidence, and may support only the treatment association justified by completed comparable observations.

## USER AUTHORIZATION REQUIRED BEFORE

- `REAL_PROVIDER_SMOKE`
- `REAL_CODEX_SMOKE`
- `REAL_CLAUDE_SMOKE`
- `REAL_DEEPSEEK_SMOKE`
- `REAL_MATRIX_EVIDENCE`
- `REAL_JUDGE_SMOKE`

`REAL_PROVIDER_SMOKE=NOT_VERIFIED` and `REAL_CODEX_SMOKE=NOT_VERIFIED`; the other four states remain `NOT_RUN`. Any new authorization must name `core-real-smoke-v2`, approve exactly eight top-level launches and the 14,256-token ceiling, supply the four declared configuration references, and accept every predefined abort condition. It does not authorize the Matrix, full Judge run, tag, or uplift claim.

The smoke must stop on authentication, route/schema/observed-model/alias drift, any secret leak, proxy bypass or unrestricted network, verifier networking, P-Lane route mismatch, task/artifact binding failure, provider fallback, or Judge persistence/integrity failure. Only successful separately authorized smoke may support a later Matrix authorization decision.

Observed-model validation is harness-aware. Claude Code must expose the exact requested `qwen3.8-max` identity in its full stream. DeepSeek Harness E1 instead preserves its frozen `FINAL_OUTPUT_ONLY` limitation with `observed_model_status=NOT_EXPOSED` and `observed_model=null`; its requested provider/model identity is proven separately by the runtime doctor's effective configuration and is never copied into observed evidence. OpenCode Go model identity also remains unverified until real response evidence exists.

The production control plane is `harnesslab release smoke preflight` for keyless validation and `harnesslab release smoke execute --allow-real-smoke` for the later explicitly authorized run. Both consume the same exact-plan bindings. Gate K injects fake providers into the same executor used by the real command. Preflight resolves no credential values and performs zero provider calls. Execute validates all four references and then creates, inspects, removes, and verifies absence of a temporary Docker bridge configured with `--internal --ipv6=false` and `com.docker.network.bridge.gateway_mode_ipv4=isolated`; incompatibility raises `EGRESS_NETWORK_ISOLATION_UNAVAILABLE` before runtime resolution or call one. It then validates all routes, enforces eight launches and 14,256 output tokens internally, runs in plan order, and persists an abort receipt immediately on the first typed failure. Its Judge path invokes only `core-calibration/1.0.0#label-l0-pass` through `JudgeRunner`; it never invokes or reports the 63-call calibration campaign.
