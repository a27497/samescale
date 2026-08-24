def parse_feature_flag(value: str | None, default: bool = False) -> bool:
    if value is None:
        return False
    return value.lower() == "true"
