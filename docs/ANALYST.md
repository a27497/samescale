# Attribution Analyst

Phase J is a read-only analysis layer over existing immutable HarnessLab experiment evidence. It
answers attribution questions without becoming another execution Agent and without changing the
authority of deterministic verifiers, curated gold, Judges, or Phase G statistics.

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

`FakeAnalystBackend` is deterministic and keyless. Phase J has no operational real-provider
backend; ambient credentials cannot trigger a call. Persisted trace and task strings are untrusted
evidence data and cannot change the graph or tool registry.

## Citations and claims

Evidence catalog entries use stable logical identities, never paths: `run:<id>`,
`trace:<run>#event:<ordinal>`, `task:<id>@<version>`, `cell:<experiment>:<cell>`, and
`ablation:<experiment>:<ablation>`.

Every factual claim is `VERIFIED_FACT` and must cite returned catalog entries. Unknown citations
reject the draft. Interpretations are `HYPOTHESIS` and must name evidence needed to verify or
falsify them. Causal wording is not accepted as a verified fact. A controlled ablation supports a
fact about the observed ablation result, but evidence tier, sample size, and Comparability
limitations remain visible and controlling.

The evidence hierarchy remains `L0 > L1 > L2`; Analyst output cannot alter PASS/FAIL, scores,
ground truth, Judge output, or capability denominators.

## Persistence and verification

Trusted host code atomically writes only validated `report.json` and `report.md` under
`harnesslab-artifacts/analyst/<analysis-id>/`. Canonical identity excludes timestamps. The Agent
has no write tool.

Gate J creates evidence before analysis through ExperimentSpec/Plan, queue,
ExperimentRunExecutor, fake Codex runners, persisted manifests, ExperimentReport, and a declared
reasoning-effort AblationSpec. It then compares source database rows, Judge state, artifact
digests/mtimes, and fake execution call counts before and after analysis.

```text
uv run --locked python scripts/verify_gate_j.py
```

All real provider, Harness, and Judge calls remain not run during analysis.
