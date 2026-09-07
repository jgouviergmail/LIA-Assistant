"""Shared builders for the 360° evidence tests.

The values here are FROZEN: they are the inputs the golden payload file was
captured from, so changing one silently invalidates the anti-regression oracle.
When a genuine behaviour change is intended, the golden file is regenerated in
the same commit and the diff is the review.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from src.domains.relations.overview_scope import RelationOverviewScope
from src.domains.relations.providers.schemas import (
    ContactCard,
    ContactEmail,
    ContactPhone,
    ContactValue,
    ContextSection,
    ContextStatus,
    ExchangedEmail,
    RelationContext,
    SharedEvent,
)
from src.domains.relations.schemas import (
    IdentityConfidence,
    RelationCall,
    RelationDetail,
    RelationMemory,
    RelationOpenLoop,
    RelationPeerLink,
    RelationPeerMessage,
    RelationShare,
)

USER_ID = UUID("11111111-2222-3333-4444-555555555555")
NOW = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)
PERSON = "Gérard Dupont"


def detail(**over: object) -> RelationDetail:
    """One relationship as the database-local half reports it."""
    base = {
        "display_name": PERSON,
        "identity_confidence": IdentityConfidence.EXACT,
        "open_loops": [
            RelationOpenLoop(
                id=f"l{index}",
                subject=f"Engagement {index}",
                direction="user_owes",
                due_hint=NOW if index == 2 else None,
                days_open=index,
            )
            for index in range(8)
        ],
        "open_loops_total": 8,
        "recent_calls": [
            RelationCall(
                id="c1",
                objective="Anniversaire",
                outcome="answered",
                summary="OK",
                created_at=NOW,
            )
        ],
        "recent_calls_total": 1,
        "memories": [RelationMemory(id="m1", content="Aime la randonnée")],
        "memories_total": 1,
        "peer_messages": [
            RelationPeerMessage(id="p1", direction="received", content="Salut", occurred_at=NOW),
            RelationPeerMessage(id="p2", direction="sent", content="Ok", occurred_at=NOW),
        ],
        "peer_messages_total": 2,
        "peer_link": RelationPeerLink(
            connected_since=NOW,
            shared_by_me=[RelationShare(domain="task", level="titles")],
            shared_with_me=[RelationShare(domain="calendar", level="availability")],
        ),
        "is_favorite": True,
        "is_peer": True,
    }
    return RelationDetail(**{**base, **over})  # type: ignore[arg-type]


def section(status: ContextStatus = ContextStatus.OK, **over: object) -> ContextSection:
    """One provider-backed section envelope."""
    return ContextSection(status=status, generated_at=NOW, **over)  # type: ignore[arg-type]


CARD = ContactCard(
    display_name=PERSON,
    nickname="Gégé",
    organization="ACME",
    occupation="Architecte",
    birthday="--04-07",
    biography="Rencontré au forum.",
    emails=[ContactEmail(value="gerard@x.com", label="work")],
    phones=[ContactPhone(value="+33600000000", label="mobile")],
    addresses=[ContactValue(value="12 rue des Lilas, Lyon", label="home")],
    relations=[ContactValue(value="Claire Lefèvre", label="spouse")],
    links=[ContactValue(value="https://example.com", label=None)],
    important_dates=[ContactValue(value="2011-09-03", label="anniversary")],
    messaging=[ContactValue(value="gerard.d", label="skype")],
)


def context(**over: object) -> RelationContext:
    """The provider-backed half as the context service reports it."""
    base = {
        "contact": section(contact=CARD),
        "emails": section(
            emails=[
                ExchangedEmail(
                    id="e1",
                    direction="received",
                    subject="Devis",
                    occurred_at=NOW,
                    excerpt="Bonjour",
                ),
                ExchangedEmail(id="e2", direction="sent", subject="Relance", occurred_at=NOW),
            ]
        ),
        "events": section(
            events=[
                SharedEvent(
                    id="v1",
                    summary="Chantier",
                    starts_at=NOW,
                    ends_at=NOW,
                    is_past=False,
                    role="organizer",
                    organizer_known=True,
                ),
                SharedEvent(
                    id="v2",
                    summary="Point",
                    starts_at=NOW,
                    ends_at=None,
                    is_past=True,
                    role="attendee",
                    organizer_known=True,
                ),
                SharedEvent(
                    id="v3",
                    summary="Apple",
                    starts_at=NOW,
                    ends_at=None,
                    is_past=False,
                    role="attendee",
                    organizer_known=False,
                ),
            ]
        ),
        "addresses_used": 1,
        "window_days": 90,
        "email_window_days": 365,
    }
    return RelationContext(**{**base, **over})  # type: ignore[arg-type]


def scope(**over: object) -> RelationOverviewScope:
    """A 360° scope, defaults unless overridden."""
    return RelationOverviewScope(**over)  # type: ignore[arg-type]


NO_ADDRESS_CONTEXT = context(
    emails=section(ContextStatus.NO_ADDRESS),
    events=section(ContextStatus.NO_ADDRESS),
    addresses_used=0,
)
ERROR_CONTEXT = context(
    emails=section(ContextStatus.ERROR),
    events=section(ContextStatus.NOT_CONFIGURED),
)
EMPTY_CONTEXT = context(
    contact=section(ContextStatus.EMPTY),
    emails=section(ContextStatus.EMPTY),
    events=section(ContextStatus.EMPTY),
)
EMPTY_DETAIL = detail(
    open_loops=[],
    open_loops_total=0,
    recent_calls=[],
    recent_calls_total=0,
    memories=[],
    memories_total=0,
    peer_messages=[],
    peer_messages_total=0,
    peer_link=None,
    is_peer=False,
)

#: Default semantic recall. ``None`` means "the embedding could not be
#: computed", which is a DIFFERENT answer from an empty list.
DEFAULT_MEMORIES = ["Aime la randonnée"]
