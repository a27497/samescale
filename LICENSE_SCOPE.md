# License scope

Copyright 2026 a27497, for the SameScale project source identified below.

The unmodified [Apache License 2.0](LICENSE) applies to the original SameScale
project source, continuing the HarnessLab implementation and Git history. This
file identifies that Work; it does not add conditions to or modify Apache-2.0.
Third-party authors retain their copyrights and license terms.

## Covered project source

- `src/harnesslab/**`, `tests/**`, `scripts/**`, `tasks/**`, `alembic/**`,
  `docker/**`, `profiles/**`, and `judge_suites/**`: project implementation,
  tests, build recipes, locally authored task/verifier fixtures and configuration.
- `frontend/src/**`, `frontend/tests/**`, `frontend/index.html`, and the frontend
  package/build/type configuration files. This includes the program source of
  `frontend/src/components/WorkbenchBrand.vue`, not the image assets it references.
- `.github/**`, `.agents/**`, repository-maintained root documentation and
  configuration, and maintained technical Markdown directly under `docs/`.
- The original audit documentation and inventories under `docs/licensing/`.

Existing third-party text, notices, quoted material and dependency references
inside these files keep their own rights. A reference/import is not a claim that
the dependency was authored by SameScale. No dependencies are relicensed.

## Excluded from the new Apache grant

| Files/material | Treatment |
| --- | --- |
| `alembic/env.py`, `alembic/script.py.mako` | Conservatively retain MIT for Alembic-template-derived material; see `licenses/alembic-1.19.1-MIT.txt`. Other original migration files remain project source. |
| `frontend/public/brand/**`, `frontend/public/favicon.svg`, `frontend/public/favicon.ico`, `frontend/public/favicon-32x32.png`, `frontend/public/apple-touch-icon.png` | Brand artwork; exact paths and provenance in [brand policy](BRAND_ASSETS.md). No artwork or brand-use license is granted here. |
| `docs/evidence/**`, `docs/qa/**`, `docs/recruiter/**`, `release/**` | Preserved historical evidence, screenshots, reports, replay archives, generated/demo artifacts and captured external/model content. This change grants no new license over them. Existing explicit licenses remain effective. |
| `licenses/**`, `frontend/public/legal/**` | Original third-party license/notice texts and their indexes. Under the respective upstream terms, not a SameScale authorship claim. |
| Dependencies, downloaded packages, generated bundles and container/runtime contents | Each dependency keeps its own license; see [third-party obligations](THIRD_PARTY_NOTICES.md). They are not included in this project-source grant. Original project code within a build remains Apache-2.0. |
| SameScale names, logos and other brand identifiers wherever shown | Apache-2.0 section 6 does not grant trademark/brand-use rights. See the brand policy; necessary origin descriptions and upstream license rights are unaffected. |

In particular, the unchanged archive
`docs/evidence/s2-offline-replay-20260921/representative-bundles.zip` contains
LectureLens material with five preserved MIT license copies, identifying
`Copyright (c) 2026 a27497`. Those copies retain MIT, not Apache-2.0. Historical
commits and archives are not retroactively rewritten or blanket relicensed.

The website repository `a27497/samescale-site` is outside this Work; its license,
fonts, icons, artwork and deployment remain unchanged. This source license does
not grant OpenAI SIWC eligibility, account access, OAuth consent, credentials,
model/runtime rights or permission to run a real evaluation.

## Use and contributions

Apache-2.0 permits commercial use, modification and distribution of the covered
source under its terms, including license/notice retention and notices of modified
files. It provides the patent grant specified in section 3 and no warranty.
It does not require publishing every private modification or grant ownership of
third-party/brand material. Consult the license rather than treating this summary
as additional terms. See [contribution guidance](CONTRIBUTING.md).

The [dated audit](docs/licensing/AUDIT.md) records evidence and limitations. Git
authorship is attribution, not independent proof of employer rights or an external
copyright assignment. The owner-authorized source licensing decision is applied
without inventing a company, assignment, CLA, or ownership of external material.
