# HarnessLab

HarnessLab is an evidence-diagnosis and regression Agent workbench for AI Coding, backed by
reproducible Model × Harness × Judge execution and verifier-validated evidence.

## Start here

- Read [Project Blueprint](docs/PROJECT_BLUEPRINT.md) for first-application scope and acceptance,
  and [Project Status](docs/PROJECT_STATUS.md) for the active task, baseline, and next step.
  [README](README.md) provides setup and verification entrypoints; read specialist docs as needed.
- The user's current instructions govern task scope and override project/skill guidance within
  system and developer constraints. Source and tests establish implemented behavior; immutable
  artifacts establish observed results. Report discrepancies rather than making prose into proof.
- Maintain plans only in the blueprint and live state only in status. Dated audits, campaign
  records, and historical authorizations describe their original scope; they do not start work.

## Invariants and authority

- Evidence authority is deterministic L0 > human gold L1 > LLM Judge L2. Keep Official and Custom
  evidence separate; causal claims require controlled evidence and comparability eligibility.
- Preserve evidence identities and original attempts. Never fabricate results, silently rewrite
  evidence, or present model self-report as verification. `NOT_RUN` and `NOT_VERIFIED` are not passes;
  zero collected tests, missing prerequisites, or skipped critical checks do not establish success.
- Do not print or persist secrets or private reasoning. Use credential references and development
  placeholders; keep hidden verifier/oracle assets outside subject workspaces.
- Inspect Git state before editing and preserve existing user changes. Do not overwrite unrelated
  work or perform destructive Git operations without explicit authorization.
- Without explicit user authorization, do not commit, push, create PRs/tags, merge, deploy, send
  external messages, or launch paid/provider/Harness/Judge campaigns. Credentials and old campaign
  permissions alone are not authorization for a new execution.

## Work and acceptance

- Complete the requested outcome autonomously through routine, reversible implementation choices.
  State reasonable assumptions; ask only when a material scope/contract decision or permission
  boundary cannot be resolved from existing authorization. Continue independent authorized work.
- Stay within the requested scope; a task need not be a whole phase. A roadmap or NEXT item is
  context, not permission to advance phases. Stop when the requested outcome is complete.
- Diagnose failures and retry when a concrete correction or changed condition justifies it.
  If progress depends on unavailable input or infrastructure, report the blocker and evidence;
  do not repeat unchanged attempts indefinitely.
- Match verification to the changed contract and risk. For documentation, check links, scope,
  consistency, and affected documentation contracts. For behavior changes, run focused checks;
  expand only for failures, cross-cutting risk, or an explicitly required acceptance/release gate.
  Once sufficient checks pass, stop testing. Report what ran, results, and material limitations.
