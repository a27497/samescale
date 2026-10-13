# Restricted GCP QA deployment — actual observations, 2026-10-13 (Asia/Shanghai)

Base main `a0ab9e8d5170d99703781046e7b853063c8e6891`; independent branch
`codex/gcp-auto-deploy-20261013`. Product code, original dirty checkout and frozen evidence unchanged.
Only the existing samescale-grok-qa API and one-off migrate are operated; no GitHub deployment run,
PR merge, PostgreSQL/gateway/tunnel restart, firewall change, other project mutation or model call.

## Actual server runs

- Main CI authority verified against Fast run **38293616560** and offline run **38293616478**;
  complete main push attempts/jobs successful before building.
- Dedicated restricted SSH login deployed exact main successfully, source label equal to the full
  SHA above. Server-local Dockerfile build, real `alembic upgrade head` one-off and gateway health
  completed. The database was already at this code's head: this is not a schema compatibility UAT.
- Successful API image:
  `sha256:f1f5b8fd10293d30c00ce30ca7cea4d4b87a48bea7ed9ece447aab29575d0814`.
  A few startup **502** retries were followed by real status/database **ok**; no zero-downtime claim.
- Final installed-code health-failure rehearsal built the same source with a distinct rehearsal
  label, candidate image
  `sha256:65ece0283e36fcc553186ff7dadf86860a29dc8d4596414687948d6f0078acb3`.
  The deliberately nonexistent gateway probe returned actual **403** on three attempts. This is
  injected probe failure, not a claim that the normal health endpoint or product business failed.
  Production health-validation logic is reused. Script returned **1**, switched back to **f1f5b8...**,
  and confirmed the normal `/api/health` response `status=ok, database=ok`.
  Successful deployment receipt was not promoted by the failed candidate; no pending transaction.
- API address stayed **172.24.0.4**. No nginx reload/restart was needed. **57 protected container
  identities/images/start-times/states** match the pre-operation snapshot, including the existing
  PostgreSQL, gateway, tunnel, lecturelens and other PostgreSQL instances. Old images remain.
- A second successful SSH request reported `ALREADY_HEALTHY`, without API replacement.
- Holding the server deployment lock refused a concurrent SSH request before deployment.
- New deploy account: primary deploy group only, no Docker/dev/general sudo. Actual SSH shell,
  rollback, flag/injection requests denied; generic sudo/Docker/api.env/Compose reads denied.
- Synthetic invalid GitHub token over SSH stdin was not echoed; request failed before deployment,
  API container identity unchanged. No real GitHub token was read/reused for this test.
- Installed root code byte-compared equal to branch host/CI-gate sources. Private key was generated
  once under a 0700 dev directory, file 0600. No private key content printed or committed.

Public key fingerprints (not private values):

- Dedicated deployment public key: `SHA256:EgFp2BIU2QpbR7t45REJYr0Do9UFvv3L0cxZP5w6dTk`.
- Existing server Ed25519 host key: `SHA256:ak2eplJaOpUnbOpPW9b+zv6XEmtNzvoW4HKeaIXNNC0`.

## Local verification

- Offline deployment contracts: **17 unittest cases PASS**. Includes authority, latest CI attempt,
  required jobs/no skips, fork/PR/stale refusal, migrations-before-switch, failed migration retaining
  old API, partial activation/failed health/receipt failure rollback, failed rollback remaining an
  error, byte-preserving image-only rewrite, actual command construction limited to api/migrate,
  SSH negative commands, environment/concurrency/trigger contract.
- Related deployment/CI/routing/S3 contracts: **63 PASS**, **34 subtests PASS**, 4.23s.
- Whole repository Ruff check / format **PASS**, **857 files**; strict mypy **438 sources PASS**.
- Shell and workflow YAML syntax PASS. Documentation links and whitespace checked before pushing.
- Original dirty diff and status preserved; protected product/frozen trees have no diff from base.

Exact final pushed SHA's PR CI is checked separately and linked in the task handoff. This committed
record does not anticipate its own future CI verdict. No environment existed at inspection; no
GitHub environment, secret, variable or repository setting was created/changed in this task.

## Limits

The actual GitHub-hosted runner → SSH deployment chain is unexecuted: this workflow is not on main
and the user has not configured the environment/Secrets. PR-only deployment-contract jobs never
receive SSH secrets or contact the server. No production workflow/manual dispatch was triggered.
Migration failure was validated with offline controlled operations; no failing live SQL/schema
upgrade was attempted. Application-image rollback does not undo forward schema changes. Manual
rollback command, host crash/SIGKILL recovery, disk exhaustion, daemon failure and incompatible
schema rollback were not separately exercised. [Setup, operations and risks](../../GCP_DEPLOYMENT.md).

Review artifacts (safe stage logs, account/lock/token-boundary receipts, container snapshots,
final image state and local/remote CI receipts) are under
`/home/dev/samescale-deliverables/gcp-auto-deploy-20261013/`.
Raw build/migration logs and Compose snapshots remain root-only under `/var/lib/samescale-deploy/`;
they are not copied into the repository or public QA record.
