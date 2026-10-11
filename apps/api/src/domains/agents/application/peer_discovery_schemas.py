"""Exact source search has no arbitrary account selector or wildcard controls."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from src.domains.peers.schemas import DiscoveryMatch, DiscoverySearchRequest


class PeerDiscoveryQuery(DiscoverySearchRequest):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    limit: StrictInt = Field(default=25, ge=1, le=50)
    offset: StrictInt = Field(default=0, ge=0)


class PeerDiscoveryProjection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    matches: list[DiscoveryMatch]
    total: int
    next_offset: int | None = None
    observed_at: datetime


if set(DiscoverySearchRequest.model_fields) != {"query"}:
    raise AssertionError("New source discovery filters require reviewed native search mapping")
