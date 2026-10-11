"""Finite source UI sections with bounded public projections and explicit truncation."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from src.domains.peers.schemas import (
    AccessLogEntry,
    BlockView,
    ConnectionView,
    DiscoveryStateResponse,
    RelayedMessageItem,
)

PeerReadSection = Literal[
    "preferences", "connections", "requests", "blocks", "access_log", "messages"
]
PeerUIItem = ConnectionView | BlockView | AccessLogEntry | RelayedMessageItem


class PeerUIQuery(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    section: PeerReadSection = "preferences"
    limit: StrictInt = Field(default=25, ge=1, le=50)
    offset: StrictInt = Field(default=0, ge=0)


class PeerUIProjection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    section: PeerReadSection
    preferences: DiscoveryStateResponse | None = None
    items: list[PeerUIItem] = Field(default_factory=list)
    total: int | None = None
    next_offset: int | None = None
    source_limit: int | None = None
    observed_at: datetime
