def deduplicate(events: list[str]) -> list[str]:
    """Return unique event ids in first-seen order."""

    return list(dict.fromkeys(events))
