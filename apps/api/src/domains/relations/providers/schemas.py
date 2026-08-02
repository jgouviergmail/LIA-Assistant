"""Provider-backed sections of the 360° view — the wire contract (Bloc C).

Three sections that reach OUTSIDE the database: the contact card, the mail
exchanged with that person, and the meetings you share. Their honesty rules
differ from the database-local ones on purpose:

- **no counts.** ADR-185 forbids a count that is not exact, and a provider page
  never proves how many rows exist behind it. So these sections carry items and
  the SCOPE they looked at (a window in days), never a total they cannot honor.
- **the identity is stated.** Mail and calendar are queried by ADDRESS, resolved
  from the user's own contact card. Which addresses answered is part of the
  payload: a section built on one of three addresses is a partial answer, and
  saying so is the difference between a lens and a claim.
- **a status per section**, so "I looked and found nothing" is never confused
  with "I could not look".
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ContextStatus(str, Enum):
    """Per-section outcome — drives the frontend rendering branch.

    Kinship with ``briefing.CardStatus`` is deliberate (same idea, same
    vocabulary) but the enum is local: importing it would tie ``relations`` to
    ``briefing`` for five string constants, and this surface needs one value
    briefing does not have (``NO_ADDRESS``).
    """

    OK = "ok"
    EMPTY = "empty"
    #: No connector active for this category — nothing to reconnect, nothing
    #: broken; the user simply has not plugged that provider in.
    NOT_CONFIGURED = "not_configured"
    #: The connector exists but the read failed (expired token, provider down).
    ERROR = "error"
    #: Mail and calendar only: no address could be resolved for this person, so
    #: the question was never asked. NOT the same as "nothing found" —
    #: reporting an empty result here would be a negative we never verified.
    NO_ADDRESS = "no_address"


class ContactValue(BaseModel):
    """One labelled entry of a multi-valued contact field.

    The shared shape of every list on the card: a value as the provider stored
    it, and the label it stored alongside (home, work, spouse…).
    """

    model_config = ConfigDict(frozen=True)

    value: str = Field(description="The value as stored in the address book.")
    label: str | None = Field(default=None, description="Provider type/label.")


class ContactEmail(ContactValue):
    """One address on the contact card."""


class ContactPhone(ContactValue):
    """One phone number on the contact card."""


class ContactCard(BaseModel):
    """The address-book entry matching this relationship, in full.

    Everything the provider stored about the person, because a CRM card that
    shows two fields out of ten is a card the reader stops trusting.

    Provider parity is NOT uniform and the payload says so by omission: names,
    emails, phones, postal addresses, birthday, biography and organization are
    normalized by all three providers; relations, links, important dates and
    messaging handles exist only on Google's People API. A provider that
    stores none of a block simply yields an empty list — never a placeholder,
    never an invented value.

    The photo is deliberately absent: it is a third party's likeness, and
    showing it is an identity decision, not a data completeness one.
    """

    model_config = ConfigDict(frozen=True)

    display_name: str = Field(description="Name as stored in the address book.")
    nickname: str | None = Field(default=None, description="Alternative name, when stored.")
    organization: str | None = Field(default=None, description="Company / role, when stored.")
    occupation: str | None = Field(default=None, description="Job title, when stored.")
    birthday: str | None = Field(
        default=None,
        description=(
            "``YYYY-MM-DD``, or ``--MM-DD`` when the address book holds no "
            "year (RFC 6350's own notation for a partial date). A string and "
            "not a date on purpose: a missing year must stay missing, and "
            "formatting belongs to the frontend, which knows the locale. Free "
            "text when that is all the provider stored."
        ),
    )
    biography: str | None = Field(default=None, description="Free-form note, when stored.")
    emails: list[ContactEmail] = Field(default_factory=list)
    phones: list[ContactPhone] = Field(default_factory=list)
    addresses: list[ContactValue] = Field(
        default_factory=list, description="Postal addresses, formatted by the provider."
    )
    relations: list[ContactValue] = Field(
        default_factory=list, description="People this person is related to (Google only)."
    )
    links: list[ContactValue] = Field(default_factory=list, description="Web links (Google only).")
    important_dates: list[ContactValue] = Field(
        default_factory=list,
        description=(
            "Anniversaries and the like, same date notation as ``birthday`` " "(Google only)."
        ),
    )
    messaging: list[ContactValue] = Field(
        default_factory=list, description="Messaging handles (Google only)."
    )


class ExchangedEmail(BaseModel):
    """One message exchanged with this person, either direction."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="Provider message id — the stable render key.")
    direction: str = Field(description="received | sent, relative to the CRM owner.")
    subject: str = Field(description="Subject line, or a stated placeholder.")
    occurred_at: datetime | None = Field(
        default=None, description="UTC instant, when the provider gave a usable one."
    )
    excerpt: str | None = Field(
        default=None,
        description=(
            "First words of the message, capped at "
            "``relations_provider_email_excerpt_max_chars``. This is the preview "
            "the provider returns WITH the search — free — never the full body, "
            "which would cost one call per message. Absent when the provider "
            "gave none: an empty string would render as a blank line claiming "
            "the message had no content."
        ),
    )


