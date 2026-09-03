# Phase L.1 — Core Architecture Ownership Audit

Audit baseline: `main` / `v1.0.0-core` / `e3cab6f180f2bbcd6c8f134aa3d710c503fe6e87`.

This is an ownership guide to the released Core, not a proposal to change it. Source and tests are
treated as authoritative where prose differs. “Authority” below means the component allowed to
decide a fact, not merely the component that displays or transports it.

## 1. System map

The shortest accurate mental model is:

```text
Task package + frozen profiles
  -> deterministic plan and durable logical slots
  -> M-Lane or H-Lane runtime
  -> final workspace + normalized public evidence
  -> isolated hidden verifier
  -> immutable lane manifest
  -> PostgreSQL lifecycle/reference
  -> digest-verifying report + Comparability/statistics
  -> Judge/Analyst/Workbench projections
  -> detached release verifier + semantic receipt
```

| Module | Responsibility and public entrypoints | Important contracts | May call | Must not own | Persistence/artifact boundary | Correctness authority |
| --- | --- | --- | --- | --- | --- | --- |
| Product entrypoints | `src/harnesslab/__main__.py` invokes `harnesslab.cli:app`. `src/harnesslab/cli.py` assembles Typer commands, including `run_direct_model`, experiment, Judge, Analyst, and release command groups. `src/harnesslab/api/app.py:create_app` assembles FastAPI. | CLI arguments, FastAPI request/response DTOs, `src/harnesslab/core/config.py:Settings`. | Domain services, SQLAlchemy session factory, Uvicorn. | Evaluation truth, statistics, or secret material. | CLI prints safe summaries; API returns typed DTOs. | None; it is routing and presentation glue. |
| Task package and verifier | `src/harnesslab/tasks/package.py:TaskPackage.load/materialize/apply_oracle` validates strict package layout and computes package, workspace, verifier, oracle, and context digests. `src/harnesslab/tasks/validation.py:validate_task_package` proves baseline-fail/oracle-pass. `src/harnesslab/tasks/verifier.py:execute_verifier` is the trusted host validator used for package qualification. | `TaskPackageManifest`, `TaskDefinition`, `MaterializedTask`, `VerifierReport`, `VerifierExecutionResult`, `EvidenceManifest`. | Filesystem-safe package reads and a bounded verifier subprocess during trusted package validation. | Subject execution policy, model judgment, or experiment aggregation. Oracle/verifier assets must not enter the subject materialization. | Versioned files under `tasks/<id>/<version>`; transient materializations; deterministic digests. | The hidden deterministic verifier is L0 for task pass/fail and score. |
| M-Lane | `src/harnesslab/model_lane/runner.py:DirectModelRunner.run` renders `direct-patch-v1`, invokes a `ProviderAdapter`, parses/applies a strict patch, and sends the final workspace to the isolated verifier. Provider implementations are in `src/harnesslab/model_lane/providers.py`; patch safety is in `patch.py`; prompt identity is in `prompt.py`. CLI: `harnesslab model run` -> `src/harnesslab/cli.py:run_direct_model`. | `ModelProfile`, `ProviderRequest/ProviderResult`, `DirectPatch`, `DirectModelEvidence`, `DirectModelRunResult`. | Approved provider adapter, `TaskPackage`, `DockerSandbox.run_hidden_verifier_workspace`. | Tools for the model, raw-response retention, private reasoning, or final correctness. | Atomic per-run directory containing `manifest.json`, optional workspace, and verifier bundle. | Provider output is subject evidence; only the hidden verifier decides correctness. |
| Codex H-Lane | `src/harnesslab/harness_lane/runner.py:CodexHarnessRunner.run` owns the fresh workspace, prompt, filesystem inventory, verifier call, and evidence. `adapter.py:CodexHarnessAdapter` defines/collects the Codex contract; `docker_backend.py:DockerCodexBackend` runs the pinned runtime; `trace.py:collect_codex_jsonl` sanitizes and normalizes native events. | `CodexHarnessProfile`, `CodexExecutionPlan`, `CodexProcessCapture`, `NormalizedTrace`, `HarnessLaneEvidence`. | Codex backend, artifact hygiene helpers, isolated verifier. | Correctness, observed model inference when unexposed, or retention of private reasoning/raw authorization data. | `native/codex.sanitized.jsonl`, `trace/normalized.json`, final workspace, verifier artifacts, canonical manifest. | Filesystem state plus hidden verifier; native success messages are diagnostic only. |
| Multi-harness H-Lane | `src/harnesslab/multi_harness/runner.py:MultiHarnessRunner.run` is the shared Claude/DeepSeek orchestration. `adapter.py:ClaudeCodeAdapter/DeepSeekHarnessAdapter`, `docker_backend.py:DockerMultiHarnessBackend`, and `trace.py:collect_claude_stream/collect_deepseek_final` isolate adapter-specific behavior. | `MultiHarnessProfile`, `HarnessExecutionPlan`, `HarnessProcessCapture`, `MultiHarnessEvidence`. | Pinned harness backend, provider-scoped egress boundary, isolated verifier. | A second statistics stack, correctness, or pretending DeepSeek E1 has full trace coverage. | Same immutable run-bundle shape as H-Lane, with harness-specific sanitized native filename. | Hidden verifier only. Harness/process classifications remain infrastructure/trajectory evidence. |
| Sandbox and egress | `src/harnesslab/sandbox/runner.py:DockerSandbox` materializes/runs subjects and separately stages hidden verifiers. `_create_arguments` owns fixed Docker security flags and `_inspect_security` checks effective state. `src/harnesslab/egress.py:ProviderScopedDockerBoundary` creates an isolated subject network plus controlled proxy topology. | `SandboxRunResult`, `SandboxArtifactManifest`, `SecurityEvidence`, `EgressPolicy`, `ProxySecurityAttestation`. | Docker CLI through `sandbox/docker_cli.py`; artifact writer; preflight inspection. | Arbitrary caller Docker flags, unconfined host paths, task correctness, or general-purpose networking. | Managed runtime roots are ephemeral; safe workspace/stdout/stderr/manifest bundles are immutable artifacts. | Enforces execution isolation; the verifier running inside it remains correctness authority. |
| Experiment planning and durable execution | `src/harnesslab/experiment/spec.py:load_experiment_spec`, `plan.py:build_experiment_plan/build_methodology_v2_plan`, `queue.py:enqueue_plan/claim_next_run/heartbeat_run/finish_run`, and `executor.py:ExperimentRunExecutor` own deterministic slots and lifecycle. CLI: `harnesslab experiment plan/run`, `harnesslab run inspect`. Real Matrix: `src/harnesslab/release/matrix.py:execute_real_matrix`. | `ExperimentSpec`, `ExperimentPlan`/`MethodologyV2ExperimentPlan`, `ExperimentRunSlot`, `RunSnapshot`, `Experiment*Record`. | Existing M/H bindings, PostgreSQL transactions, heartbeat task, manifest validation. | Reimplementing lane runners, changing immutable plans, interpreting statistics, or overwriting earlier physical-attempt evidence. | PostgreSQL stores plan/slot/lifecycle and artifact references; lane artifacts remain on disk. | Lifecycle authority is the queue state machine; capability truth still comes from verified lane manifests. |
| Evidence and trace | Lane models enforce coherent manifests. `src/harnesslab/evidence/reader.py:trusted_artifact_path/load_verified_manifest/load_normalized_trace` confines paths, verifies bytes and physical attempt identity, and exposes normalized traces only. `src/harnesslab/experiment/evidence.py:validate_manifest_against_slot` binds manifests back to planned controls. | `DirectModelEvidence`, `HarnessLaneEvidence`, `MultiHarnessEvidence`, `VerifiedManifest`, `NormalizedTrace`, `ComparisonFacts`. | Trusted-root filesystem reads and digest functions. | Reconstructing missing identity, opening private native transcripts on read surfaces, or changing outcomes. | PostgreSQL holds path+digest; the immutable file holds detailed evidence; trace is a digest-bound sibling. | Evidence integrity authority, not correctness or causal authority. |
| Comparability and statistics | `src/harnesslab/comparability/manifest.py:facts_from_manifest/load_manifest_facts` extracts identities. `engine.py:ComparabilityEngine.assess` compares controls/treatments. `experiment/statistics.py:summarize_cell/summarize_pair` computes approved metrics. `experiment/report.py:load_verified_experiment_evidence/build_experiment_report` reopens artifacts and composes reports. | `ComparisonFacts`, `ComparabilityReport`, `RunObservation`, `CellStatistics`, `PairStatistics`, `ExperimentReport`. | Verified manifests, deterministic numerical libraries, declared pair/ablation definitions. | Correctness, filling missing controls, or causal claims beyond declared comparable treatment evidence. | Deterministic JSON/Markdown report identity; no new execution evidence. | Statistical and comparability authority for admissibility and reported aggregates. |
| JudgeLab | `src/harnesslab/judgelab/plan.py:build_calibration_plan` expands slots; `calibration.py:execute_calibration` orchestrates; `runner.py:JudgeRunner.run` produces immutable evaluations; `report.py:build_judge_report` reloads evidence and qualifies a cell. CLI: `harnesslab judge suite validate/plan/calibrate/report`. | `JudgeSuite`, `JudgeDefinition`, `JudgeCalibrationPlan`, `JudgeEvaluationSlot`, `JudgeEvidence`, `JudgeCalibrationReport`, `AuthorityResolution`. | Existing one-attempt provider adapter, PostgreSQL Judge records, immutable artifacts. | M/H subject execution, hidden-gold disclosure, L0/L1 override, or universal Judge-quality claims. | PostgreSQL calibration/slot/reference records plus one immutable evidence file per evaluation and report JSON/Markdown. | L2 annotation only; `resolve_authority` preserves L0 > L1 > L2. |
| Attribution Analyst | `src/harnesslab/analyst/service.py:AnalystService.analyze` composes `AnalystEvidenceRepository`, `AnalystToolRegistry`, and `AttributionGraph`. `graph.py:AttributionGraph` has decide/tools/finalize nodes. `report.py:validate_and_build_report` verifies exact-value facts. CLI: `harnesslab analyst analyze`. | `AnalysisRequest/Scope`, strict six-call union, `EvidenceEntry`, `FactAssertion`, `VerifiedFact`, `HypothesisClaim`, `AttributionReport`. | Read-only scoped queries, verified report/trace/task evidence, injected backend (operationally fake in Core). | SQL/path/shell/provider/execution tools, evidence mutation, free-form verified prose, or causal upgrades. | Source evidence is read-only; trusted host atomically writes only validated Analyst report JSON/Markdown. | Explanation only. Exact facts inherit cited evidence; hypotheses have no causal authority. |
| Workbench API | `src/harnesslab/api/routes/workbench.py` maps HTTP routes to `src/harnesslab/api/workbench_service.py`. The service builds typed projections, task-scoped Matrix points, verified run/trace/Judge views, regression comparisons, diagnosis, and readiness. | DTOs in `api/workbench_models.py`, Phase G/H report models, diagnosis models. | PostgreSQL reads, trusted artifact reader, existing statistics/comparability/diagnosis services. | Browser-triggered subject/provider/Harness/Judge execution or a new statistics authority. | Public DTOs only; server paths and ORM records do not cross the boundary. | Presentation; it inherits evidence/statistics authorities. Note that diagnosis BadCase export is a computation endpoint, not canonical release BadCase mutation. |
| Release and semantic verifier | `src/harnesslab/release/reconciliation.py:verify_candidate/verify_v6_snapshot`, `contracts.py:evaluate_release_readiness/tag_creation_authorized`, and `final_verifier.py:resolve_authoritative_snapshot/resolve_github_ci/bind_final_head/verify_semantic_final_release` compose released evidence. Entry: `scripts/verify_gate_k.py:verify_final_release`. | `ReleaseEvidenceManifest`, `EvidenceBinding`, `AcceptedRealEvidencePlan`, `AuthoritativeReleaseSnapshot`, `RemoteCIAttestation`, `SemanticReleaseReceipt`. | Read-only PostgreSQL, trusted artifacts, Git/`gh` metadata, corpus/claim/BadCase reconstruction. | Creating a tag, rewriting historical evidence, executing models, or accepting a candidate/CI from another head. | Committed stable candidate plus an in-memory head/CI binding and detached receipt. | Final release authority. `tag_creation_authorized` requires ready bound manifest plus matching receipt. |

