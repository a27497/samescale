# K-B3 V6 Production Throughput R2

This addendum supersedes only the modelled V6 throughput-profile selection. It does not change
the seven cells, 18 tasks, five repeats, Judge design, scoring, budgets, paired lane, ablation,
provider caps, or any frozen V5 evidence.

The qualification used the production `BlockAwareDispatcher` and PostgreSQL queue for two
complete 630-slot trials of each bounded profile. Every trial stopped after 70 terminal slots
and resumed with a new coordinator. Each Harness slot created, attested, ran, and removed a
pinned Codex or Claude container with network `none`, read-only rootfs, dropped capabilities,
no-new-privileges, two-CPU/one-GiB limits, bounded PIDs, and deterministic local filesystem I/O.
Direct slots used deterministic local response fixtures. No provider endpoint was contacted.

The dispatcher now waits when the first unrepresented frozen slot is temporarily lane- or
provider-capped. It no longer skips to a later slot in the block. This removes completion-race
ordering variance while retaining pipelining: 87-88 adjacent block transitions overlapped in
each trial.

| Profile | Global | Harness | Median wall | Result |
| --- | ---: | ---: | ---: | --- |
| A | 4 | 2 | 78.020558 s | Qualified |
| B | 6 | 2 | 77.863214 s | Qualified; 0.201670% faster than A |
| C | 6 | 3 | 65.162402 s | Qualified; 16.311698% faster than B |

Profile C is the final fixed production profile. It exceeded the required ten-percent
improvement against both lower-risk comparators while producing zero duplicate claims,
scheduling violations, cap violations, lease losses, workspace/artifact/container collisions,
cleanup failures, security failures, and repeat attempts. All six trials reproduced dispatch
sequence digest
`sha256:bb73846c13f7cfaedcb639a01e08dc6fe8f62fce480ac81889d0ba67e0a4e3ac`.

Peak observed C telemetry across its two trials was 5.253731 CPU cores, 2,504,163,328 bytes of
host memory used, 2,646,016 bytes of swap used with no growth, 5.276367 one-minute load, six
database connections, 21 qualifier-process file descriptors, 2,400 host-allocated file
descriptors, and three qualifier containers. The separate cancellation probe observed the
cancelled state after a real heartbeat and left zero containers and workspaces.

The evidence is frozen in `release/core-real-matrix-v6-throughput-r2.json`. Host telemetry is
system-wide and may include unrelated local services. The containers exercise real production
image lifecycle and security limits, but not provider-backed CLI inference, so this qualification
does not authorize or replace the preregistered real canary.
