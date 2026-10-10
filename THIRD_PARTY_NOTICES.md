# Third-party licenses and redistribution

SameScale's Apache-2.0 grant covers the project source identified in
[LICENSE_SCOPE.md](LICENSE_SCOPE.md). It does not replace dependency licenses,
claim external authorship or certify every compiled/container distribution.

The [locked dependency inventory](docs/licensing/dependencies.json) records all
282 npm entries and 72 external Python packages, original declared expressions,
installed/sdist notice hashes and platform omissions. Metadata and observed
license texts are distinguished. Package versions, hashes and dependency edges
are unchanged. The [audit](docs/licensing/AUDIT.md) explains findings and remaining
distribution-specific checks.

Original observed license and attribution texts are retained in
[`frontend/public/legal/THIRD_PARTY_NOTICES.txt`](frontend/public/legal/THIRD_PARTY_NOTICES.txt),
with an exact-byte [section index](licenses/notice-index.json). Vite copies that
static file to the build without changing application code. It deliberately
includes a conservative set of build/runtime dependency notices; inclusion is
not a claim that each package is shipped to browsers. The same legal file,
source license and scope documents are included in wheels/build contexts.

## Material findings

| Material | Original terms and handling |
| --- | --- |
| `alembic/env.py`, `alembic/script.py.mako` | Template-derived structure is conservatively treated as upstream MIT material, retaining Alembic's actual copyright/license text in `licenses/alembic-1.19.1-MIT.txt`. Not claimed as wholly original SameScale code. |
| ECharts 6.1.0 | Apache-2.0. The actual imported chart library's LICENSE and ASF NOTICE are preserved verbatim. NOTICE is also copied to `licenses/echarts-6.1.0-NOTICE.txt`. No SameScale authorship claim. |
| Element Plus 2.14.5, `@element-plus/icons-vue`, Vue, Pinia, Vue Router, Axios and their dependencies | Retain the original MIT/BSD/ISC/other notices recorded in the inventory. Icons are external assets, not original SameScale artwork. |
| `psycopg` and `psycopg-binary` 3.3.4 | LGPL-3.0-only, separate libraries; not relicensed. Retain LGPL/GPL texts and upstream copyrights; preserve modification/relinking rights and provide corresponding source as required when distributing a combined/binary work. Python imports do not establish all redistribution conditions. Exact library source: `https://github.com/psycopg/psycopg/tree/3.3.4`. |
| Certifi, orjson, pathspec, lightningcss | MPL-2.0 or expressions containing MPL. Preserve file-level licenses and make the covered source/modifications available with appropriate source notices if distributed. New independent project files are not reclassified as MPL. |
| NumPy/SciPy binary wheels | Preserve the complete wheel notices, including OpenBLAS, GCC runtime/libquadmath and accompanying exceptions; a top-level BSD expression is not the whole binary audit. |
| Python/Node/PostgreSQL/Debian/Temurin, Codex CLI, Claude Code and downloaded build tools | Their recipes are project source; installed distributions and commercial tool/service terms are separate. No runtime binary, container image or model/service permission is licensed by SameScale. This change neither builds/publishes those images nor runs the Agents. |
| LectureLens replay ZIP | Five original MIT notices remain inside the unchanged ZIP. A readable exact copy is retained in `licenses/archived-lecturelens-MIT.txt`. All archive contents stay outside the new Apache grant. |
| SameScale logos/favicon/snapshots | Separate excluded artwork/evidence scope, not third-party code magically relicensed by the root LICENSE. See the brand policy. |

## Retention and limits

Apache-2.0 section 4 requires retaining applicable upstream notices, including
NOTICE text when supplied. No inherited project-wide NOTICE requiring a new
root NOTICE was found. The actual ECharts NOTICE is preserved in the third-party
distribution materials instead; this is not an assumption that every Apache
project must create NOTICE.

MIT/BSD/ISC and related licenses require their applicable notices to travel with
redistributed material. MPL and LGPL have additional source/notice and, where
applicable, replacement/relinking obligations. Do not restrict rights granted by
those licenses with the brand policy. The accompanying GPL text supports the
LGPL terms; it does not turn independent SameScale source into GPL code.

`agent-base` and `https-proxy-agent` include their MIT notices in README; those
exact sections are retained. LangSmith's wheel/sdist omit a separate LICENSE;
its MIT license was recovered from the matching upstream `v0.11.1` tag.
`lodash-unified` 1.0.3 publishes MIT/author metadata but no separate copyright
notice or repository in its tarball/registry metadata. Its original package
metadata is retained, no year/copyright owner is invented, and it remains a
separate dependency. A distributor requiring a complete upstream copyright
notice must resolve that gap before publishing a binary containing it.

The audit includes locally installed Linux distributions and the Colorama/tzdata
source archives (matching lock hashes), not every optional platform binary or
OS package. A future binary/container release needs a manifest of its actual
contents, all embedded licenses/notices, required corresponding source and
replacement/relinking verification. This source-license PR does not publish or
certify such a release; these requirements remain a separate distribution gate.

Sources: [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0),
[Mozilla MPL FAQ](https://www.mozilla.org/en-US/MPL/2.0/FAQ/),
[exact Psycopg LGPL text](https://github.com/psycopg/psycopg/blob/3.3.4/LICENSE.txt),
[Psycopg installation forms](https://www.psycopg.org/psycopg3/docs/basic/install.html).