## 2. Five core execution chains

### 2.1 Model-only task execution

```text
User
-> `harnesslab model run`
-> `src/harnesslab/cli.py:run_direct_model`
-> `src/harnesslab/model_lane/runner.py:DirectModelRunner.run`
-> `src/harnesslab/tasks/package.py:TaskPackage.load/materialize`
-> `src/harnesslab/model_lane/prompt.py:render_direct_prompt`
-> `src/harnesslab/model_lane/providers.py:adapter_for_profile` -> `ProviderAdapter.invoke` (one attempt)
-> `src/harnesslab/model_lane/patch.py:parse_direct_patch/apply_direct_patch`
-> final workspace digest
-> `sandbox/runner.py:DockerSandbox.run_hidden_verifier_workspace`
-> isolated `VerifierReport`
-> `DirectModelEvidence`
-> atomic per-run `manifest.json`/workspace/verifier artifact
-> CLI outcome and score
```

The provider supplies public patch text, not correctness. A refusal, malformed patch, provider
failure, verifier-infrastructure failure, and verifier-backed capability result remain distinct.

### 2.2 Codex Harness task execution

The production Matrix route is the most complete Codex chain:

```text
User
-> `harnesslab release matrix execute --allow-real-matrix --max-runs ...`
-> `src/harnesslab/cli.py:execute_release_matrix`
-> `src/harnesslab/release/matrix.py:execute_real_matrix`
-> `MatrixControlPlane.build_plan` + `production_matrix_bindings`
-> `src/harnesslab/experiment/queue.py:enqueue_plan` -> PostgreSQL
-> `src/harnesslab/experiment/executor.py:ExperimentRunExecutor.claim` [transaction + lease]
-> `src/harnesslab/release/matrix.py:_CodexProductionBinding.run`
-> `src/harnesslab/egress.py:ProviderScopedDockerBoundary`
-> `src/harnesslab/harness_lane/docker_backend.py:DockerCodexBackend.run`
-> `src/harnesslab/harness_lane/adapter.py:CodexHarnessAdapter`
-> `src/harnesslab/harness_lane/trace.py:collect_codex_jsonl`
-> sanitized JSONL + Normalized Trace + filesystem inventory
-> `src/harnesslab/harness_lane/runner.py:CodexHarnessRunner.run`
-> `src/harnesslab/sandbox/runner.py:DockerSandbox.run_hidden_verifier_workspace`
-> immutable `HarnessLaneEvidence` bundle
-> `src/harnesslab/experiment/evidence.py:validate_manifest_against_slot`
-> `src/harnesslab/experiment/queue.py:finish_run` [transaction; path+digest+outcome]
```

