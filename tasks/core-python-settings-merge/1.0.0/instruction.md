# Correct layered settings

Fix `settings.build_settings` so caller overrides take precedence over `DEFAULTS`, unknown override
keys are preserved, and neither input mapping is mutated. The defaults live in a separate module;
keep both public modules and `contract.txt` intact.
