"""Projections of one relationship's sources into the 360° payload blocks.

Pure functions, no I/O: every one of them takes what a fetcher already read and
returns the shape the assistant (or the debrief prompt) receives. Keeping them
free of I/O is what makes the honesty rules testable without a provider.

Two rules run through all of them, and both come from measured defects:

- **a page always ships its exact total** when the source can prove one
  (ADR-185); when it cannot — a provider page, or a list a direction filter
  narrowed — it ships no total at all rather than an inexact one;
- **a section that could not be read carries no block**, and is named in
  ``unavailable`` instead. Emitting ``"emails": []`` beside
  ``unavailable: ["emails"]`` states "nothing found" and "I could not look" in
  one payload, and a model believes the list (ADR-184).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from src.domains.relations.overview_scope import (
    OverviewDirection,
    OverviewSection,
    RelationOverviewScope,
)
from src.domains.relations.providers.schemas import (
    ContactCard,
    ContactValue,
    ContextStatus,
    RelationContext,
)
from src.domains.relations.schemas import RelationDetail

#: The three sections that come from a connector, in payload order.
PROVIDER_SECTIONS = (
    OverviewSection.CONTACT,
    OverviewSection.EMAILS,
    OverviewSection.EVENTS,
)

#: Statuses that mean "the question was asked and never answered" — a missing
#: connector, a failed read, an identity with no address. Never "there is
#: nothing", and never "you excluded it".
UNREADABLE = frozenset(
    {ContextStatus.ERROR, ContextStatus.NOT_CONFIGURED, ContextStatus.NO_ADDRESS}
)

#: Statuses that carry no items to project. ``NOT_REQUESTED`` joins the
#: unreadable ones HERE and nowhere else: a section the reader excluded must
#: emit no block (it holds nothing), but it must not be reported as a gap
#: either — the question was deliberately never asked.
_NO_PAYLOAD = UNREADABLE | {ContextStatus.NOT_REQUESTED}


def directions_of(scope: RelationOverviewScope) -> set[str]:
    """Directions the reader kept — mail and relayed messages share them."""
    return {direction.value for direction in scope.directions}


def local_blocks(detail: RelationDetail, scope: RelationOverviewScope) -> dict[str, Any]:
    """The database-local half, filtered by what the reader ticked.

    Each list is a PAGE, and every page ships its EXACT total (ADR-185): the
    totals come from database aggregates over the whole set, so five rows out
    of a hundred and thirty-seven can be said as such. Without them the
    assistant reads five rows and states "you have five open commitments" —
    the same under-report the CRM cards were fixed for, one surface later.

    The relayed messages are the exception, and deliberately: the direction
    filter narrows the LIST but not the stored total, so a total would then
    describe a different set than the rows beside it. No total is the honest
    answer there — an inexact count must not exist.

    Args:
        detail: The relationship as the database-local half reports it.
        scope: What the reader ticked on the relationship card.

    Returns:
        The scoped blocks, keyed as the payload carries them.
    """
    blocks: dict[str, Any] = {}
    if scope.includes(OverviewSection.OPEN_LOOPS):
        blocks["open_commitments"] = [
            {
                "subject": loop.subject,
                "direction": loop.direction,
                "days_open": loop.days_open,
                # The DEADLINE, when one was captured. "What should I raise
                # next" is answered by what is due, so dropping it left the
                # most actionable field of the payload on the floor. Absent
                # rather than null: most commitments have none, and a key full
                # of nulls trains the model to mention them.
                **({"due_hint": loop.due_hint.isoformat()} if loop.due_hint else {}),
            }
            for loop in detail.open_loops[: scope.max_items]
        ]
        blocks["open_commitments_total"] = detail.open_loops_total
    if scope.includes(OverviewSection.CALLS):
        blocks["recent_calls"] = [
            {
                "objective": call.objective,
                "outcome": call.outcome,
                "summary": call.summary,
                # WHEN, like every other interaction in this payload. Without
                # it the assistant cannot place a call in time, and a request
                # about "recent interactions" walked straight past four of
                # them (production, 2026-08-01) — the one block that carried
                # no instant was the one block that went unused.
                "occurred_at": call.created_at.isoformat(),
            }
            for call in detail.recent_calls[: scope.max_items]
        ]
        blocks["recent_calls_total"] = detail.recent_calls_total
    if scope.includes(OverviewSection.PEER_MESSAGES):
        wanted = directions_of(scope)
        blocks["relayed_messages"] = [
            {
                "direction": message.direction,
                "text": message.content,
                "occurred_at": message.occurred_at.isoformat(),
            }
            for message in detail.peer_messages
            if message.direction in wanted
        ][: scope.max_items]
        if len(wanted) == len(OverviewDirection):
            # Unfiltered: the stored total describes exactly these rows.
            blocks["relayed_messages_total"] = detail.peer_messages_total
    return blocks


def _labelled(values: Sequence[ContactValue]) -> list[str]:
    """Flatten labelled values, keeping the label that makes them legible.

    "Claire Lefèvre" alone does not say she is his spouse, and a phone number
    without "mobile" is one the assistant cannot choose between. The label is
    dropped only when the provider stored none.
    """
    return [f"{item.value} ({item.label})" if item.label else item.value for item in values]


def card_block(card: ContactCard) -> dict[str, Any]:
    """The address-book entry, as the assistant reads it.

    The SAME content the card shows on screen — asking "what do you know about
    this person" and reading their file must not produce two different answers.
    Empty blocks are dropped rather than sent as ``[]``: a provider that stores
    no relations says nothing about whether this person has any, and a listed
    empty key invites the model to conclude one way (ADR-184).
    """
    fields: dict[str, Any] = {
        "display_name": card.display_name,
        "nickname": card.nickname,
        "organization": card.organization,
        "occupation": card.occupation,
        "birthday": card.birthday,
        "biography": card.biography,
        # Addresses stay bare: they are long, and "home"/"work" adds little to
        # a string that already names a street and a city.
        "emails": [email.value for email in card.emails],
        "addresses": [address.value for address in card.addresses],
        "links": [link.value for link in card.links],
        "phones": _labelled(card.phones),
        "relations": _labelled(card.relations),
        "important_dates": _labelled(card.important_dates),
        "messaging": _labelled(card.messaging),
    }
    return {key: value for key, value in fields.items() if value}


def _mail_block(context: RelationContext, scope: RelationOverviewScope) -> dict[str, Any]:
    """Mail exchanged, in the reader's chosen directions, plus its window."""
    wanted = directions_of(scope)
    return {
        "emails": [
            # `excerpt` is omitted, never null, when the provider returned no
            # preview: a key present with no value invites the assistant to
            # describe a message it has not read.
            {
                key: value
                for key, value in (
                    ("direction", email.direction),
                    ("subject", email.subject),
                    (
                        "occurred_at",
                        email.occurred_at.isoformat() if email.occurred_at else None,
                    ),
                    ("excerpt", email.excerpt),
                )
                if value is not None
            }
            for email in context.emails.emails
            if email.direction in wanted
        ][: scope.max_items],
        # The scope, never a total: a provider page proves none (ADR-185).
        "emails_window_days": context.email_window_days,
    }