The asynchronous boundary is explicit: `claim_next_run` uses a lease; the executor runs a
concurrent heartbeat; a lost lease or cancellation prevents the stale owner from finishing.

### 2.3 Experiment Matrix durable execution

```text
User / release CLI
-> `src/harnesslab/cli.py:execute_release_matrix`
-> `src/harnesslab/release/matrix.py:MatrixControlPlane.load/preflight/build_plan`
-> `src/harnesslab/experiment/plan.py:build_experiment_plan` deterministic cell x task x repeat expansion
-> `src/harnesslab/experiment/queue.py:enqueue_plan`
-> PostgreSQL records in `src/harnesslab/db/models/experiment.py`
-> `src/harnesslab/experiment/queue.py:claim_next_run` using `FOR UPDATE SKIP LOCKED`
-> `src/harnesslab/experiment/executor.py:ExperimentRunExecutor.execute`
-> CLAIMED -> PREPARING -> RUNNING [heartbeat] -> VERIFYING -> SCORING
-> injected Direct/Codex/Multi production binding from `src/harnesslab/release/matrix.py`
-> physical attempt artifact `<logical-run>-a<attempt>`
-> manifest/slot identity validation
-> `src/harnesslab/experiment/queue.py:finish_run` -> terminal PostgreSQL state + artifact path/digest
-> `src/harnesslab/experiment/report.py:load_verified_experiment_evidence`
-> `src/harnesslab/experiment/report.py:build_experiment_report`
-> `src/harnesslab/comparability/engine.py:ComparabilityEngine`
-> `src/harnesslab/experiment/statistics.py:summarize_cell/summarize_pair`
-> deterministic `ExperimentReport` JSON/Markdown
```

Logical slot identity is stable across lease recovery; physical attempt identity is not. The
database coordinates work and references evidence, while the artifact bytes remain the detailed
source for capability results.

### 2.4 Judge calibration and evaluation

```text
User
-> `harnesslab judge calibrate`
-> `src/harnesslab/judgelab/cli.py:_calibrate`
-> `src/harnesslab/judgelab/plan.py:load_calibration_spec/resolve_suite/resolve_definitions`
-> `src/harnesslab/judgelab/plan.py:build_calibration_plan`
-> `src/harnesslab/judgelab/calibration.py:execute_calibration`
-> `src/harnesslab/judgelab/persistence.py:enqueue_calibration` -> PostgreSQL calibration/evaluation slots
-> `src/harnesslab/judgelab/persistence.py:pending_slots`
-> `src/harnesslab/judgelab/runner.py:JudgeRunner.run`
-> `src/harnesslab/judgelab/prompt.py:build_provider_request` -> existing `ProviderAdapter.invoke`
-> `src/harnesslab/judgelab/output.py:parse_judge_output`
-> immutable `JudgeEvidence`
-> `src/harnesslab/judgelab/persistence.py:persist_evidence_reference` -> PostgreSQL path/digest/outcome
-> `src/harnesslab/judgelab/report.py:build_judge_report`
-> `src/harnesslab/judgelab/runner.py:load_and_verify_evidence`
-> LABEL/SCORE/PAIRWISE metrics + `src/harnesslab/judgelab/models.py:resolve_authority`
-> suite-scoped qualification
-> report JSON/Markdown + completed calibration record
```

Hidden gold is used only after provider output is persisted. Pairwise slots include original and
swapped orders when the definition requires it. Judge infrastructure is durable but is not the
Phase G lease worker; the current calibration loop processes pending slots sequentially.

### 2.5 Final release semantic verification

```text
Authorized operator
-> `uv run ... scripts/verify_gate_k.py --final-release ...`
-> `scripts/verify_gate_k.py:verify_final_release`
-> rebuild/load corpus, accepted plan, stable candidate, Claim Map, BadCases
-> `src/harnesslab/release/final_verifier.py:resolve_authoritative_snapshot`
-> read-only PostgreSQL Experiment/Judge rows
-> trusted Matrix/recovery/J4 artifacts and native report reconstruction
-> `src/harnesslab/release/final_verifier.py:resolve_github_ci` for exact-head Full Release CI
-> `src/harnesslab/release/final_verifier.py:bind_final_head` creates in-memory SHA/CI overlay
-> `src/harnesslab/release/final_verifier.py:verify_semantic_final_release`
-> `src/harnesslab/release/reconciliation.py:verify_v6_snapshot` + BadCase/claim/pair/ablation/Judge checks
-> `src/harnesslab/release/final_verifier.py:_verify_final_checkout` checks exact clean committed candidate
-> `SemanticReleaseReceipt`
-> `src/harnesslab/release/contracts.py:tag_creation_authorized(bound_manifest, receipt)`
-> authorization result; Git tag creation remains an external, separately authorized mutation
```

The committed candidate intentionally cannot contain its own final SHA/CI binding. The semantic
receipt closes that cycle without adding a post-CI commit.

## 3. Authority model

| Authority class | Source of truth | What it decides | What it cannot override |
| --- | --- | --- | --- |
| Correctness authority | Hidden deterministic verifier (`tasks/verifier.py` for trusted qualification; isolated `DockerSandbox` verifier for untrusted run workspaces) | Task PASS/FAIL, bounded score, and per-check results. Trusted package qualification also rejects protected-file drift before invoking its verifier. | It does not decide provider reliability, comparative validity, causal effects, or Judge quality. Protected-file enforcement is not uniform across all lanes; see Section 5. |
| Curated semantic authority | Human Gold in `JudgeSuite.gold` with `GoldSource.HUMAN_L1` | Repository-curated answers where no deterministic L0 exists. | It cannot replace an available deterministic L0 value. It is never sent in Judge prompts. |
| LLM Judge | `JudgeEvidence` and suite-scoped `JudgeCalibrationReport` | L2 labels/scores/preferences, calibration metrics, and qualification for the named suite. | `judgelab/models.py:resolve_authority` prevents it from overriding L0 or L1. It cannot mutate Phase G outcomes or denominators. |
| Diagnostic evidence | Sanitized native events, Normalized Trace, workspace diffs, failure taxonomy, BadCase observations | How execution proceeded and which safe facts were observed. | Agent success text, exit zero, trace shape, or analyst prose cannot change verifier correctness. Root cause remains null/hypothesis unless supported. |
| Statistical evidence | `ExperimentReport`, `CellStatistics`, `PairStatistics` | Denominators, uncertainty, evidence tier, exact paired/descriptive results. | It cannot admit infrastructure failures into capability n, pool unrelated tasks to manufacture formal evidence, or override Comparability. |
| Comparability authority | `ComparabilityEngine.assess` over digest-bound `ComparisonFacts` | Whether a specific intent is `COMPARABLE`, `PARTIALLY_COMPARABLE`, or `NOT_COMPARABLE`; why; which differences are treatment versus control drift. | It cannot infer absent identity, decide task correctness, or turn association into causation. |
| Causal authority | A declared controlled ablation whose hard controls pass and whose evidence tier supports the claim | Only the observed effect under the declared treatment and supported scope. | Pair labels, Analyst narrative, favorable deltas, or `PARTIALLY_COMPARABLE` evidence cannot create causal authority. Released Core has zero controlled causal claims. |
| Attribution Analyst | Exact-value `FactAssertion`s over a bounded evidence catalog; otherwise `HYPOTHESIS` | Canonical restatement of cited facts and explicit questions requiring more evidence. | No evidence mutation, free-form verified prose, new statistics, hidden data, or causal upgrade. |
| Release authority | Reconstructed accepted sources + exact-head CI + clean checkout + `SemanticReleaseReceipt` + `tag_creation_authorized` | Whether the exact released commit is semantically eligible for tag creation. | No artifact filename, candidate alone, CI from another SHA, mismatched receipt, or documentation claim can authorize release. |

