# Frozen mixed evaluation: SWE-bench Verified 25 + HumanEval 5

This successor protocol supersedes the **unexecuted** 30-task HumanEval full stage. Original
three-task HumanEval bytes, results and archive are retained. The current user explicitly requires
the product REAL_CODEX gate: it is unconditionally closed. Both new mixed `pilot/full` commands
and the historical standalone paid entrypoint reject before reading credentials or starting a
subject. No environment switch, direct CLI, alternate provider, auth-directory mount or worker
bypass is permitted. New real attempts require the existing gate's actual prerequisites and a
separately admitted task/runtime/route/one-attempt authorization; this PR does not open that gate.

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
contains only source, config/IDs/digests and small receipts. No developer auth file or private
reasoning is read by this stage. HumanEval's original MIT notice stays in its original archive.

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

Since REAL_CODEX is closed, SWE Agent claim/acceptance, Agent time, tokens, cost and gap are
**NOT_RUN / unknown**, never 0%/100% or inferred from the gold controls. New-stage model calls are
zero. Do not extrapolate small HumanEval cost to 25 repository tasks. Mixed total token/fee/time
estimates remain unknown until genuine gated SWE observations exist. Report the old HumanEval
control results separately from SWE, retaining their original scopes.

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

Before any future Subject dispatch, export only issue text and a fresh base-commit working tree,
reinitialize its Git history and remove oracle/evaluation files: do not expose gold/test patches,
future Git objects, upstream eval scripts or accepted control logs through an instance image.
Independent verification applies the frozen final patch in a separate no-network container.
No such real dispatcher is implemented/admitted by this keyless preparation. Real pilot and full
campaign remain separate permission boundaries; after three admitted SWE attempts, report actual
per-task results/time/usage/cost and setup failures, then **STOP for user confirmation**.


## Observed preflight and offline review

[Successor receipts](../../docs/evidence/swe-mixed-preflight-20261014/README.md) retain all first
failures and concrete corrections. `--preflight-label` writes another namespace without overwriting
records; `--instance-id` may only select an already-fixed pilot identity for a documented correction,
never introduce a replacement. Reporting-only `PYTEST_ADDOPTS=-rA --color=no` is supplied to control
containers, but tox does not forward it for the observed Sphinx image, which remains not admitted.
Model/hidden-test semantics and membership stay fixed. Saved `replay --preflight-label NAME` verifies
inputs/case inventories and qualification without Docker/upstream tooling/models/credentials.
