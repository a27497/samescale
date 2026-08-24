from defaults import DEFAULTS


def build_settings(overrides: dict[str, object]) -> dict[str, object]:
    merged = dict(overrides)
    merged.update(DEFAULTS)
    return merged
