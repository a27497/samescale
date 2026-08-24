# Correct layered settings

Fix `Settings.merge` so caller overrides take precedence over `Defaults.values()`, unknown keys are
preserved, and neither input map is mutated. Keep the two-class Java 21 API and `contract.txt`.
