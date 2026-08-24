# Core BadCases

Status for Phase K-A: **NOT_VERIFIED — REAL EVIDENCE PENDING**.

No real BadCase can be selected before the authorized Core Matrix has produced trusted run, verifier, trace, and cell evidence. The machine-readable placeholders are in `release/badcases.json`; they contain no invented task, run, cell, or evidence identity.

## Required evidence bundle

Each future Core BadCase must be a real `capability_fail` persisted as `failed_subject`, bind the task/version/digest, run identity, cell/profile identity, artifact and report references, verifier outcome, and only the safe trace facts permitted by the trace policy. Infrastructure and cancellation observations remain separately classified and cannot occupy these three capability BadCase slots. Root cause is included only when the evidence supports it. The closing lesson records the mitigation and what HarnessLab detected that a simple pass-rate table would miss.

## Slot 1

`NOT_VERIFIED — REAL EVIDENCE PENDING`

Candidate: a subject failure whose deterministic verifier distinguishes a plausible wrong solution from the oracle. No candidate has been selected.

## Slot 2

`NOT_VERIFIED — REAL EVIDENCE PENDING`

Candidate: a cross-lane difference whose controls and trace evidence permit careful attribution. No candidate has been selected.

## Slot 3

`NOT_VERIFIED — REAL EVIDENCE PENDING`

Candidate: a verifier-backed subject failure whose safe trace adds a distinct mitigation lesson. No candidate has been selected.
