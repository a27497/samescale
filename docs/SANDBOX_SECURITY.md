# Phase C sandbox security

Phase C is HarnessLab's first execution boundary for an untrusted subject workspace. It targets a
local Docker Engine or Docker Desktop using Linux containers. Preflight rejects remote TCP and SSH
contexts because their host-path and ownership semantics are not equivalent to the managed local
runtime root.

## Container profile

Trusted HarnessLab code constructs every Docker CLI argv list. There is no shell interpolation or
caller-facing raw-Docker-arguments API. Every subject and verifier container is non-root, uses the
default seccomp boundary, drops all capabilities, enables `no-new-privileges`, has a read-only root
filesystem, publishes no ports, receives no devices or Docker socket, uses network `none`, and has
CPU, memory, PID, timeout, and restart-policy limits. Gate C reads selected fields from `docker
inspect`; it does not infer security solely from intended flags and never persists the complete
inspect object or its environment variables.

Only `/workspace` and disposable `/tmp` are writable for a subject. The host workspace is created
under HarnessLab's managed per-run runtime root, resolved beneath that root, and freshly copied
from the Phase B task materialization. The task package itself is never a writable subject mount.
The subject does not receive `verifier/`, `oracle/`, their paths, or the Docker socket.

## Verifier isolation

Phase B's host verifier remains valid for trusted package polarity validation. Phase C's E2E does
not execute the subject-controlled workspace directly on the host: it starts a second hardened
container with network `none`, mounts the final subject workspace read-only at `/workspace`, and
mounts the hidden verifier read-only at `/verifier`. The subject container never sees that mount.

## Cleanup, secrets, and artifacts

Timeout and explicit task cancellation both kill and remove the labeled container before control
returns. Phase C creates no run-scoped Docker volume or network; `/tmp` is container tmpfs and is
destroyed with the container. Gate C checks for zero remaining Phase C containers and volumes.

Explicit run secrets are transferred through named environment variables, never embedded as
Docker argument values. Exact values are redacted from bounded stdout, stderr, summaries, and the
persisted manifest. Artifacts are created in a new run-ID directory and never overwrite an
existing bundle. They contain a safe workspace snapshot, input/output digests, immutable image
identity, selected security evidence, status/timing, redacted logs, and artifact hashes. Symlinks
or path escapes fail artifact collection; they are never followed into unrelated host files.

## Boundary limits

Docker is a process/container boundary, not a VM or Kubernetes security claim. Phase C does not
provide remote workers, cloud sandboxes, provider or coding-harness adapters, normalized traces,
an experiment scheduler, statistics, JudgeLab, or frontend behavior. Those remain later phases.