Immutable evidence is a cross-cutting integrity mechanism, not a correctness oracle. Trace is a
safe diagnostic projection, not private reasoning and not an instruction channel. BadCases are
frozen observed facts; their `root_cause: null` is deliberate.

## 4. Data and evidence model

### Identity graph

```text
TaskPackage
  task id + version + content digest
  -> workspace input digest
  -> verifier definition digest

ExperimentPlan digest
  -> cell identity (profile + harness config + route + treatment)
  -> slot id (cell + task identity + repeat)
  -> logical run id
  -> physical attempt id (`-aN`)
  -> lane manifest byte digest
       -> final workspace digest
       -> verifier artifact digest
       -> normalized trace digest (H-Lane)

JudgeCalibrationPlan digest
  -> evaluation slot id (cell + public case + repeat + order)
  -> evaluation id
  -> JudgeEvidence byte digest
  -> JudgeCalibrationReport digest

Release candidate digest
  + accepted Matrix/Pair/Ablation/Judge/BadCase/Claim identities
  + release-head identity
  + CI attestation digest
  -> bound release-manifest digest
  -> SemanticReleaseReceipt
```

| Identity | Canonical representation and relationship |
| --- | --- |
| Task | `TaskDefinition.id`, `version`, and `content_digest`; package location must end in `<id>/<version>`. The content digest covers the full package; verifier and workspace have separate digests. |
| Workspace | `WorkspaceReference.digest` identifies the pristine input. Lane manifests retain input and output digests. The isolated verifier manifest's input digest must equal the lane's final output digest. |
| Run | `ExperimentRunRecord.run_id` derives from `ExperimentRunSlot.slot_id`. `attempt_execution_id` adds `-aN` for each physical execution without changing logical identity. |
| Experiment/slot | Plan digest covers canonical timestamp-free plan JSON. Slot identity binds cell, task, repeat, lane, and paired-slot identity; database uniqueness prevents duplicate logical slots. |
| Model profile | `ModelProfile` separates requested model, protocol, canonical base URL source/route, reasoning settings, timeout, and credential reference. Observed model belongs to evidence, not the plan. |
| Harness | `CodexHarnessProfile` or `MultiHarnessProfile` binds runtime image/version, requested model, route, tool/MCP/network/prompt policy, and trace coverage. `profile_hash` must reproduce from the embedded profile. |
| Evidence digest | The queue stores the byte digest of `manifest.json`; readers recompute it before parsing. Manifest models also bind their nested workspace/verifier/trace identities. |
| Trace | H-Lane `normalized_trace_digest` binds `trace/normalized.json`; events have deterministic ordinals/types. Coverage is explicit (`FULL_STREAM`, `FINAL_OUTPUT_ONLY`, etc.). Native private transcripts are not a read-surface authority. |
| Judge | Calibration plan -> deterministic slot -> `evaluation_id` -> immutable `JudgeEvidence` -> persisted path/digest -> reconstructed report. Public case digest and hidden suite digest are separate. |
| BadCase | `BadCaseSlot.slot_id` binds a selected logical/physical failure, task/cell/repeat, factual verifier and safe trace/source facts, evidence refs, and canonical digest. Root cause is independently optional and null in the release. |
| Release evidence | `ReleaseEvidenceManifest` is strict, canonical, and stateful. `VERIFIED` bindings require identity+digest; non-results cannot carry them. The committed schema-2 candidate leaves dynamic head/CI bindings absent. |
| Semantic receipt | `SemanticReleaseReceipt` binds candidate digest, bound manifest digest, release head, CI run, and CI attestation digest. It is detached; it does not alter the released commit. |

### Execution-to-evidence lifecycle

1. Load and digest the task/profile/plan before execution.
2. Persist the immutable logical slot; claim it transactionally and assign a physical attempt.
3. Materialize a fresh subject-visible workspace; keep verifier/oracle outside it.
4. Execute one approved lane boundary and collect allowlisted public/trajectory facts.
5. Hash actual final filesystem state; run the isolated hidden verifier on that state.
6. Build a strict coherent lane model; write into a staging directory; scan for exact secrets;
   atomically rename to the final run directory.
7. Reopen `manifest.json`, extract comparison facts, validate it against the planned slot, and
   store only its path/digest and normalized outcome in PostgreSQL.
8. Report readers confine the path, recompute its digest, revalidate logical/physical identity,
   and only then calculate statistics or expose DTOs.
9. Recovery preserves the logical slot and primary evidence while giving each authorized physical
   attempt its own identity; the accepted V6 effective dataset records which attempt supplies the
   effective outcome.

## 5. Security boundaries

“Enforced” below means a concrete guard plus test evidence exists. Documentation-only statements
are labeled policy.

