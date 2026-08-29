class CloseTracker:
    def __init__(self) -> None:
        self.close_calls = 0
        self.sent: list[str] = []

    def send(self, payload: str) -> str:
        self.sent.append(payload)
        return f"sent:{payload}"

    def close(self) -> None:
        self.close_calls += 1
