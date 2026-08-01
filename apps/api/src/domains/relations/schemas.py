"""Relations domain schemas (N-09) — the read-only CRM API contract.

All payloads are UI-ready and immutable. Timestamps are ISO-8601 UTC strings;
the frontend formats them in the user's timezone (briefing doctrine). Nothing
here is a source of truth — every field is aggregated from an existing domain,
and ``identity_confidence`` states how sure the name match is.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class IdentityConfidence(str, Enum):
    """How the relationship key was matched (honesty over false precision)."""

    EXACT = "exact"  # identical display name across sources
    NORMALIZED = "normalized"  # matched after accent/case folding


class RelationOpenLoop(BaseModel):
    """One open commitment involving this person."""

    model_config = ConfigDict(frozen=True)

    id: str
    subject: str
    direction: str = Field(description="user_owes | waiting_on_other")
    due_hint: datetime | None = None
    days_open: int = Field(ge=0)


class RelationCall(BaseModel):
    """One past call with this person (never the phone number — D-8)."""

    model_config = ConfigDict(frozen=True)

    id: str
    objective: str
    outcome: str | None = None
    summary: str | None = None
    created_at: datetime


class RelationMemory(BaseModel):
    """One stored memory mentioning this person."""

    model_config = ConfigDict(frozen=True)

    id: str
    content: str


class RelationPeerMessage(BaseModel):
    """One message relayed between the user and this person's assistant.

    ``content`` is null whenever the text is not the user's to show: a message
    they SENT left no copy on their side (the ledger scrubs the directive on
    delivery — peers spec §8.4), and a received one loses its text if the
    conversation was reset. The exchange itself is never lost, so a count
    never promises text that cannot be displayed.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    direction: str = Field(description="received | sent, relative to the user")
    content: str | None = Field(
        default=None, description="Delivered text, when it is still archived on this side."
    )
    occurred_at: datetime


class RelationShare(BaseModel):
    """One read-only share on the LIA connection behind this relationship.

    Raw values, never a rendered label: the frontend already owns the
    translated table for ``{domain}_{level}`` (label-key doctrine).
    """

    model_config = ConfigDict(frozen=True)

    domain: str = Field(description="calendar | task (PeerShareDomain).")
    level: str = Field(description="availability | details | titles (PeerShareLevel).")


class RelationPeerLink(BaseModel):
    """The LIA connection behind this relationship (peers spec §11, D2).

    Read-only, like everything else on this surface: sharing is granted and
    revoked in the Connections settings, never here. Both directions are
    stated — what the user shares, and what is shared with them — because a
    one-sided view of a two-sided arrangement is misleading.
    """

    model_config = ConfigDict(frozen=True)

    connected_since: datetime | None = Field(
        default=None, description="UTC instant the connection was accepted."
    )
    shared_by_me: list[RelationShare] = Field(default_factory=list)
    shared_with_me: list[RelationShare] = Field(default_factory=list)


class RelationSummary(BaseModel):
    """One row of the CRM overview — a person and why they surface now."""

    model_config = ConfigDict(frozen=True)

    display_name: str
    identity_confidence: IdentityConfidence
    open_loops_count: int = Field(ge=0)
    calls_count: int = Field(ge=0)
    # Relayed messages exchanged both ways with this person (peers D2 bridge).
    peer_messages_count: int = Field(default=0, ge=0)
    # ISO-8601 UTC of the most recent signal (loop/call), for "last seen".
    last_interaction_at: datetime | None = None
    # Starred by the user — persisted, survives the live signals expiring.
    is_favorite: bool = False
    # Also a connected LIA user (peers program D2 bridge, read-only).
    is_peer: bool = False


class RelationsOverview(BaseModel):
    """The CRM overview — relationships ranked by recency of interaction."""

    model_config = ConfigDict(frozen=True)

    relations: list[RelationSummary]
    relations_total: int = Field(
        default=0,
        ge=0,
        description=(
            "Exact number of relationships the aggregation found, before the "
            "page cap. The list is a page like any section: past the cap a "
            "person would simply vanish, so the cap is stated (ADR-185)."
        ),
    )


class RelationDetail(BaseModel):
    """The 360° view of one relationship."""

    model_config = ConfigDict(frozen=True)

    display_name: str
    identity_confidence: IdentityConfidence
    # Every section ships a PAGE plus its exact TOTAL. The page is capped by
    # ``relations_max_items_per_section``; the total never is, so the UI can
    # state what it is not showing instead of truncating in silence.
    open_loops: list[RelationOpenLoop]
    open_loops_total: int = Field(default=0, ge=0)
    recent_calls: list[RelationCall]
    recent_calls_total: int = Field(default=0, ge=0)
    memories: list[RelationMemory]
    memories_total: int = Field(default=0, ge=0)
    peer_messages: list[RelationPeerMessage] = Field(default_factory=list)
    peer_messages_total: int = Field(default=0, ge=0)
    # Present only while an ACCEPTED connection exists — a removed one leaves
    # its past messages behind but has no state left to describe.
    peer_link: RelationPeerLink | None = None
    is_favorite: bool = False
    is_peer: bool = False