| Boundary | Documented policy | Actual code enforcement | Test evidence | Assessment |
| --- | --- | --- | --- | --- |
| Credential references | Profiles contain environment-variable names, never values. | `contracts/model.py:ModelProfile.credential_reference` and H-Lane profile fields require uppercase reference syntax; provider adapters resolve at invocation. `DirectModelRunner` and H-Lane runners scan prompts/workspaces/artifacts for exact runtime values. | `tests/test_contracts.py`, `test_cli.py`, `test_model_lane.py`, `test_codex_harness.py`, `test_registry_lite.py`, `test_runtime_config_hygiene.py`. | Enforced for modeled execution paths and exact known secret values. It is not a general semantic secret detector. |
| Provider route values | URL must be explicit/canonical and separate from credentials. | `ModelProfile.base_url_is_safe/route_is_safe`, `resolve_base_url`, `provider_route_identity`; custom M-Lane endpoints require `allow_custom_endpoint`; campaign HTTP clients key by route+credential reference. | `tests/test_contracts.py`, `test_provider_adapters.py`, `test_kb3_v6.py`, `test_phase_kb0.py`. | Enforced; runtime URL references are resolved only at execution. |
| Docker/filesystem isolation | Fresh non-root container, constrained mounts/resources, no host/Docker access. | `DockerSandbox._create_arguments` fixes `network=none`, read-only rootfs, cap-drop ALL, no-new-privileges, memory/CPU/PID limits, user `10001:10001`, tmpfs and explicit mounts; `_inspect_security` verifies effective state and Docker socket absence. H-Lane backends apply parallel fixed argv and inspection. | `tests/test_sandbox.py`, `test_codex_harness.py`, `test_multi_harness.py`, `test_runtime_config_hygiene.py`. | Enforced for Docker-backed runs; availability depends on a supported local Docker engine/preflight. |
| Network egress | Subject has no arbitrary Internet/host access; real Harness traffic is provider-scoped. | Normal sandbox and verifier use `network=none`. `ProviderScopedDockerBoundary` creates an internal isolated-gateway bridge, a separate outbound bridge, and a dual-homed CONNECT proxy restricted to one hostname:443; effective topology is inspected and cleanup verified. | `tests/test_phase_kb0.py`, `test_phase_kb0_review.py`, `test_runtime_config_hygiene.py`. | Enforced for the production binding when preflight succeeds; DNS/provider behavior remains external. |
| Verifier isolation | Hidden verifier/oracle must never be visible to subject and verifier input is read-only. | `TaskPackage.materialize` copies only workspace/context. `DockerSandbox._run_hidden_verifier_workspace` stages a digest-checked verifier separately; workspace and verifier mounts are read-only and verifier network is none. | `tests/test_task_package.py`, `test_task_verifier.py`, `test_sandbox.py`, `test_model_lane.py`, `test_codex_harness.py`, `test_multi_harness.py`. | Enforced. Host `execute_verifier` is only the trusted package-qualification path, not the untrusted subject boundary. |
| Protected paths and patch traversal | Declared protected public task files should retain their digests; package and patch paths must remain contained. | Module-level `tasks/package.py:resolve_package_path` and link checks confine task assets. Trusted-host `execute_verifier` calls `protected_file_violations`. `model_lane/patch.py` rejects absolute/traversal/symlink/case-folded protected targets and stages atomic changes. The isolated verifier path and H-Lane runners do not call `protected_file_violations` or otherwise consume `protected_digests`. | `tests/test_direct_patch.py`, `test_task_package.py`, `test_task_verifier.py`. | Enforced for package handling, trusted qualification, and strict M-Lane patches. **Not uniformly enforced:** Codex/multi-harness actual changes are inventoried, but generic protected-file rejection depends on the task's hidden verifier rather than a lane-level guard. |
| Artifact secret hygiene | No credentials/private reasoning in durable artifacts. | Exact-value redaction/scanning in `sandbox/artifacts.py`; lane runners scan all staged trees before atomic rename; trace collectors replace reasoning with `REASONING_PRESENT`; provider models exclude raw headers/body/private thinking. | `tests/test_sandbox.py`, `test_model_lane.py`, `test_codex_harness.py`, `test_multi_harness.py`, `test_workbench_api.py`, `test_analyst_e2e.py`. | Enforced for known runtime secrets and modeled private fields. Novel secrets not supplied to the scanner remain a residual risk. |
| Trusted artifact reads | A database path alone is insufficient. | `evidence/reader.py:trusted_artifact_path` resolves existing paths under configured roots; `load_verified_manifest` checks file digest and physical attempt id; trace read checks sibling containment and digest. | `tests/test_workbench_api.py`, `test_analyst_e2e.py`, `test_release_semantic_verifier.py`. | Enforced. Trusted-root configuration itself is an operator boundary. |
| Read-only Analyst | Analysis cannot mutate evidence or call execution systems. | `AnalystEvidenceRepository._ensure_read_only` executes `SET TRANSACTION READ ONLY` on PostgreSQL. It exposes six typed methods only; graph bounds are 8 decisions/12 calls; validated host code alone persists reports. | `tests/test_analyst_contracts.py`, `test_analyst_e2e.py`, `scripts/verify_gate_j.py`. | Enforced for PostgreSQL and exposed tool surface. Report output is the only intentional write. |
| Workbench execution boundary | Browser is an evidence consumer, not an executor. | Workbench routes call read/report/diagnosis functions; regression POST computes a comparison. No Workbench route calls lane/Judge executors. Registry/preflight APIs are separate control-plane scope and must not be confused with Workbench evidence routes. | `tests/test_workbench_api.py`, `test_bundled_workbench.py`, `test_registry_lite.py`. | Enforced by route inventory/tests. Some older docs saying “only Workbench POST” predate diagnosis export and need careful interpretation. |
| Release authorization | A clean exact head and real evidence are required. | Strict release models, trusted snapshot loaders, exact CI attestation, `bind_final_head`, `_verify_final_checkout`, semantic receipt, and `tag_creation_authorized`. | `tests/test_release_contracts.py`, `test_release_semantic_verifier.py`, `test_kc_release_reconciliation.py`, `scripts/verify_gate_k.py`. | Enforced. Tag creation itself remains outside code and needs operator authorization. |

## 6. Twenty-eight key engineering decisions

