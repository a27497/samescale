# Private local planning (Phase 1)

Use a private loopback API with the locked repository toolchain and your own separate PostgreSQL
workspace migrated through `20261010_0011`. This delivery does not migrate an existing service or
historical database. The unchanged Compose distribution does **not** automatically mount a trusted
source/policy or Docker socket; this opt-in Phase-1 workflow was verified on a host API. Public Demo
and getsamescale.com are separate surfaces.

1. Prepare a snapshot task package under an approved root: `<task-id>/<version>/task.yaml`,
   instruction, Workspace, verifier and oracle following [Task Packages](TASK_FORMAT.md).
   Import accepts local folders only, not remote URLs, repository checkout, uploads or arbitrary
   commands. Remove `.git`, `.env`, credential files, symlinks/hardlinks and special files. Limits:
   4,000 ordinary files, 64 MB total, 8 MB per file; managed-store reads have a 40,000-file/512 MB
   envelope. UI discovery lists up to 100 candidates per approved root, at the package's two-level
   layout. A root outside the allowlist cannot be selected by an API path.
2. Keep a separate server-owned managed store and external existing qualification/validation JSON.
   The latter must be full `TaskQualification` and `TaskValidationResult` documents with exact task,
   verifier, baseline Workspace and oracle-overlay Workspace bindings; Custom status QUALIFIED,
   nonempty baseline-fail/oracle-pass SUBJECT_RESULT checks and matching qualification evidence.
   Put these records and the policy outside every subject root and the managed store. They must
   be ordinary, current-user-owned files without group/other write permissions (for example 0600).
   Paths must be canonical absolute paths without symlink ancestors. Roots/store cannot overlap.
   This is operator trust of prior observations, not automatic provenance attestation. Do not create
   synthetic qualification for a real task. Phase-1 tests use explicitly synthetic records only.
3. Create a private policy matching the following schema, replacing the illustrative paths and all
   digests with real existing identities. Compute canonical JSON digests using the existing
   `registry.models.canonical_digest`; use `TaskQualification.qualification_identity` for that record.
   Obtain an approved cached image ID with read-only `docker image inspect <existing-ref> --format
   '{{.Id}}'`; no image pull, CLI launch or runtime upgrade is implied.

```json
{
  "schema_version": 1,
  "source_roots": {"engineering": "/private/operator/task-snapshots"},
  "managed_store": "/private/operator/product-custom-store",
  "runtime_images": {
    "harnesslab-phase-e-codex:0.149.0": "sha256:<approved-local-image-id>"
  },
  "admissions": [{
    "task_identity": "sha256:<exact-task-content-digest>",
    "qualification_file": "/private/operator/admission/task-qualification.json",
    "qualification_identity": "sha256:<qualification-identity>",
    "validation_file": "/private/operator/admission/task-validation.json",
    "validation_identity": "sha256:<validation-document-digest>"
  }]
}
```

4. Configure `DATABASE_URL`, `HARNESSLAB_LOCAL_TASK_POLICY` (the policy file) and an operator secret
   of at least 32 characters in `HARNESSLAB_LOCAL_CONFIGURATION_TOKEN` on the private host process.
   Reuse the existing Registry model/Harness configuration and credential reference mechanism;
   enter no Provider secret in this planning form. The compatible configuration must be enabled,
   have a valid endpoint fingerprint and a present credential reference. No connectivity or balance
   check occurs. The approved image ref/version is whatever the selected registered Codex definition
   declares; the example preserves the existing 0.149.0 registry runtime, not a claim about any
   historical 0.153.4 case or a runtime upgrade. Image ID is verified, CLI binary version is not run.
5. Build the frontend with `npm ci --no-audit --no-fund` and `npm run build` in your own checkout,
   or use an explicit isolated `--outDir`. Set `HARNESSLAB_WORKBENCH_DIST` to those built assets and
   use `uv run --locked harnesslab serve --host 127.0.0.1 --port <private-unused-port>`.
   Existing `samescale`/`harnesslab` names and `HARNESSLAB_*` identities remain compatible. Docker
   metadata access is required for preflight, not a mounted execution workspace or started Worker.
6. Open `/plans`, unlock using the operator token, choose/import/reinspect a trusted package, select
   one Codex configuration and provide a name plus explicit budgets. Inspect admission and preflight
   checks, then tick the plan-only confirmation and save. After refresh/restart, unlock again to read
   the saved plan. Token lives in component memory, not URL/default Axios headers/browser storage.

Preflight is valid for 15 minutes and is rechecked before first save. Task, source, admission,
policy, provider endpoint/reference availability, model/Harness revision, image ID or application
code changes invalidate it. A lost save response can retry the same UUID key; the exact stored plan
is returned. Reusing that key with a different receipt gives 409. Saved plans/receipts reject
UPDATE/DELETE in migrated PostgreSQL; integrity failure never silently regenerates a replacement.
Duplicates return the historical plan even after drift; they create no new authorization. Source
changes require a new task version/import; an immutable task identity cannot be overwritten.

`STALE` describes current drift alongside an unchanged original. `UNCHANGED_RECHECK_REQUIRED`
still requires future execution rechecks and separate authorization. Missing prior validation is
NOT_VERIFIED; structural PASS is never a behavioral PASS. For this phase, `/execute` is always 403,
Run/Episode counts stay zero, and no Worker, subject, Provider, Judge or Verifier starts.
Wall time describes existing runner timeout support that a later worker must apply; USD/token
values are reference estimates with no hard cap/reservation. See the concrete
[Phase-2 interface gaps](PROJECT_BLUEPRINT.md#phase-2-的具体接口与缺口规划不启动).
