"""Transaction-local admission balances; no eviction or global mutable state."""

from dataclasses import dataclass


@dataclass(slots=True)
class IngestionBudget:
    available_bytes: int
    available_receipts: int

    def consume(self, logical_bytes: int) -> None:
        self.available_bytes -= logical_bytes
        self.available_receipts -= 1
