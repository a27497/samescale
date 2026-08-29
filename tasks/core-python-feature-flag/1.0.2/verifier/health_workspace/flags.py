import re


def parse_window(value: str, limit: int) -> tuple[int, int]:
    if limit < 0:
        raise ValueError("limit must be non-negative")
    match = re.fullmatch(r"\s*(\d+)\s*:\s*(\d+)\s*", value)
    if match is None:
        raise ValueError("invalid window")
    start, end = (int(part) for part in match.groups())
    if start > end or end > limit:
        raise ValueError("window out of range")
    return start, end
