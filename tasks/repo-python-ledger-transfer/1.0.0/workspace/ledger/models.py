from dataclasses import dataclass


@dataclass(frozen=True)
class TransferResult:
    request_id: str
    source: str
    target: str
    amount: int
    replayed: bool = False
