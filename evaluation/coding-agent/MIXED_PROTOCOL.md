# Frozen mixed evaluation: SWE-bench Verified 25 + HumanEval 5

This successor protocol supersedes the unexecuted 30-task HumanEval full stage. The user's
clarification explicitly authorizes three **external Codex CLI** attempts, following the original
HumanEval route. SameScale's product REAL_CODEX gate remains closed and unchanged; this campaign
is not product runtime enablement. Saved outputs enter the existing bounded external intake and
separately authorized independent Verifier. Existing product-gated entrypoints remain denied.
Original selection and original HumanEval evidence stay fixed. Full execution is NOT authorized
until the three new SWE observations and mixed forecast have been reported and confirmed.

## Selection fixed before execution

[mixed-config.json](mixed-config.json) enumerates all 30 identities and fixes:

- SWE-bench Verified revision `c104f840cc67f8b6eec6f759ebc8b2693d585d4a`, test split (500 records),
  compressed Parquet SHA-256 `a45b1fe4e2f0c8390b2b2938ac83e92ed5979000856808f3679c07812e9e6dcd`.
- A priori repository strata: `astropy/astropy`, `sphinx-doc/sphinx`, `sympy/sympy`, `psf/requests`,
  `pytest-dev/pytest`. Standard-library or ordinary Python repository tasks with upstream Linux
  Docker recipes/images and permissive primary source licenses; five tasks per repository limits
  domination by one project. This deliberately excludes Django and is not representative of the
  full benchmark's repository mix or difficulty distribution.
- Require nonempty problem, gold patch, test patch, base commit and FAIL_TO_PASS. Within each
  stratum take the first five by ascending `sha256("samescale-swe-mixed-v1:" + instance_id)`, then
  globally order those 25 by the same hash. Pilot: scan that order and take the first three from
  distinct repositories. No test/model outcome or environment-success filter changes membership.
- Pilot IDs: `astropy__astropy-8872`, `sphinx-doc__sphinx-8120`, `sympy__sympy-20916`.
- HumanEval: retain original 122, 33 and 153 as original observations, with exact original summary
  digest; select 121 and 25 as the next two in the original predeclared hash order. Do not rerun
  the first three or count them as newly executed through REAL_CODEX. Their earlier standalone
  capture does not prove product-gate compliance or serving-model identity.
- Pin each published Linux amd64 image by its OCI manifest digest, never run `latest` by tag.
  All 25 manifests were found before Docker controls. Image availability is not local admission:
  only the three pilot environments receive base/gold controls in this bounded stage; other
  22 remain untested locally. Failed environments remain selected and reported, not replaced.
- SWE-bench upstream harness **4.1.0**, immutable commit
  `726c5461e2ef52d83cf1ea2107870a8bb3328d57`, retains its original-dataset TestSpec and grader.
  The newer harness's task-repository format is not silently substituted. Upstream dependencies
  are installed only in a separate external tooling environment from [swe-tooling.lock](swe-tooling.lock);
  SameScale's product stack and dependency locks are unchanged.

## Licenses and evidence placement

