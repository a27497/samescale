class LRUCache:
    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        self._values: dict[str, object] = {}

    def get(self, key: str) -> object | None:
        return self._values.get(key)

    def put(self, key: str, value: object) -> None:
        self._values[key] = value

    def keys(self) -> list[str]:
        return list(self._values)
