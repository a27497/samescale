class Quota:
    def __init__(self, capacity: int) -> None:
        self.remaining = capacity

    def consume(self, units: int) -> bool:
        if units <= 0:
            raise ValueError("units must be positive")
        if units > self.remaining:
            return False
        self.remaining -= units
        return True
