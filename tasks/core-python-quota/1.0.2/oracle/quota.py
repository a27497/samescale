from collections import OrderedDict


class LRUCache:
    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self._values: OrderedDict[str, object] = OrderedDict()

    def get(self, key: str) -> object | None:
        if key not in self._values:
            return None
        self._values.move_to_end(key)
        return self._values[key]

    def put(self, key: str, value: object) -> None:
        self._values[key] = value
        self._values.move_to_end(key)
        if len(self._values) > self.capacity:
            self._values.popitem(last=False)

    def keys(self) -> list[str]:
        return list(self._values)