| # | Decision and repository evidence | Problem solved | Trade-off | What breaks if simplified |
| --- | --- | --- | --- | --- |
| 1 | CLI-first composition (`cli.py`, `__main__.py`) with a small FastAPI assembly (`api/app.py`). | Keeps execution and operator workflows scriptable while providing a read surface. | The CLI module is large and API/CLI capabilities can drift. | Hiding orchestration in UI handlers would make evidence-producing operations harder to audit and reproduce. |
| 2 | Domain Pydantic contracts are separate from SQLAlchemy records (`contracts/*` vs `db/models/*`). | Separates immutable meaning/validation from storage mechanics. | Mapping and duplicate fields require maintenance. | ORM convenience objects could leak persistence concerns into evidence identity and public APIs. |
| 3 | Task identity is a digest of strict, link-free package content (`tasks/package.py`). | Makes task, workspace, verifier, oracle, and context reproducible and tamper-evident. | Any legitimate byte change creates a new identity. | Path/name matching alone would allow silent verifier or fixture drift. |
| 4 | Baseline must fail and oracle overlay must pass (`tasks/validation.py`). | Detects vacuous tests and broken reference solutions before evaluation. | Requires maintaining a trusted oracle and two verifier runs per validation. | A task could be admitted even if every solution passes or no valid solution can pass. |
| 5 | Subject materialization excludes verifier and oracle (`TaskPackage.materialize`). | Prevents answer/test leakage. | More staging and separate verifier handoff. | A capable subject could read hidden correctness criteria or reference code. |
| 6 | Untrusted correctness runs in a separate networkless verifier container (`sandbox/runner.py`). | Prevents the subject runtime or its claims from controlling correctness. | Docker overhead and a stricter local prerequisite. | Running verifier inside the subject container would collapse trust boundaries. |
| 7 | Trusted code owns complete Docker argv and verifies effective configuration (`DockerSandbox._create_arguments/_inspect_security`). | Prevents callers or Docker defaults from silently weakening isolation. | Platform-specific complexity and substantial tests. | User flags or daemon drift could add mounts, privileges, ports, or network. |
| 8 | Credentials are references, resolved only at invocation (`ModelProfile`, provider adapters). | Keeps durable profiles, plans, logs, and Git secret-free. | Execution depends on correctly configured environment references. | Literal credentials would become part of fingerprints/artifacts or leak through diagnostics. |
| 9 | Provider evidence is allowlisted public output/identity/usage, not raw HTTP or reasoning (`model_lane/models.py`, `providers.py`). | Preserves useful operational evidence while reducing sensitive retention. | Harder postmortems when omitted raw detail would help. | Persisting raw transport data could expose headers, bodies, or private reasoning. |
| 10 | M-Lane accepts a strict JSON patch and applies it with traversal/protected-path/atomicity guards (`model_lane/patch.py`). | Lets a tool-less model modify a workspace without handing it a shell/filesystem. | Limits solution shape and requires patch serialization. | Free-form commands or direct writes would bypass protected-path and reproducibility controls. |
| 11 | Actual filesystem diff/digest outranks Harness-native file-change claims (`harness_lane/runner.py`, `multi_harness/runner.py`). | Prevents self-reported success or incomplete events from defining what changed. | Requires full tree inventory/copy. | A harness could claim edits that do not exist or omit edits that do. |
| 12 | Codex and multi-harness adapters share outcome/verifier concepts but retain protocol-specific collectors (`harness_lane/*`, `multi_harness/*`). | Preserves native protocol truth and explicit trace coverage. | Similar orchestration/persistence code exists twice. | Forcing all streams into one parser would invent equivalence between full JSONL and final-output-only evidence. |
| 13 | Run artifacts are staged, secret-scanned, then atomically renamed (`*_lane/runner.py`, `sandbox/artifacts.py`). | Avoids consumers seeing partial or known-secret-containing evidence. | Extra disk use and copy cost. | Partial manifests/workspaces could be mistaken for completed evidence. |
| 14 | Plans are canonical and timestamp-free; slots derive from identity (`experiment/plan.py`). | Enables idempotent enqueue and exact reproduction. | Operational timestamps live separately from plan identity. | Random UUID/timestamp plan identity would prevent deterministic replay and conflict detection. |
| 15 | PostgreSQL is both durable state and queue, with `FOR UPDATE SKIP LOCKED` leases (`experiment/queue.py`); Redis/Celery, Kafka/RocketMQ, and Kubernetes are deliberate exclusions (`docs/ARCHITECTURE.md`). | Coordinates bounded workers transactionally with plan/results while avoiding scale/operations systems for problems not established by current evidence. | Database coupling, less specialized queue tooling, and no claim of unbounded/distributed scale. | An in-memory queue would lose work; an added broker would create cross-system atomicity/operations complexity; a cluster stack would add an unevidenced operational boundary. |
| 16 | Heartbeat cadence is at most one-third of lease TTL; stale owners cannot finish (`ExperimentRunExecutor`). | Makes long external runs reclaimable without accepting writes after ownership loss. | Background heartbeat complexity and conservative failure behavior. | Duplicate workers could publish competing terminal results. |
| 17 | Logical run identity is stable; every physical attempt gets `-aN` (`attempt_execution_id`). | Preserves primary/recovery history and prevents artifact overwrite. | Readers must understand two identities. | Reusing the logical id would overwrite evidence and erase failure history. |
| 18 | Infrastructure, capability failure, and cancellation are separate (`experiment/outcomes.py`, `statistics.py`). | Avoids conflating system reliability with task capability. | Readers must inspect multiple denominators. | Counting outages as wrong answers biases capability; dropping them hides reliability. |
| 19 | Evidence tiers and repetition are evaluated per intended task (`statistics.py`). | Prevents pooled unrelated observations from manufacturing formal evidence. | Formal qualification is harder and reports are more complex. | A diverse small dataset could appear statistically mature through aggregation alone. |
| 20 | Comparability is pure, intent-specific, field-level, and fail-closed (`comparability/engine.py`). | Makes controls, treatments, missingness, and reason codes inspectable. | Large identity surface and conservative `NOT_COMPARABLE` results. | A favorable delta could be reported across mismatched task, route, model, budget, or verifier. |
| 21 | Requested model and observed model remain separate; missing observed identity is not copied (`ModelProfile`, H-Lane evidence). | Exposes aliases/routing/fallback uncertainty. | Missing identity can reduce claim strength even when execution succeeds. | Copying requested into observed would fabricate route evidence. |
| 22 | Direct-vs-Codex is not automatically Harness uplift (`ComparabilityIntent.HARNESS_UPLIFT`, released `NO_HARNESS_UPLIFT_CLAIM`). | Blocks causal branding when observed model/route/control evidence is incomplete. | Product narratives remain limited despite useful directional results. | Treatment and routing differences could be falsely attributed to the Harness. |
| 23 | Pairwise Judge evaluation uses order swaps and stable A/B canonicalization (`judgelab/plan.py`, `runner.py`, `report.py`). | Measures position inconsistency and verbosity bias. | Doubles pairwise calls and complicates aggregation. | LEFT/RIGHT bias could masquerade as judgment quality. |
| 24 | Deterministic L0 > human L1 > Judge L2 (`judgelab/models.py:resolve_authority`). | Keeps reproducible facts above preference-based annotations. | Judge disagreement is retained rather than “resolved” by the model. | A calibrated Judge could overwrite tests or curated gold. |
| 25 | Workbench reuses backend reports/statistics and exposes status-bearing missingness (`api/workbench_service.py`). | Prevents browser recalculation and zero/missing ambiguity. | Large DTO/service mapping layer. | Frontend formulas could drift from authoritative denominators and comparisons. |
| 26 | Analyst has exactly six typed reads, bounded graph steps, and host-validated exact-value facts (`analyst/*`). | Allows useful explanation without creating an execution agent or prose authority. | Less flexible than generic tools/RAG and currently only a fake backend is operational. | SQL/path/shell access or free-form facts could leak data, mutate evidence, or manufacture claims. Explicit no-RAG/no-multi-agent rationale is in `docs/ARCHITECTURE.md`. |
| 27 | Core stays Python; Java/TypeScript exist as evaluated toolchains, not Core services (`docs/ARCHITECTURE.md`). | Keeps schemas, orchestration, and analysis in one implementation runtime. | Python owns many concerns and some files are very large. | Adding a second Core runtime would duplicate contracts/deployment without an established adapter need. |
| 28 | Final release uses a committed stable candidate plus detached in-memory SHA/CI binding and receipt (`release/final_verifier.py`, `contracts.py`). | Avoids the impossible cycle of committing a final SHA into itself and invalidating exact-head CI. | Operational ceremony; receipt and bound manifest must match exactly. | Committing the binding would require another CI run; accepting candidate-only state would release unbound evidence. |

No repository evidence supports claims about team size, deadlines, developer preference, or why
specific module boundaries were authored in their present shape. Any such narrative is
**INFERRED — HUMAN MUST CONFIRM**.

## 7. Ownership risk map

### P0 — must personally understand before further development

