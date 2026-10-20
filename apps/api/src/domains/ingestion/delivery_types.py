"""Content-free transport contracts for durable ingestion deliveries."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class DeliveryDisposition(StrEnum):
    ACCEPTED = "accepted"
    RETRYABLE = "retryable"
    PERMANENT = "permanent"
    UNKNOWN = "unknown"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class DeliveryDestination:
    key: str
    device_id: UUID | None = None

    def __post_init__(self) -> None:
        if not self.key or len(self.key) > 64 or self.key == "fanout":
            raise ValueError("Invalid delivery destination")


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    disposition: DeliveryDisposition
    error_code: str | None = None
    retry_after_seconds: int = 60

    def __post_init__(self) -> None:
        if self.error_code and (
            len(self.error_code) > 48
            or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789" for c in self.error_code)
        ):
            raise ValueError("Only content-free error codes are accepted")
        if not 1 <= self.retry_after_seconds <= 86400:
            raise ValueError("Invalid retry delay")


@dataclass(frozen=True, slots=True)
class DeliveryClaim:
    id: UUID
    user_id: UUID
    receipt_id: UUID
    destination_key: str
    device_id: UUID | None
    fence: int
    worker: UUID
    lease_until: datetime
    attempts: int
    effect_id: UUID | None
