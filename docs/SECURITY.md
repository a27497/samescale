# Core Security and Trust Boundaries

HarnessLab evaluates untrusted generated code and reads sensitive operational evidence. Its Core posture is fail-closed: subjects run in a bounded sandbox, evidence is immutable and digest-bound, artifact paths stay within server-owned roots, credentials are references rather than values, and read surfaces cannot trigger providers or queues.

## Trust boundaries

- Subject workspaces and model output are untrusted. Hidden verifiers, oracles, credential material, host paths, and network access stay outside the subject-visible workspace.
- PostgreSQL queue records and server-owned artifact roots are trusted only after schema, scope, state, path, and digest checks.
- Provider, Codex, Claude, DeepSeek, and Judge responses are external evidence, not authority to mutate task truth.
- Workbench and Analyst output is an evidence projection. Private reasoning is withheld, untrusted labels are encoded, references are scope-bound, and unsupported prose cannot become a verified fact.
- GitHub Actions Gate K is keyless. Ambient environment variables, local logins, or existing `.env` values never constitute authorization.

## Focused security documents

[SANDBOX_SECURITY.md](SANDBOX_SECURITY.md) defines container, network, filesystem, process, and protected-path controls. [TASK_FORMAT.md](TASK_FORMAT.md) defines hidden verifier/oracle packaging. [HARNESS_COMPARABILITY.md](HARNESS_COMPARABILITY.md) covers evidence identity and control drift. [JUDGELAB.md](JUDGELAB.md) covers Judge boundaries. [ANALYST.md](ANALYST.md) covers bounded read-only analysis. [WORKBENCH.md](WORKBENCH.md) covers public DTO, safe-trace, and artifact-read behavior.

## Secrets and authorization

No `.env`, token, API key, OAuth credential, or login artifact belongs in Git, task packages, release manifests, logs, or reports. Profiles name uppercase environment-variable references only. Phase K-B requires a separate explicit authorization that freezes the exact provider/model calls and limits in [REAL_EVIDENCE_AUTHORIZATION.md](REAL_EVIDENCE_AUTHORIZATION.md). Credential availability is necessary but never sufficient.

## Provider-scoped Harness egress

K-B0 prepares an ephemeral internal Docker network per real Harness execution. The subject joins only that internal network and reaches a HarnessLab-controlled HTTPS CONNECT proxy; the proxy alone is dual-homed and allows exactly the configured provider DNS hostname on port 443. It rejects IP literals, undeclared hosts, non-443 targets, loopback, private, link-local, and metadata addresses after DNS resolution. It performs no TLS interception and its log schema contains only host, port, timestamps, byte counts, and result category—never credentials, headers, bodies, prompts, or model output. Docker socket, privileged, host-network, and direct-internet subject access remain forbidden. The hidden verifier remains `network=none`. Offline fakes test this topology; actual runtime behavior remains `CONFIGURED_NOT_SMOKED` until K-B1.

## Release boundary

Ordinary Gate K verifies contracts and reports `CORE_RELEASE_READY=FALSE` during K-B0. Final release mode requires trusted PostgreSQL reachability, a trusted artifact root, digest-bound real Matrix/Pair/Ablation/Judge/BadCase evidence, supported resume claims, exact release commit and remote CI head, and every mandatory state `VERIFIED`. Only then can the tag guard authorize `v1.0.0-core`; the verifier does not create the tag itself.