The [upstream harness](https://github.com/SWE-bench/SWE-bench/blob/726c5461e2ef52d83cf1ea2107870a8bb3328d57/LICENSE)
is MIT licensed. The [Verified data release](https://huggingface.co/datasets/princeton-nlp/SWE-bench_Verified/tree/c104f840cc67f8b6eec6f759ebc8b2693d585d4a)
card has no separate explicit license field; do not claim such a field exists. Use the authors'
public SWE-bench release in its project context and retain the original release/source terms.
The individual task source/tests remain under the original repository licenses: Astropy BSD-3,
Sphinx BSD-2, SymPy BSD-3, requests Apache-2.0, pytest MIT, with all embedded-software notices
retained. Base-commit license text hashes/URLs are in the config. GitHub's automatic NOASSERTION
is preserved separately from the reviewed primary license; it is not treated as a missing grant
where the text itself states redistribution/use permission. Do not relicense embedded code,
issue-text contributions, data, binaries or base images as SameScale-owned material.

Raw dataset, gold/test patches, logs, copied license notices and tooling stay outside Git. Git
contains only source, config/IDs/digests and small receipts. The external CLI reads only the existing credential reference in its disposable runtime;
credentials and private reasoning are never persisted in campaign evidence. HumanEval's original MIT notice stays in its original archive.

## Keyless environment admission and failure rate

For each fixed pilot ID, attempt its image pull once, record inspected image identity, then run
two independent fresh Docker containers at the exact base commit: baseline with upstream hidden
test patch, and gold with upstream gold patch plus hidden tests. Use upstream eval-script generation
and log parsing, not an invented passing signal. Require positive parsed checks, every required
FAIL_TO_PASS failing in baseline, all PASS_TO_PASS passing in baseline, and all required checks
passing for gold. Missing/zero checks, timeout, setup/package/patch failure or missing required
statuses fails admission. These are **reference controls**, not Agent pass rates or task attempts.

Control containers have no network, credentials, Docker socket or host source mount. Only an
external case containing the eval script/gold patch is mounted read-only. Resource limits are
4 GiB, 2 CPUs, 512 PIDs, dropped capabilities and no new privileges. Upstream's root-in-container
writable overlay is retained because its setup/test script modifies the checkout and editable
install; this is an environment control, not a declaration of product Verifier/Subject admission.
`PIP_NO_INDEX=1` forbids index retrieval; no hidden test/patch ever enters an Agent container.
Each control has a 600s wall limit; pull has its own 600s limit. Only campaign-created containers
are removed. Image caches are external artifacts, not a cleanup target.

First-attempt environment failure rate is `failed fixed-pilot environments / 3`. Record setup
duration separately from Agent and verifier timing. A later concrete correction would produce a
new receipt, retain the first failure and never change membership or erase the initial rate.
If preparation itself prevents an attempt, report attempted/planned and NOT_RUN separately.

SWE self-report, independent acceptance and costs come only from the real external attempts.
Reference controls do not establish Agent results. The 30-task forecast uses separate SWE and
HumanEval sample means, with cached and uncached API-equivalent scenarios and explicit remaining
setup uncertainty. Requested model identity is preserved; serving identity and actual subscription
billing remain unverified. Stop after the three SWE results, awaiting full-stage confirmation.

## Reproduction

First prepare an isolated tooling environment outside the repository. No model is installed or called:

```bash
uv venv --python 3.12.14 /absolute/external/tooling-venv
uv pip install --python /absolute/external/tooling-venv/bin/python -r evaluation/coding-agent/swe-tooling.lock
bash evaluation/coding-agent/run-swe-preflight.sh /absolute/new/external/campaign /absolute/external/tooling-venv/bin/python /absolute/original/pilot-summary.json
uv run --locked python -m scripts.swe_mixed_eval gate
```

The three-task original HumanEval bundle must be supplied from its separate storage and retain the
configured digest. During a new preparation the pinned dataset is fetched and decoded using the
external toolchain; all membership is recomputed and compared with the committed list. It fails
closed rather than selecting replacements. Keyless preparation does not authorize `pilot/full`.
Those commands report `REAL_EXECUTION_BLOCKED` and exit 3, even with enablement environment vars.

External execution uses `scripts.swe_external_pilot`: only the issue and a fresh exported
base-commit tree with reinitialized Git enter the Subject. A derived runtime removes upstream
checkout/history/setup scripts, retaining dependencies; hidden patches and accepted control logs
are never mounted. Each attempt has a 900s timeout, 4 GiB/2 CPU bound, no automatic retry, and a
provider-only egress proxy. CLI/model/effort match the HumanEval profile.

Campaign acceptance uses `scripts.swe_external_acceptance`: prepare a fixed trusted patch-task
wrapper, warm baseline dependencies/compiled extensions in a separate pinned image, and actually
observe baseline-fail/gold-pass under the **unchanged** existing 128 MiB/0.5 CPU/30s Verifier.
The UTF-8 delivery is `solution.patch`; the full final repository is retained separately. The
campaign-specific trusted verifier applies it to the immutable baseline, restores hidden tests,
executes every frozen required ID (Astropy explicit pytest IDs; Sphinx original file/collection
order with short traceback/no captured-output reporting; SymPy original test script with its path
helper materialized in the candidate tree), using upstream 4.1 parser
semantics. Required membership/thresholds are unchanged; unrelated aggregate failures remain
in the original control logs. This bounded resource adaptation receives fresh baseline/gold controls. Non-required failures remain in logs.
This is a CUSTOM task adapter, not general patch import or Official benchmark authentication.
Exact TaskStore admission, existing `service.ingest`, `verify_workspace`, export and offline
replay are used, without a browser execution API, gate modification, new runtime or Agent rerun.

## Observed preflight and offline review

[Successor receipts](../../docs/evidence/swe-mixed-preflight-20261014/README.md) retain all first
failures and concrete corrections. `--preflight-label` writes another namespace without overwriting
records; `--instance-id` may only select an already-fixed pilot identity for a documented correction,
never introduce a replacement. Reporting-only `PYTEST_ADDOPTS=-rA --color=no` is supplied to control
containers, but tox does not forward it for the observed Sphinx image, which remains not admitted.
Model/hidden-test semantics and membership stay fixed. Saved `replay --preflight-label NAME` verifies
inputs/case inventories and qualification without Docker/upstream tooling/models/credentials.


Final reporting correction: Sphinx's generated command has `tox --current-env -epy39 -v -- ...`.
The adapter validates exactly one such command and adds **only** `-rA --color=no` after its argument
separator so pytest receives the reporting flags. The upstream eval script is retained alongside
the projection; hidden tests, instance IDs and required-check rubric are unchanged. This is now
automatic for the Sphinx repository, making the one-command keyless reproduction cover the latest
reporting contract. CLI `--direct-pytest-reporting` supports a labeled same-ID diagnostic, never a
replacement task. Latest Sphinx receipt is `preflight-sphinx-direct-fixed`; all prior receipts and
the first compressed archive remain unchanged. Required control checks now pass for all three.

## Real external pilot completed

[New real observations, costs, forecasts and artifact receipts](../../docs/evidence/swe-external-pilot-20261014/README.md)
supersede the historical blocked interpretation. Product REAL_CODEX remains unchanged/closed.
The new API-equivalent total is $0.4314104; self-report 3/3, independent acceptance 2/3.
Full stage remains NOT_RUN pending user confirmation.
