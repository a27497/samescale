class RetryLedger:
    def __init__(self) -> None:
        self._results: dict[str, str] = {}

    def record_success(self, operation_key: str, result: str) -> bool:
        if not operation_key:
            raise ValueError("operation_key must not be empty")
        existing = self._results.get(operation_key)
        if existing is None:
            self._results[operation_key] = result
            return True
        if existing != result:
            raise ValueError("conflicting retry result")
        return False

    def lookup(self, operation_key: str) -> str | None:
        return self._results.get(operation_key)
