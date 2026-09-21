# Independent offline audit of the saved A Candidate workspace

This is a separate offline audit, not an Episode, real attempt, retry or resume.
The original attempt remains NOT_VERIFIED after its 600-second Subject timeout (601.037 seconds observed).
Its authorization and execution IDs remain consumed. No timeout cause is inferred.

Task: `lecturelens-embedded-subtitle-language-metadata@1.0.1`, original slot `A/candidate/1`.
Original execution: `a4869bcecb1148debd84bed5f7259d20`.
Bindings and original hashes are in `identity.json`, `result.json`, and `original-hashes.json`.

## Reconstruction and isolation

The frozen task workspace was copied, then overlaid with exactly the five saved source files.
All 99 resulting files are byte-identical to the original output snapshot. The verifier copy is also byte-identical.
The workspace was mounted read-only. All generated dependency links, type caches, build output and test injection
were confined to disposable container `/tmp` copies; no Candidate source was changed.
Docker used the frozen image `sha256:88c5544438f5942f7b3d17263816ac01f1479fb8d0ae7e9dd640fbe8ef51f11b`,
`--network none --read-only --cap-drop ALL --security-opt no-new-privileges --memory 2g --cpus 2 --pids-limit 256`,
a 768 MiB writable `/tmp`, and explicit `python3` entrypoint. No credentials, Subject runner or Codex CLI invoked.
Provider/model/Judge calls: 0. Original file preservation: 240 checked, unchanged.

## Results

- Original `python3 tools/frontend_check.py`: exit 0, 9 public test files / 25 tests passed, type-check passed, build passed.
- Original independent `python3 /verifier/verify.py /workspace`: valid report, `passed=false`, 71/75 checks passed.
  Business assertions: 68/72 passed, 4 failed; the other 3 gates (public-unit, type-check, build) passed.
  Verifier process exit 0 means report generation succeeded, not acceptance passed.
- Separate supplemental component acceptance: 12/22 passed, 10 failed, no skipped tests.
- Check ratios are not engineering-completion percentages.

The original verifier's four failures are the duplicate variant `sl-rozaj-rozaj` and duplicate extension
`en-u-ca-gregory-u-nu-latn`, on both pages. Candidate preserves those invalid strings in DOM `srclang`;
the verifier's language canonicalization raises RangeError. These are collected test failures caused by Candidate
output, not failed test collection or dependency setup. The parser does not reject duplicate variants/singletons.

The original frozen verifier has no `en-x-demo` case. Supplemental assertions mount the real upload/course view
and shared player, retaining the existing mocked API setup, and assert DOM srclang and preserved subtitle content.
Both pages return `und` for `en-x-demo`, `de-DE-x-goethe`, `en-US-x-a`, `x-demo`, and
`en-US-u-ca-gregory-x-demo`. Normal Unicode extension `en-u-ca-gregory` and `zh-Hant-TW` pass on both pages.
The parser's extension-loop character class excludes x/X, making its internal x branch unreachable;
a private-use-only tag also fails the initial primary-language test.
These added assertions are a separate acceptance supplement; the frozen verifier was not extended or rewritten.

Existing lifecycle assertions pass on both pages. Supplemental checks additionally pass for loaded-resource
switch clearing old text/visible track pending the new download, refresh clearing text while pending,
late failed old probe, and overlapping refreshes where the older download arrives last.

A1: pass in tested scope. A2: core alias/region/script cases pass; broader tags fail under A4.
A3: fail. A4: fail (supplemental). A5/A6: pass in tested scope.
A7: partial: both surfaces and existing functions are exercised and consistent, but both share A3/A4 defects.
Overall: engineering work is close to complete, with reproducible language-parser acceptance defects.
This is not a passing workspace or evidence that more time would have guaranteed success.

## Infrastructure and limits

First verifier audit failed to write its result because the new audit output bind mount was not writable for
the container user; traceback is preserved in `verifier-infrastructure-first.stderr`.
The first supplemental launch could not traverse the new mode-0700 audit directory. Only permissions of new audit
directories were adjusted, then the unchanged verifier/tests ran successfully. No dependency versions were changed.
Build Vue/component-stub and bundle-size/annotation warnings did not fail the checks.

Tests use Vue components in happy-dom and mocked APIs; real browser media decoding/playback was not validated.
BCP47 and asynchronous schedules are not exhaustively covered. Original token usage, request telemetry and upstream
timeout cause remain unknown. No results were written back to the original Episode or frozen run bundle.

Detailed reports: `verifier-evidence/report.json`, `verifier-evidence/business-vitest.json`,
`verifier-evidence/public-vitest.json`, `verifier-evidence/stages.json`, and
`supplemental-evidence/supplemental-vitest.json`. Test source: `supplemental-contract.test.ts`.
