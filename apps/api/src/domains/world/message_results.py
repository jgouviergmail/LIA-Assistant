"""The common acknowledgement, independent of correspondence audience."""

from collections.abc import Coroutine
from dataclasses import dataclass
from typing import Literal

from pydantic import Field

from src.domains.world.schemas import StrictModel


class MessageAccepted(StrictModel):
    id: str = Field(
        description="Stable client intent identifier for owned status and idempotent acknowledgement."
    )
    status: Literal["delivered", "pending", "uncertain"] = Field(
        description="Explicit lifecycle outcome; pending and uncertain never imply completed delivery."
    )


@dataclass(frozen=True)
class AcceptedSend:
    ack: MessageAccepted
    job: Coroutine[None, None, None] | None = None
