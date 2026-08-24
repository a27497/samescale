from defaults import DEFAULTS


def build_settings(overrides: dict[str, object]) -> dict[str, object]:
    return {**DEFAULTS, **overrides}
