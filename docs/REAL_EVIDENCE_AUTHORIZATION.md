# Real Evidence Authorization

Phase K-B0 stop state: `PHASE_K_B0_DSH_OBSERVED_MODEL_FIXED_AWAITING_REAL_SMOKE_AUTHORIZATION`.

No provider, Codex, Claude Code, DeepSeek, or Judge call is authorized by this document. Ambient credentials and existing logins are not authorization. The eight-call K-B1 smoke in `release/core-real-smoke-plan.json` requires separate explicit authorization; the 630-run Matrix and 63 Judge calls require later authorization.

## Frozen Core scope

- Corpus: `harnesslab-core-18-v1`, 18 tasks (6 Python, 6 Java, 6 TypeScript).
- Seven Matrix cells; five repetitions per task; 90 planned runs per cell.
- Model-only: `gpt-5.6-sol` through an operator-trusted Responses-compatible relay, `qwen3.8-max` through Alibaba Cloud Model Studio/Bailian's Messages-compatible route, and non-thinking `deepseek-v4-pro` through DeepSeek's first-party Chat Completions API.
- Harness: Codex `gpt-5.6-sol` medium/high through the same relay, Claude Code Harness × `qwen3.8-max` through Bailian, and DeepSeek Harness E1 × `deepseek-v4-flash` through DeepSeek official. DeepSeek E2 remains `DEFERRED_NOT_VERIFIED`.
- Judge: `glm-5.2` hosted by Alibaba Cloud Model Studio/Bailian, Chat Completions, thinking disabled, and `core-calibration@1.0.0` repeat three. This is `ALIBABA_HOSTED_MODEL`, not a Zhipu official API claim.

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

Configuration references are `HARNESSLAB_GPT56_RELAY_BASE_URL`, `HARNESSLAB_GPT56_RELAY_API_KEY`, `DASHSCOPE_API_KEY`, `HARNESSLAB_BAILIAN_ANTHROPIC_BASE_URL`, `HARNESSLAB_BAILIAN_OPENAI_BASE_URL`, and `DEEPSEEK_API_KEY`. Values must not enter Git or evidence artifacts. Operator URLs are syntax-checked without connecting.

For the Beijing Bailian Anthropic-compatible API, `HARNESSLAB_BAILIAN_ANTHROPIC_BASE_URL` uses the operator/Claude Code base URL `https://dashscope.aliyuncs.com/apps/anthropic`. The frozen direct Messages route appends `/v1/messages`; Claude Code receives the operator base URL unchanged as `ANTHROPIC_BASE_URL`.

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

All six equal `NOT_RUN`. K-B1 authorization must name `core-real-smoke-v1`, approve exactly eight top-level launches and the 14,256-token ceiling, supply the declared configuration references, and accept every predefined abort condition. It does not authorize the Matrix, full Judge run, tag, or uplift claim.

The smoke must stop on authentication, route/schema/observed-model/alias drift, any secret leak, proxy bypass or unrestricted network, verifier networking, P-Lane route mismatch, task/artifact binding failure, provider fallback, or Judge persistence/integrity failure. Only successful separately authorized smoke may support a later Matrix authorization decision.

Observed-model validation is harness-aware. Claude Code must expose the exact requested `qwen3.8-max` identity in its full stream. DeepSeek Harness E1 instead preserves its frozen `FINAL_OUTPUT_ONLY` limitation with `observed_model_status=NOT_EXPOSED` and `observed_model=null`; its requested provider/model identity is proven separately by the runtime doctor's effective configuration and is never copied into observed evidence. This limitation does not promote DSH evidence to full observed-model comparability.

The production control plane is `harnesslab release smoke preflight` for keyless validation and `harnesslab release smoke execute --allow-real-smoke` for the later explicitly authorized run. Both consume the same exact-plan bindings. Gate K injects fake providers into the same executor used by the real command. Preflight resolves no credential values and performs zero provider calls. Execute validates all six references and then creates, inspects, removes, and verifies absence of a temporary Docker bridge configured with `--internal --ipv6=false` and `com.docker.network.bridge.gateway_mode_ipv4=isolated`; incompatibility raises `EGRESS_NETWORK_ISOLATION_UNAVAILABLE` before runtime resolution or call one. It then validates all routes, enforces eight launches and 14,256 output tokens internally, runs in plan order, and persists an abort receipt immediately on the first typed failure. Its Judge path invokes only `core-calibration/1.0.0#label-l0-pass` through `JudgeRunner`; it never invokes or reports the 63-call calibration campaign.
