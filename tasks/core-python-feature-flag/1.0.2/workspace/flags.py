def parse_window(value: str, limit: int) -> tuple[int, int]:
    start, end = value.split(":")
    return int(start), int(end)
