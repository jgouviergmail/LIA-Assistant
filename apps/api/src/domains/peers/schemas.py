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

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


@dataclass(frozen=True)
class PeerMessageActivity:
    """One DELIVERED relayed message on the caller's timeline, either way.

    The read-only bridge the Relations CRM consumes (spec §11, D2). Identity
    comes from foreign keys, never from a name match: ``peer_id`` is the OTHER
    participant and ``peer_display_name`` their live name, so a rename or a
    homonym can never split or merge two people's timelines.

    Attributes:
        message_id: ``PeerMessage`` id — the stable key of the rendered item.
        peer_id: The other participant.
        peer_display_name: Their current ``full_name``, trimmed. Never blank
            and never the unknown placeholder — such rows are dropped.
        direction: ``received`` when they wrote to the caller, ``sent`` when
            the caller wrote to them.
        occurred_at: UTC instant of the delivery.
        text: The caller's OWN side of the exchange — their directive when
            they sent it, their assistant's rendering when they received it —
            or None once the retention horizon cleared it (ADR-186). Never the
            other side's words: that would undo the relay.
    """

    message_id: UUID
    peer_id: UUID
    peer_display_name: str
    direction: str
    occurred_at: datetime
    text: str | None


@dataclass(frozen=True)
class PeerConnectionProfile:
    """One ACCEPTED connection, as the personal CRM needs to see it.

    The read-only bridge of spec §11 (D2): enough to badge a relationship, to
    say since when it exists, and to look its shares up — without the CRM ever
    touching the peers tables itself.

    Attributes:
        connection_id: Pair row id, to fetch the shares of both sides.
        peer_id: The other participant.
        peer_display_name: Their current ``full_name``, trimmed and non-blank.
        connected_since: UTC instant of the acceptance, when recorded.
        peer_email: Their address, ONLY when they opted into
            ``peer_email_visible``; ``None`` otherwise. It is the peer's own
            consent that fills this field, and nothing else may.
    """

    connection_id: UUID
    peer_id: UUID
    peer_display_name: str
    connected_since: datetime | None
    peer_email: str | None = None


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
    """Exact discovery search input — a full name OR an email address.

    ONE field on purpose (Bloc B): the backend decides which identity was
    typed (``looks_like_email``), so the frontend cannot hold a second,
    diverging opinion about the same string — and a half-typed address is
    searched as a name and answers "no result" instead of a 422.
    """

    query: str = Field(
        min_length=1,
        max_length=255,
        description="Exact full name or email address to search (never prefix/substring).",
    )


class DiscoveryStateResponse(BaseModel):
    """The caller's own peers opt-ins — two independent consents."""

    discovery_enabled: bool = Field(description="Whether the caller is discoverable.")
    email_visible: bool = Field(
        default=False,
        description="Whether ACCEPTED connections see the caller's real address (ADR-189).",
    )


class DiscoveryStateUpdate(BaseModel):
    """Toggle payload — each field is optional, and at least one is required.

    Partial on purpose: the two switches live side by side, and sending both
    every time would let one tab silently revert what another just changed.
    """

    discovery_enabled: bool | None = Field(default=None, description="New discoverability.")
    email_visible: bool | None = Field(default=None, description="New address visibility.")

    @model_validator(mode="after")
    def _at_least_one(self) -> DiscoveryStateUpdate:
        """Refuse a payload that asks for nothing."""
        if self.discovery_enabled is None and self.email_visible is None:
            raise ValueError("at least one of discovery_enabled or email_visible is required")
        return self


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
    peer_email: str | None = Field(
        default=None,
        description=(
            "The peer's real address, present ONLY when they opted in AND the "
            "pair is accepted (ADR-189). Null everywhere else, including on a "
            "pending request: not yet connected is not connected."
        ),
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


class RelayedMessageItem(BaseModel):
    """One relayed message, as the notifications hub shows it.

    A read-only projection of ``PeerMessageActivity``: the hub lists what
    reached the reader, it never re-opens the relay. ``content`` is the
    CALLER's own side of the exchange — their directive when they sent it,
    their assistant's rendering when they received it — never the other
    person's words, and None once the retention horizon cleared it (ADR-186).
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="PeerMessage id — the stable key of the row.")
    peer_display_name: str = Field(description="The other participant's live name.")
    direction: str = Field(description="`received` or `sent`, relative to the caller.")
    content: str | None = Field(
        default=None,
        description="The caller's own side of the exchange; None once retention cleared it.",
    )
    occurred_at: datetime = Field(description="UTC instant of the delivery.")


class RelayedMessagePage(BaseModel):
    """One page of relayed messages, and the EXACT total behind it.

    The total counts the whole timeline, never the length of this page
    (ADR-185): a figure shown to the reader is a claim, and "10 of 10" on an
    account with 200 exchanges is a false one.
    """

    messages: list[RelayedMessageItem]
    total: int = Field(ge=0, description="Exact count over the whole timeline.")