| Area | Why critical / files to study | Expected interview questions | Debugging exercise |
| --- | --- | --- | --- |
| Task correctness and hidden-verifier polarity | A mistake invalidates every downstream result. Study `tasks/package.py`, `tasks/verifier.py`, `tasks/validation.py`, `tasks/models.py`, `sandbox/runner.py`. | Why baseline-fail/oracle-pass? Why is verifier failure not subject failure? How is oracle leakage prevented? | Take a fixture copy, alter a protected file and then corrupt verifier JSON; trace the two distinct fail-closed outcomes. |
| Sandbox, egress, and secret boundary | This is the primary untrusted-code and credential boundary. Study `sandbox/*`, `egress.py`, H-Lane Docker backends, `sandbox/artifacts.py`. | Why inspect Docker after create? Why is an internal bridge insufficient? What reaches the provider proxy? | Using fake endpoints only, inspect generated/observed container security and demonstrate host/path/network bypass rejection and cleanup. |
| Lane orchestration and immutable evidence | M/H result semantics feed every report. Study `model_lane/runner.py`, `harness_lane/runner.py`, `multi_harness/runner.py`, their models/traces. | What is trajectory versus outcome? Why can exit zero still fail? Why separate requested/observed model? | Follow one failed manifest from native capture through filesystem digest, verifier result, manifest, and normalized source taxonomy. |
| Durable Matrix queue and lease lifecycle | Concurrency bugs can duplicate or lose expensive work. Study `experiment/plan.py`, `queue.py`, `executor.py`, `evidence.py`, DB experiment models. | Why PostgreSQL queue? How does `SKIP LOCKED` work? What happens on lease loss/cancellation? | Run the keyless lease tests; pause heartbeat, reclaim a slot, and verify the stale owner cannot publish while attempt artifacts remain distinct. |
| Comparability, denominator, and statistics authority | These controls prevent invalid product claims. Study `comparability/*`, `experiment/outcomes.py`, `statistics.py`, `report.py`. | Why exclude infra from capability n? When is partial evidence usable? Why is n per task? | Mutate one hard control in a copied manifest and show the exact reason code and loss of formal pair eligibility. |
| Judge/causal/Analyst authority hierarchy | This is the central explanation boundary. Study `judgelab/models.py`, `runner.py`, `report.py`, `analyst/models.py`, `report.py`. | Can a Judge overrule tests? What proves a causal claim? How is Analyst prose constrained? | Create a Judge disagreement with L0 and a contradictory Analyst assertion; confirm both are retained/rejected without changing L0. |
| Final release semantic binding | Release correctness depends on reconstructing—not trusting—evidence. Study `release/reconciliation.py`, `final_verifier.py`, `contracts.py`, `models.py`, `scripts/verify_gate_k.py`. | Why detached receipt? What does Tag Guard deny? Why is exact-head CI necessary? | In fixture-only tests, mismatch CI head, one artifact digest, then receipt head; identify the independent refusal at each layer. |

### P1 — important ownership

- Workbench DTO/service boundary: `api/routes/workbench.py`, `api/workbench_service.py`,
  `api/workbench_models.py`, `evidence/reader.py`.
- Judge durable calibration and report reconstruction: `judgelab/calibration.py`,
  `judgelab/persistence.py`, `judgelab/report.py`.
- Registry/preflight configuration ownership: `registry/*`, `preflight/*`, and their API routes.
- Released V6/J4 reconciliation and frozen-history scripts under `release/` and `scripts/`.
- Gate structure and clean-checkout reproduction in `scripts/verify_gate_a.py` through
  `verify_gate_k.py` and `.github/workflows/`.

### P2 — can learn later

- Frontend component-level rendering and visual polish after the typed API semantics are owned.
- Product distribution/lifecycle conveniences under `src/harnesslab/productization`.
- Historical one-off freeze/analysis script internals once their immutable outputs and validation
  role are understood.
- Optional custom evaluation and diagnosis presentation details outside the released Core claims.

## 8. AI-generated code risk hotspots

These are maintainability/risk signals, not proof of AI authorship and not instructions to refactor
now.

| # | Evidence | Risk | Confidence | Change now? |
| --- | --- | --- | --- | --- |
| 1 | `release/v6_canary.py` is ~1,900 lines; `release/smoke.py` ~1,350; `release/throughput_qualification.py` ~1,320. | Orchestration, validation, persistence, and historical policy can become inseparable; local changes have wide regression radius. | High | No. Map responsibilities first; consider Phase L characterization seams. |
| 2 | `api/workbench_service.py` is ~1,150 lines and owns artifact confinement, report reads, DTO mapping, diagnosis, comparison, and readiness. | Unclear service ownership and accidental coupling between security reads and presentation. | High | No; use the audit to select bounded extraction candidates later. |
| 3 | `release/final_verifier.py` has accepted-V6 special branches for queued campaign status and historical `real_judge_smoke`, alongside generic release paths. | Exceptional historical facts can be mistaken for reusable policy or silently persist into a future release. | High | No; retain until a separately authorized release-contract migration. |
| 4 | `release/models.py`, `matrix.py`, and `smoke.py` branch on v2/v3/v4/v5/schema versions and encode exact plan IDs/counts. | Compatibility residue and current policy share models, raising change risk and cognitive load. | High | No; inventory which versions remain active before consolidation. |
| 5 | Direct, Codex, and multi-harness runners repeat run-id validation, staging, workspace/verifier copy, secret scan, canonical manifest write, and atomic rename. | Security fixes may land in one persistence path but not others. | High | No; first create cross-runner invariant tests and compare intentional differences. |
| 6 | Codex H-Lane and multi-harness H-Lane retain parallel adapters/backends/models despite similar lifecycle. | Duplicate abstractions can drift, but premature unification could erase protocol/trace truth. | Medium | No. Document shared versus protocol-specific invariants before any merge. |
| 7 | `scripts/verify_gate_k.py` is ~950 lines and carries a large explicit list of critical test names plus frozen commit/digest/history facts. | Test-name coupling and historical checks make benign reorganization expensive; purpose of individual constants may be obscure. | High | No; release gate is protected until a new audited contract exists. |
| 8 | Identity is repeated across plan JSON, DB columns, lane manifest, `ComparisonFacts`, reports, and release bindings. | One new field requires coordinated changes and can produce confusing mismatch categories. | High | No; create an ownership/schema crosswalk before changing identity fields. |
| 9 | Documentation drift: `docs/BADCASES.md` ends by saying K-C is not started; `docs/RELEASE_EVIDENCE.md` opens in pre-release tense; `docs/ARCHITECTURE.md` says the only Workbench POST is regression while `routes/workbench.py` also has diagnosis BadCase export. | Interviewers/operators may confuse immutable historical statements with current product state. | High | Not in L.1; schedule a documentation-truth pass that preserves historical provenance. |
| 10 | Many release/source files contain exact external profile IDs, cell IDs, digests, counts, and permitted aliases. | Brittle coupling is intentional for evidence freezing but dangerous if copied into general product logic. | High | No; classify each constant as frozen evidence versus reusable configuration first. |
| 11 | Gate and release tests frequently assert source text, exact command shape, and named critical tests. | Implementation artifacts may become de facto architecture, discouraging safe refactoring even when semantics remain stable. | Medium | No; identify which are security invariants before relaxing any assertion. |
| 12 | The Workbench/read-only narrative spans Workbench, Registry, preflight, diagnosis export, and custom-eval routers in one FastAPI app. | “Read-only UI” can be overgeneralized to the entire API even though other routers have controlled mutations. | High | No; clarify router-level trust boundaries before feature work. |

