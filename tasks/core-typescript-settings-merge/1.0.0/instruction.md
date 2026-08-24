# Correct layered settings

Fix `buildSettings` so caller overrides take precedence over `DEFAULTS`, unknown keys are
preserved, and neither input object is mutated. Keep the two-module typed API and `contract.txt`.
