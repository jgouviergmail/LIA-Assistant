"""Peers domain schemas (Lot 1) — API contract of the /peers surface.

Error details on this surface are stable machine codes (``peers_*``) that the
frontend maps to localized strings (label-key doctrine — never pre-translated
strings in payloads). Timestamps are ISO-8601 UTC; the frontend formats them
in the viewer's timezone.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.core.constants import PEERS_CONTEXT_MESSAGE_MAX_CHARS
from src.domains.peers.models import PeerShareDomain, PeerShareLevel


@dataclass(frozen=True)
class PeerEvent:
    """One state change Lot 3 will turn into chat notifications.

    Attributes:
        kind: request_created | request_accepted | request_declined |
            connection_removed.
        connection_id: Pair row the event happened on.
        actor_id: User who performed the action.
        affected_ids: Users to notify (Lot 3 dispatch).
    """

    kind: str
    connection_id: UUID
    actor_id: UUID
    affected_ids: tuple[UUID, ...]


class DiscoveryMatch(BaseModel):
    """One discoverable user matching an exact folded-name search."""

    model_config = ConfigDict(frozen=True)

    peer_id: UUID = Field(description="Opaque user id to target a request at.")
    display_name: str = Field(description="The user's full name as displayed.")
    email_hint: str = Field(description="A6 masked email fragment (homonym discriminator).")
    relationship: Literal["none", "pending", "connected"] = Field(
        default="none",
        description=(
            "Searcher's existing relationship with this user. DECLINED/REMOVED "
            "pairs read 'none' on purpose (indistinguishable from no history)."
        ),
    )


class DiscoverySearchRequest(BaseModel):
    """Exact full-name discovery search input (never prefix/substring)."""

    full_name: str = Field(min_length=1, max_length=255, description="Exact name to search.")


class DiscoveryStateResponse(BaseModel):
    """The caller's own discovery opt-in state."""

    discovery_enabled: bool = Field(description="Whether the caller is discoverable.")


class DiscoveryStateUpdate(BaseModel):
    """Toggle payload for the discovery opt-in."""

    discovery_enabled: bool = Field(description="New opt-in value.")


class ConnectionRequestCreate(BaseModel):
    """Create-connection-request payload."""

    peer_id: UUID = Field(description="Target user id (from a discovery search).")
    context_message: str | None = Field(
        default=None,
        max_length=PEERS_CONTEXT_MESSAGE_MAX_CHARS,
        description="Optional note shown provenance-framed to the addressee.",
    )


class ConnectionRespond(BaseModel):
    """Accept/decline payload for a pending request."""

    accept: bool = Field(description="True accepts the request, False declines it.")


class ConnectionStateView(BaseModel):
    """Minimal state view returned by lifecycle verbs (request/respond/remove)."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(description="Connection (pair row) id.")
    status: str = Field(description="pending | accepted | declined | removed.")


class ShareItem(BaseModel):
    """One shared domain and its granularity."""

    model_config = ConfigDict(frozen=True)

    domain: str = Field(description="calendar | task (PeerShareDomain).")
    level: str = Field(description="availability | details | titles (PeerShareLevel).")


class ShareUpdate(BaseModel):
    """Upsert/delete payload for one of MY shares on a connection.

    Enum-typed on purpose: an unknown domain/level is a 422 at the Pydantic
    boundary, before any service code runs.
    """

    domain: PeerShareDomain = Field(description="calendar | task.")
    level: PeerShareLevel | None = Field(
        default=None,
        description="Target level; null removes the share (back to not-shared).",
    )


class ConnectionView(BaseModel):
    """One connection as seen by the caller — both share directions visible."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(description="Connection (pair row) id.")
    peer_id: UUID = Field(description="The other user's id.")
    peer_display_name: str = Field(description="The other user's full name.")
    peer_email_hint: str = Field(
        description="A6 masked email fragment — pinned permanently (spec §12.8)."
    )
    status: str = Field(description="pending | accepted.")
    direction: str | None = Field(
        default=None,
        description="incoming | outgoing for pending requests; null once accepted.",
    )
    requested_at: datetime = Field(description="UTC instant of the current/last request.")
    responded_at: datetime | None = Field(
        default=None, description="UTC instant of the accept, when accepted."
    )
    context_message: str | None = Field(
        default=None, description="Requester note (incoming pending only)."
    )
    my_shares: list[ShareItem] = Field(
        default_factory=list, description="What I share with this peer (editable)."
    )
    their_shares: list[ShareItem] = Field(
        default_factory=list, description="What this peer shares with me (read-only)."
    )


class BlockCreate(BaseModel):
    """Block payload."""

    peer_id: UUID = Field(description="User to block (never notified).")


class BlockView(BaseModel):
    """One block placed by the caller."""

    model_config = ConfigDict(frozen=True)

    blocked_id: UUID = Field(description="Blocked user id.")
    blocked_display_name: str | None = Field(
        default=None, description="Blocked user's name at display time (may be null)."
    )
    created_at: datetime = Field(description="UTC instant the block was placed.")


class AccessLogEntry(BaseModel):
    """One cross-user read of MY data (transparency view — spec §12.4)."""

    model_config = ConfigDict(frozen=True)

    accessor_display_name: str = Field(description="Peer whose assistant read the data.")
    domain: str = Field(description="Domain that was read.")
    tool_name: str = Field(description="Tool that performed the read.")
    created_at: datetime = Field(description="UTC instant of the read.")
