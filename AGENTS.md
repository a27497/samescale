# SameScale Product (HarnessLab-compatible)

SameScale Product continues the existing HarnessLab P0 evidence-diagnosis and regression Agent
workbench for AI Coding. Keep the existing repository, Git history, and implementation identities.

## Start here

- Read [Current Milestone](CURRENT_MILESTONE.md) for active scope, baseline, acceptance results,
  and the stopping point; [Public Product Contract](PUBLIC_PRODUCT_CONTRACT.md) for supported
  user-facing claims; then [README](README.md) for setup and verification.
- [Project Blueprint](docs/PROJECT_BLUEPRINT.md) owns plans and architecture constraints.
  [Project Status](docs/PROJECT_STATUS.md) retains the P0/real-smoke evidence and historical handoff.
  It links to current state rather than maintaining a competing NEXT.
- Use the repo-local [samescale-product Skill](.agents/skills/samescale-product/SKILL.md) for
  SameScale product implementation, migration, and acceptance work. Read specialist docs as needed.
- The user's current instructions govern task scope and override project/skill guidance within
  system and developer constraints. Source and tests establish implemented behavior; immutable
  artifacts establish observed results. Report discrepancies rather than making prose into proof.
- Maintain plans only in the blueprint and live state only in CURRENT_MILESTONE. Dated audits, campaign
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

- Start with `git status --short --branch`, `git branch --show-current`, `git worktree list`,
  and `git remote -v`. Inspect the diff before editing; do not reinitialize Git or change remotes
  for product naming. One writer per worktree; other worktrees are not cleanup targets.
- SameScale is the product name. Preserve `src/harnesslab`, the `harnesslab` CLI, `HARNESSLAB_*`
  configuration, package/database/API identities, and frozen evidence. Rename only an explicitly
  scoped product surface; never globally replace HarnessLab or rewrite historical reports.
- Codex is the development environment, not a new product runtime or permission to change subject
  models. Reuse the locked Python/FastAPI/PostgreSQL/LangGraph/Vue stack. No new framework,
  multi-agent runtime, dependency upgrade, or paid campaign is implied by setup.
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
- Use the README quickstart for the keyless demo. PostgreSQL-backed tests need an isolated,
  disposable database and migrations; never point destructive fixtures at historical/demo data.
  Update CURRENT_MILESTONE with actual results and blockers. Commit/push only within the current
  user's authorization; verify the pushed branch SHA and report CI separately from local checks.
