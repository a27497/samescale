class Quota:
    def __init__(self, capacity: int) -> None:
        self.remaining = capacity

    def consume(self, units: int) -> bool:
        if units < self.remaining:
            self.remaining -= units
            return True
        self.remaining -= units
        return False