class SharedEvent(BaseModel):
    """One calendar event this person shares with the CRM owner."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="Provider event id — the stable render key.")
    summary: str = Field(description="Event title, or a stated placeholder.")
    starts_at: datetime | None = Field(default=None, description="UTC start, when parseable.")
    ends_at: datetime | None = Field(
        default=None,
        description=(
            "UTC end, when the provider gave one. Null rather than guessed: a "
            "meeting with an invented duration is a claim the calendar never "
            "made. All-day ranges keep the provider's EXCLUSIVE end date."
        ),
    )
    is_past: bool = Field(description="Whether the event already happened.")
    role: str = Field(
        default="attendee",
        description="organizer | attendee — the person's part in this meeting.",
    )
    organizer_known: bool = Field(
        default=False,
        description=(
            "Whether the provider exposed organizers at all. Apple's events "
            "carry none, so the split must read UNKNOWN rather than "
            "'organized nothing' — a negative nobody verified (ADR-184)."
        ),
    )


class ContextSection(BaseModel):
    """Generic envelope — one shape for the three sections."""

    model_config = ConfigDict(frozen=True)

    status: ContextStatus
    from_cache: bool = Field(
        default=False,
        description="True when served from the section cache rather than fetched live.",
    )
    generated_at: datetime = Field(description="UTC instant this payload was produced.")
    contact: ContactCard | None = Field(default=None, description="Contact section payload.")
    emails: list[ExchangedEmail] = Field(default_factory=list)
    events: list[SharedEvent] = Field(default_factory=list)


class RelationContext(BaseModel):
    """The three provider-backed sections of one relationship's 360° view."""

    model_config = ConfigDict(frozen=True)

    contact: ContextSection
    emails: ContextSection
    events: ContextSection
    addresses_used: int = Field(
        default=0,
        ge=0,
        description=(
            "How many addresses of the contact card the mail and event lookups "
            "actually used. The reader is told when an answer rests on part of "
            "an identity — never shown the addresses themselves, which the "
            "contact section already carries when it is available."
        ),
    )
    window_days: int = Field(
        default=0,
        ge=0,
        description=(
            "Half-window, in days, scanned around today for shared events. "
            "Stated instead of a total: a provider page cannot prove how many "
            "events exist, and ADR-185 forbids a count that is not exact."
        ),
    )
    email_window_days: int = Field(
        default=0,
        ge=0,
        description=(
            "How far back mail was searched. Wider than the event window on "
            "purpose — correspondence is sparser than meetings — and stated "
            "for the same reason: a page proves no total."
        ),
    )