Hotspot count: 12.

## 9. Technical-debt candidates

Bounded ranking; none is authorized for repair in L.1.

| Priority | Candidate and evidence | Impact | Likely repair scope | Regression risk | Recommended Phase L action |
| --- | --- | --- | --- | --- | --- |
| P0 | Resolve the H-Lane protected-file enforcement gap or explicitly narrow the contract. H-Lane runners and the isolated verifier path do not consume `protected_digests`; only trusted-host qualification and M-Lane patching apply the generic guard. | A Harness can change a declared protected public file without a generic `PROTECTED_FILE_VIOLATION` unless that task's hidden verifier independently detects it. | Either bind protected digests into isolated verification for every lane, or document/test a deliberately lane-specific rule. | High | L.2 decision plus cross-lane characterization tests before any implementation. |
| P0 | Define one invariant checklist for all lane artifact writers; current logic is repeated across three runners. | Secret/integrity fixes can drift. | Shared internal helper or protocol plus characterization tests, without unifying native collectors. | High | L.2 discovery: diff the three writers and first add invariant tests. |
| P0 | Separate reusable final-release semantics from accepted-V6 exceptions in `final_verifier.py`. | Future releases may inherit one-off queued/Judge-field exceptions. | Explicit accepted-evidence adapter with unchanged receipt contract. | Very high | Architecture decision record and fixture matrix before code change. |
| P0 | Establish an authoritative “current versus historical” documentation rule. | Current ownership guidance conflicts with stale phase text. | Update top-level docs and clearly mark frozen historical artifacts; no evidence rewrite. | Medium | Documentation-only phase with path-by-path assertions. |
| P0 | Decompose `api/workbench_service.py` ownership while retaining one trusted artifact reader. | Security projection, statistics, and DTO concerns are hard to review together. | Internal query/readiness/diagnosis services and stable route DTOs. | High | Capture route contract tests and data-flow diagram before extraction. |
| P1 | Inventory version branches across release models/control planes. | Cognitive load and accidental cross-version policy changes. | Compatibility matrix; retire only versions no longer required for immutable history validation. | Very high | No deletion until release-history consumers/tests are enumerated. |
| P1 | Replace gate test-name coupling with a structured critical-test manifest if semantics can remain identical. | Renaming/reorganizing tests can invalidate gates for non-semantic reasons. | Gate runner + machine-readable manifest + meta-tests. | High | Prototype outside Gate K, then security review. |
| P1 | Document logical run versus physical attempt identity in API/operator surfaces. | Recovery/debugging errors can target the wrong artifact. | DTO/docs naming and non-breaking aliases. | Medium | Add an operator debugging guide before schema changes. |
| P1 | Make the router-level mutation/read boundary explicit in API docs. | “Workbench is read-only” may be misread as “all FastAPI routes are read-only.” | Route inventory and capability matrix for Workbench/Registry/preflight/custom-eval. | Low | Documentation and route meta-test. |
| P1 | Centralize exact-secret scanning policy and residual-risk documentation. | Each runner knows values differently; exact matching misses unknown secret forms. | One policy object passed through runtime and artifact writers; preserve no-value serialization. | High | Threat-model first; do not add heuristic logging of suspected secrets. |
| P1 | Characterize Judge calibration durability/concurrency. | Judge slots are persisted but the calibration loop is sequential and lacks Phase G leases. | Decide whether current scale is sufficient; if not, design a Judge-specific lease model. | High | **INFERRED — HUMAN MUST CONFIRM** demand for distributed Judge work before implementation. |
| P2 | Reduce `cli.py` composition size without changing commands. | Navigation and ownership are harder than necessary. | Move release command definitions into existing domain CLI modules; preserve Typer registration. | Medium | Snapshot help/output before mechanical extraction. |
| P2 | Add a generated identity crosswalk for plan/DB/manifest/report/release fields. | Onboarding/debugging requires reading several models. | Documentation generator or schema introspection; no runtime source of truth change. | Low | Good early ownership tooling task. |
| P2 | Clarify the trusted host verifier versus isolated verifier names. | Readers may mistake `execute_verifier` for the production untrusted boundary. | Naming/docs only initially. | Medium | Document call sites; rename only with full gate coverage. |

Technical-debt candidate count: 14.

## 10. Human ownership checklist

Do not check these from documentation alone. Complete them only after drawing, tracing, and
debugging the released system personally.

- [ ] I can draw the architecture from CLI/API input through PostgreSQL and immutable evidence.
- [ ] I can trace model-only task execution from profile resolution to hidden verifier.
- [ ] I can trace Codex H-Lane execution, including egress, trace sanitization, and filesystem authority.
- [ ] I can trace Matrix plan -> enqueue -> lease/heartbeat -> lane -> artifact -> report.
- [ ] I can trace Judge suite -> slot -> public prompt -> evidence -> gold comparison -> qualification.
- [ ] I can trace stable release candidate -> persisted snapshot -> exact-head CI -> receipt -> Tag Guard.
- [ ] I can explain correctness, diagnostic, statistical, causal, and release authority without notes.
- [ ] I can explain why deterministic L0 outranks Human Gold L1 and Judge L2 when present.
- [ ] I can locate `FOR UPDATE SKIP LOCKED`, lease expiry, heartbeat, cancellation, and stale-owner guards.
- [ ] I can explain why infrastructure outcomes are visible but outside capability denominators.
- [ ] I can explain requested model versus observed model and the consequence of missing identity.
- [ ] I can explain `COMPARABLE`, `PARTIALLY_COMPARABLE`, and `NOT_COMPARABLE` for a named intent.
- [ ] I can explain why the released Direct/Codex pair supports no Harness-uplift claim.
- [ ] I can explain the scope limits of J4 and why zero L0 overrides is an invariant.
- [ ] I can explain each of the three frozen BadCases, including why every root cause remains null.
- [ ] I can explain logical slot identity versus physical attempt identity during recovery.
- [ ] I can debug a failed run from PostgreSQL row -> trusted path -> manifest digest -> verifier/trace evidence.
- [ ] I can show where provider credentials are resolved and prove they are absent from durable profiles/artifacts.
- [ ] I can show the subject/verifier network and mount difference from code and Docker inspection evidence.
- [ ] I can explain why PostgreSQL was sufficient and why Redis/Celery/Kafka/Kubernetes were not added.
- [ ] I can explain why the Core implementation remains Python while evaluated tasks span three languages.
- [ ] I can explain why generic RAG/multi-agent tooling is outside the Core Analyst boundary.
- [ ] I can identify which release compatibility branches are historical and which are active policy.
- [ ] I can state the residual risks that exact-secret scanning and trusted-root configuration do not eliminate.

## Audit conclusion

The released Core has a coherent authority spine: deterministic task truth is produced only after
fresh-workspace execution and isolated verification; durable orchestration preserves logical and
physical identities; immutable manifests are revalidated before statistics; Comparability gates
strong claims; Judge and Analyst remain subordinate evidence layers; and release authorization
reconstructs the whole chain at an exact Git/CI head. The principal ownership risk is not a missing
architecture component but the density of frozen release history, duplicated evidence-writing
paths, and broad modules that require careful characterization before refactoring.
