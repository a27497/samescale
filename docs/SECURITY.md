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

K-B0 prepares an ephemeral internal Docker bridge per real Harness execution. Docker `--internal` alone is insufficient for Core Harness isolation because an ordinary internal bridge can still expose host services through its bridge/gateway address. Core therefore creates the subject network with IPv6 disabled and `com.docker.network.bridge.gateway_mode_ipv4=isolated`. The subject joins only that isolated network and reaches a HarnessLab-controlled HTTPS CONNECT proxy; the proxy alone is dual-homed and allows exactly the configured provider DNS hostname on port 443. The proxy is the sole intended subject egress path. It rejects IP literals, undeclared hosts, non-443 targets, loopback, private, link-local, and metadata addresses after DNS resolution. It performs no TLS interception and its log schema contains only host, port, timestamps, byte counts, and result category—never credentials, headers, bodies, prompts, or model output. Docker socket, privileged, host-network, direct-internet, and Docker host-gateway subject access remain forbidden. The hidden verifier remains `network=none`.

The proxy image `harnesslab-egress-proxy:1.0.0` uses an immutable `python:3.12.14-slim-bookworm` base digest and source/version identity labels. Each execution carries an inspected non-zero image ID. Before subject start, Docker's effective state must attest `Privileged=false`, read-only root, user `10001:10001`, all capabilities dropped, no-new-privileges, no published ports, the exact internal-plus-controlled-outbound network set, and network `Driver=bridge`, `Internal=true`, `EnableIPv6=false`, and gateway mode `isolated`. Cleanup independently attempts and verifies subject, proxy, and network removal after partial failures. Gate K exercises the actual local topology without provider Internet access, proving subject-to-proxy reachability, undeclared CONNECT rejection, direct-public and host-gateway bypass denial, verifier `network=none`, effective inspection, mutation rejection, and complete cleanup. Real provider behavior remains `CONFIGURED_NOT_SMOKED` until K-B1 authorization.

## Release boundary

Ordinary Gate K verifies contracts and reports `CORE_RELEASE_READY=FALSE` during K-B0. Final release mode requires trusted PostgreSQL reachability, a trusted artifact root, digest-bound real Matrix/Pair/Ablation/Judge/BadCase evidence, supported resume claims, exact release commit and remote CI head, and every mandatory state `VERIFIED`. Only then can the tag guard authorize `v1.0.0-core`; the verifier does not create the tag itself.