def _meeting_block(context: RelationContext, scope: RelationOverviewScope) -> dict[str, Any]:
    """Meetings shared, in the reader's chosen roles, plus their window."""
    wanted_roles = {role.value for role in scope.roles}
    return {
        "events": [
            {
                "summary": event.summary,
                "role": event.role if event.organizer_known else "unknown",
                "starts_at": event.starts_at.isoformat() if event.starts_at else None,
                "ends_at": event.ends_at.isoformat() if event.ends_at else None,
                "is_past": event.is_past,
            }
            for event in context.events.events
            # A role nobody verified must not be filtered ON: under a provider
            # that exposes no organizer, filtering by role would silently drop
            # every meeting instead of admitting the distinction is unknown.
            if not event.organizer_known or event.role in wanted_roles
        ][: scope.max_items],
        "events_window_days": context.window_days,
    }


def peer_connection(detail: RelationDetail) -> dict[str, Any] | None:
    """The LIA connection behind this relationship, when there is one.

    Root-level context, NOT a scoped section: "you are connected since May,
    they share their availability, you share your task titles" describes the
    RELATIONSHIP, the way ``identity_confidence`` does — it is not a source of
    items a scope could narrow. It also costs nothing: the same ``build_detail``
    read already carries it, and a 360° on a connected peer that never says
    they are one omits the most relevant fact on the card.
    """
    link = detail.peer_link
    if link is None:
        return None
    block: dict[str, Any] = {
        "shared_by_me": [f"{share.domain}:{share.level}" for share in link.shared_by_me],
        "shared_with_me": [f"{share.domain}:{share.level}" for share in link.shared_with_me],
    }
    if link.connected_since:
        block["connected_since"] = link.connected_since.isoformat()
    return block


def provider_blocks(context: RelationContext, scope: RelationOverviewScope) -> dict[str, Any]:
    """The provider-backed half, filtered the same way.

    A section that could not be READ carries no block at all. Emitting
    ``"emails": []`` next to ``unavailable: ["emails"]`` states both "nothing
    found" and "I could not look" in the same payload — and the model believes
    the list, because a list is data and the other is a caveat (ADR-184).
    """
    blocks: dict[str, Any] = {}
    if scope.includes(OverviewSection.CONTACT) and context.contact.contact is not None:
        blocks["contact"] = card_block(context.contact.contact)
    if scope.includes(OverviewSection.EMAILS) and context.emails.status not in _NO_PAYLOAD:
        blocks.update(_mail_block(context, scope))
    if scope.includes(OverviewSection.EVENTS) and context.events.status not in _NO_PAYLOAD:
        blocks.update(_meeting_block(context, scope))
    return blocks


def unavailable_sections(context: RelationContext, scope: RelationOverviewScope) -> list[str]:
    """Sections the reader asked for that could not be read.

    Stated rather than silently empty: "I could not look" and "there is
    nothing" are different answers (ADR-184), and only the first is worth the
    assistant mentioning. A section the reader EXCLUDED is neither — it never
    reaches this list, because the scope gate below runs first.
    """
    payloads = (context.contact, context.emails, context.events)
    return [
        section.value
        for section, payload in zip(PROVIDER_SECTIONS, payloads, strict=True)
        if scope.includes(section) and payload.status in UNREADABLE
    ]
