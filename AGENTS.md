# HarnessLab agent governance

- Work on exactly one named phase per Codex task. Finish its safe internal implementation,
  diagnosis, repair, and gate verification before stopping.
- Continue through minor ambiguity and non-destructive failures. Read exact errors, repair the
  minimal root cause, and rerun the affected checks before the full gate.
- Do not cross the current phase gate or create speculative future architecture.
- Do not commit, push, create a pull request, merge, or deploy unless the user explicitly asks.
- Never fabricate evidence. `NOT_RUN` means the command was not run; `NOT_VERIFIED` means evidence
  is insufficient. Neither is a pass.
- Keep test failure observable. Zero tests, missing tools/configuration, and skipped critical tests
  must not report success.
- Never store or print secrets. Configuration examples must contain development-only placeholders.
- Do not overwrite unexplained user changes or use destructive Git operations autonomously.
- If the current task explicitly requires an external completion notification, attempt it through
  the available connector. Report `EMAIL_TOOL_UNAVAILABLE` or `EMAIL_SEND_FAILED` truthfully when
  delivery cannot be completed.
