"""What a "360° point" is allowed to look at (relation overview scope).

The 360° request leaves the browser as a chat `?intent=`, which carries text
and nothing else. Letting the planner infer the scope from that prose would
make the user's choice a **hint**; this module makes it a **guarantee**: the
selection is written server-side BEFORE the chat opens, and the tool reads it
back. Whatever the sentence says, the scope is what the reader ticked.

It doubles as the pre-filled default next time — "what I usually want" — which
is why one stored value serves both purposes instead of a preference plus a
per-request payload.

Every field is a set of *inclusions*: an empty selection means "this source is
not part of my 360°", never "everything". Silence must not be generous here —
a scope that grows when the user clears it would spend provider quota they
just asked to save.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from src.core.constants import (
    RELATION_OVERVIEW_MAX_ITEMS_CEILING,
    RELATION_OVERVIEW_MAX_ITEMS_DEFAULT,
)


class OverviewSection(str, Enum):
    """A source the 360° may draw from."""

    OPEN_LOOPS = "open_loops"
    CALLS = "calls"
    MEMORIES = "memories"
    PEER_MESSAGES = "peer_messages"
    CONTACT = "contact"
    EMAILS = "emails"
    EVENTS = "events"


class OverviewDirection(str, Enum):
    """Which way an exchange went — mail and relayed messages alike."""

    RECEIVED = "received"
    SENT = "sent"


class OverviewRole(str, Enum):
    """The person's part in a meeting."""

    ATTENDEE = "attendee"
    ORGANIZER = "organizer"


#: Everything, five items each — the shape a first-time reader gets.
_ALL_SECTIONS = tuple(OverviewSection)
_ALL_DIRECTIONS = tuple(OverviewDirection)
_ALL_ROLES = tuple(OverviewRole)


class RelationOverviewScope(BaseModel):
    """The scope one 360° point applies.

    Validated on the way in AND on the way out: the column is JSONB, so a
    payload written by an older version (or by hand) must degrade to the
    default rather than reach the tool as a half-shape.
    """

    model_config = ConfigDict(frozen=True)

    sections: list[OverviewSection] = Field(
        default_factory=lambda: list(_ALL_SECTIONS),
        description="Sources the 360° may read. Empty means: none of them.",
    )
    directions: list[OverviewDirection] = Field(
        default_factory=lambda: list(_ALL_DIRECTIONS),
        description="Applies to mail AND relayed messages — the same question.",
    )
    roles: list[OverviewRole] = Field(
        default_factory=lambda: list(_ALL_ROLES),
        description="Applies to shared meetings.",
    )
    max_items: int = Field(
        default=RELATION_OVERVIEW_MAX_ITEMS_DEFAULT,
        ge=1,
        le=RELATION_OVERVIEW_MAX_ITEMS_CEILING,
        description=(
            "Items per section handed to the assistant. Bounded and PUBLISHED "
            "so the producer can read what the validator enforces (ADR-184)."
        ),
    )

    def includes(self, section: OverviewSection) -> bool:
        """Whether this source is part of the scope."""
        return section in self.sections

    @classmethod
    def default(cls) -> RelationOverviewScope:
        """Everything, five items each."""
        return cls()

    @classmethod
    def from_stored(cls, raw: object) -> RelationOverviewScope:
        """Rebuild a scope from the JSONB column, degrading to the default.

        A stored shape this version cannot read is not an error the reader can
        act on — falling back to "everything" is the same answer they had
        before the setting existed.

        Args:
            raw: Whatever the column holds (dict, None, or worse).

        Returns:
            A valid scope.
        """
        if not isinstance(raw, dict):
            return cls.default()
        try:
            return cls.model_validate(raw)
        except ValueError:
            return cls.default()
