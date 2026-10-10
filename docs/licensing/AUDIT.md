# SameScale source-license audit — 2026-10-10

Base: remote `main@1061ddd7b13288f27e6d0545c8d6f6467278073b`, isolated
`codex/apache2-license-20261010` worktree. PR #10 and its Phase-2.6 worktree remain
independent and unchanged. The owner's current decision authorizes Apache-2.0 for
main product source, separate brand management and no website license change.
This is a source-license change, not a binary/container release or a legal
assignment of someone else's copyright.

## Evidence and scope decisions

[Audit receipt](audit.json) covers 1,691 baseline tracked files and all 225 main
commits. Git records one author name (`a27497`) with two email aliases; no
Co-authored-by trailer or separate external contributor identity was found.
The first commit is `f97f521` (Phase-A foundation, 2026-08-22). Text/header and
source-reference inspection found no contradictory copyright grant over the
main original code; no vendored dependency directory or font binary is tracked.
Git attribution alone cannot prove employer rights or an external assignment.
The owner-authorized source decision is applied without inventing either.

The baseline categories are exhaustive: **1,118 project-source/documentation
files**, **2 conservatively MIT-retained Alembic template files**, **14 excluded
brand files**, and **557 excluded historical evidence/artifact files**. The
new [LICENSE_SCOPE.md](../../LICENSE_SCOPE.md) defines the covered Work without
modifying Apache terms. New third-party texts are excluded from that source grant.
No existing source/header, task identity, original result or artwork is rewritten.

`alembic/env.py` and `alembic/script.py.mako` retain the original MIT template
terms with the actual Alembic distribution copyright/license. The project template
is not byte-identical to the current upstream generic template; treating the
recognizable template structure conservatively avoids a new originality claim.
Independent migration versions remain original project source under Apache-2.0.

[Brand inventory](brand-inventory.json) checks all 14 file hashes against the
original receipt and their website commit
`73063c5a6f311de61970862d16311cb0e2ada814`. The website's supplied-archive receipt
establishes copy provenance, not independently adjudicated design/glyph ownership.
The exact files, branded screenshots and identifiers are excluded; no rights
are inferred over an external design source. Brand use/artwork licensing remains
separate. The wrapper/CSS program source remains Apache-2.0. System font-family
names do not bundle fonts. Website fonts/icons and `samescale-site` licensing are
outside this audit's change scope.

[Archive audit](archive-audit.json) inspects all 513 ZIP entries and preserves
five identical MIT notices for LectureLens, `Copyright (c) 2026 a27497`, together
with existing source-context commit `0e392ea5c297e8e68af259fd9a50bc898a0b3d98`.
The ZIP/report/screenshot bytes stay unchanged; there is no new Apache grant over
those contents, third-party quotations, model output or generated artifacts.

## Dependencies and notices

[Dependency inventory](dependencies.json): all **282 npm lock entries** and
**72 external Python lock entries**. Original lock hashes, metadata expressions,
installed notice hashes and source URLs distinguish facts from inferences.
257 npm / 70 Python distributions are installed in this new isolated worktree.
The two Python platform omissions (Colorama/tzdata) are checked through source
archives matching the exact lock SHA-256, without executing downloaded code.
Optional foreign-platform npm binaries are metadata observations only.

372 source notice references map to **262 unique exact-byte texts** in the static
third-party notice file and its [index](../../licenses/notice-index.json).
Identical texts occur once; every original package/file reference stays indexed.
ECharts' supplied ASF NOTICE is preserved separately and in the notice aggregate;
Element Plus/icons remain external MIT assets. A new root NOTICE is not assumed
necessary merely because the project uses Apache-2.0.

The inventory records LGPL-3.0-only Psycopg, MPL components and composite/native
wheel notices including OpenBLAS/GCC/libquadmath exceptions. These libraries are
not relicensed as Apache. Their source/notice/replacement/relinking obligations
remain applicable to the actual distributed work. No dependency/version/digest
or runtime access policy is changed. See [third-party handling](../../THIRD_PARTY_NOTICES.md).

Notice gaps were examined rather than silently converted to original code:
agent-base/https-proxy-agent licenses are retained from README; LangSmith's exact
`v0.11.1` upstream MIT text fills a missing wheel/sdist LICENSE. Lodash-unified
1.0.3 supplies MIT and author metadata, but no standalone copyright notice or
repository; the original metadata is retained without an invented copyright year.
That separate-library notice gap remains a gate for a distributor requiring a
complete notice in a future binary. It does not authorize SameScale to relicense
that package, and it is not included in the first-party source grant.

**No observed conflict blocks this bounded project-source license publication.**
This does not certify all asset ownership, every OS/optional-platform distribution,
commercial tool terms, or a future binary release. Such distributions need their
own actual-content manifest, retained upstream texts, corresponding-source
availability and, where relevant, replacement/relinking checks. Excluded material
requires separate permission where no existing license already grants it.

## Integration and validation

[Official license sources](official-license-sources.json) bind the ASF's complete,
unmodified 11,358-byte Apache-2.0 text (SHA-256
`cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`). The Appendix's
example placeholders remain unchanged; the project attribution/scope is attached
in the separate scope document. The GNU GPL text accompanies LGPL notices;
it is not a new GPL grant for the independent product source.

Python metadata replaces `Proprietary` with Apache-2.0. Frontend metadata uses the
same identifier without changing private/package identities. Wheels carry the
license, scope, brand and third-party materials; the existing Docker recipe copies
those materials and the frontend build copies only an added static legal file.
No application source, API/DB logic, task/verifier, model/Runner, dependency lock
resolution, logo or design is changed. Existing CI workflows are retained.
The [validation receipt](validation.json) records actual checks and limitations;
exact pushed SHA, Draft PR and remote push/PR CI are separate publication facts.

Open source is not automatic OpenAI SIWC integration/account eligibility or OAuth
consent. REAL_CODEX remains closed; licensing grants no credential/account RPC,
model inference, paid Agent execution, deployment, DB migration or Phase 3.
The website, UI-2's 17 changes, existing worktrees (including PR #10), frozen
artifacts, databases/services and developer auth state remain protected.

## Primary references

- [Apache-2.0 text and application guidance](https://www.apache.org/licenses/LICENSE-2.0)
- [Apache licensing FAQ](https://www.apache.org/foundation/license-faq.html)
- [Mozilla MPL FAQ](https://www.mozilla.org/en-US/MPL/2.0/FAQ/)
- [Psycopg 3.3.4 LGPL text](https://github.com/psycopg/psycopg/blob/3.3.4/LICENSE.txt)
- [Psycopg installation forms](https://www.psycopg.org/psycopg3/docs/basic/install.html)
- Exact installed/sdist package notices and their hashes in the dependency inventory

**STOP after this independent Draft PR and exact-SHA CI. No merge or deployment.**
