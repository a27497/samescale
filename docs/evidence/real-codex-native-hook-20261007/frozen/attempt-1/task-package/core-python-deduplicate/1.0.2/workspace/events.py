class RetryLedger:
    def __init__(self) -> None:
        self._results: dict[str, str] = {}

    def record_success(self, operation_key: str, result: str) -> bool:
        self._results[operation_key] = result
        return True

    def lookup(self, operation_key: str) -> str | None:
        return self._results.get(operation_key)
