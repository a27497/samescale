class RetryLedger:
    def __init__(self) -> None:
        self._results: dict[str, str] = {}

    def record_success(self, operation_key: str, result: str) -> bool:
        if not operation_key:
            raise ValueError("operation_key must be non-empty")
        if operation_key in self._results:
            if self._results[operation_key] != result:
                raise ValueError("operation_key already has a different result")
            return False
        self._results[operation_key] = result
        return True

    def lookup(self, operation_key: str) -> str | None:
        return self._results.get(operation_key)
