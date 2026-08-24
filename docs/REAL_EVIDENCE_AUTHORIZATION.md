# Real Evidence Authorization

Phase K-A stop state: `PHASE_K_A_REVIEW_FIXED_AWAITING_REAL_EVIDENCE_AUTHORIZATION`.

No provider, Codex, Claude Code, DeepSeek, or Judge call is authorized by this document. Ambient credentials and existing logins are not authorization. Phase K-B may start only after the user explicitly approves the exact bounded execution below and resolves the requested Model-only model ids.

## Frozen Core scope

- Corpus: `harnesslab-core-18-v1`, 18 tasks (6 Python, 6 Java, 6 TypeScript).
- Seven Matrix cells; five repetitions per task; 90 planned runs per cell.
- Model-only: three slots using OpenAI Responses, Anthropic Messages, and an OpenAI-compatible Chat Completions endpoint. Exact requested model ids remain `NOT_VERIFIED`; the third provider/base URL/credential reference and reasoning setting are also unresolved.
- Harness: Codex medium, Codex high, Claude Code Sonnet, and DeepSeek Harness E1. DeepSeek E2 remains `DEFERRED_NOT_VERIFIED`.
- Judge: `core-calibration@1.0.0`, digest `sha256:c2708196237eab94dac473581e3a06de2f7d0e2c50e8b55190b253e547fc43fb`, repeat three, 15 public cases.

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

The 360 Harness launches may issue internal provider requests whose count is `NOT_CALCULATED_FROM_REPOSITORY_EVIDENCE`. Monetary cost is `NOT_CALCULATED_FROM_REPOSITORY_EVIDENCE`; no current price table is frozen. Per-subject maximum output is 2,000 tokens, timeout is 90 seconds, and task network policy is deny. Judge maximum output is 256 tokens per call.

Credential references are `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, the future third-provider credential reference, an explicit Codex authorization/login reference, an explicit Claude Code authorization/login reference, `DEEPSEEK_API_KEY`, and the future Judge credential reference. Values must not enter Git or evidence artifacts.

## Pair and ablation

The planned P-Lane is direct OpenAI versus Codex medium with 90 paired observations. Harness uplift requires the same requested/observed model, provider route, task/version/digest, workspace, verifier, context, budget, network policy, and other Comparability hard controls. The current direct `/responses` route and `codex-cli-default` differ, and the direct model is unselected. Therefore the pair is `NOT_VERIFIED`; under current identities it cannot support a `COMPARABLE` uplift claim. Authorization must supply a genuinely route-comparable design or accept that no uplift conclusion will be made.

The ablation compares Codex medium with Codex high, changing only `reasoning_effort`. It plans 90 paired observations and formal per-task n=5 evidence. It may support only the treatment association justified by completed comparable observations.

## USER AUTHORIZATION REQUIRED BEFORE

- `REAL_PROVIDER_SMOKE`
- `REAL_CODEX_SMOKE`
- `REAL_CLAUDE_SMOKE`
- `REAL_DEEPSEEK_SMOKE`
- `REAL_MATRIX_EVIDENCE`
- `REAL_JUDGE_SMOKE`

All six equal `NOT_RUN`. Authorization must state the exact requested model for each Model-only slot; the third provider/base URL/credential reference/reasoning choice; Judge provider/profile/credential reference; permission for each Harness runtime to use supplied authentication; approval of 693 top-level calls/launches and the 1,276,128-token ceiling; and the Pair decision above. It should confirm the trusted PostgreSQL target and artifact root.

After authorization, Phase K-B freezes executable profiles and an `ExperimentPlan`, runs bounded smokes before the Matrix, stops on identity/budget/integrity drift, binds real reports and BadCases, reruns final release verification, obtains exact-head remote CI, and only then considers `v1.0.0-core`.
