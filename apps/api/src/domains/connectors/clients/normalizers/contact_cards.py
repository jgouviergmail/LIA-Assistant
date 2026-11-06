"""A contact as a vCard file, on the way out and on the way in (ADR-369, lot 9).

One door in both directions: a card is read into the vocabulary the three providers share
(``normalize_vcard``), and a contact leaves through the same reading (``written_contact``), so
what an export writes is what an import takes. A file is somebody else's until it is read: it is
decoded with what it declares, an old export's Latin-1 included, and it is cut into cards before
any is read, so a card nobody can read is counted and costs only itself.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any, Final

import structlog
import vobject

from src.domains.connectors.clients.contact_details import NO_YEAR, ContactDetails
from src.domains.connectors.clients.normalizers.contact_values import (
    TypedAddress,
    TypedValue,
    addresses_read,
    values_read,
)
from src.domains.connectors.clients.normalizers.contacts_normalizer import (
    normalize_vcard,
    vcard_component,
)

logger = structlog.get_logger(__name__)

#: One card of a file; the lazy span ends at the first END, so a file is read once.
_CARD: Final = re.compile(r"BEGIN:VCARD\r?\n.*?END:VCARD", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True, slots=True)
class WrittenContact:
    """What a client's ``create_contact`` takes, read from a contact."""

    name: str
    organization: str | None
    notes: str | None
    emails: list[TypedValue]
    phones: list[TypedValue]
    addresses: list[TypedAddress]
    details: ContactDetails


def _first(person: Mapping[str, Any], field: str) -> Mapping[str, Any]:
    entries = person.get(field)
    if isinstance(entries, list) and entries and isinstance(entries[0], Mapping):
        return entries[0]
    return {}


def _birthday(person: Mapping[str, Any]) -> date | None:
    """A contact's birthday, in ``NO_YEAR`` when it has no year; None when it reads as no day."""
    day = _first(person, "birthdays").get("date")
    if not isinstance(day, Mapping):
        return None
    try:
        return date(day.get("year") or NO_YEAR, day["month"], day["day"])
    except KeyError, TypeError, ValueError:
        return None


def written_contact(person: Mapping[str, Any]) -> WrittenContact | None:
    """A contact as a create takes it; None when nothing in it can name it.

    Args:
        person: A contact, in the vocabulary the three providers share.

    Returns:
        What to write, going by its name, else its parts, its company, an address or a number.
    """
    names = _first(person, "names")
    organization = _first(person, "organizations")
    emails = values_read(person.get("emailAddresses"))
    phones = values_read(person.get("phoneNumbers"))
    given, family = names.get("givenName"), names.get("familyName")
    candidates = (
        names.get("displayName"),
        " ".join(part for part in (given, family) if part),
        organization.get("name"),
        emails[0]["value"] if emails else None,
        phones[0]["value"] if phones else None,
    )
    name = next((str(item).strip() for item in candidates if item and str(item).strip()), None)
    if name is None:
        return None
    return WrittenContact(
        name=name,
        organization=organization.get("name"),
        notes=_first(person, "biographies").get("value"),
        emails=emails,
        phones=phones,
        addresses=addresses_read(person.get("addresses")),
        details=ContactDetails(
            given_name=given or None,
            family_name=family or None,
            job_title=organization.get("title") or None,
            website=_first(person, "urls").get("value") or None,
            birthday=_birthday(person),
        ),
    )


def vcard_of_person(person: Mapping[str, Any]) -> str:
    """One contact as a vCard; nothing for a contact nothing can name.

    Args:
        person: A contact, in the vocabulary the three providers share.

    Returns:
        The card, every website on it (a create takes the first alone).
    """
    written = written_contact(person)
    if written is None:
        return ""
    card = vcard_component(
        written.name,
        organization=written.organization,
        notes=written.notes,
        emails=written.emails,
        phones=written.phones,
        addresses=written.addresses,
        details=written.details,
    )
    websites = person.get("urls")
    for extra in websites[1:] if isinstance(websites, list) else ():
        if isinstance(extra, Mapping) and extra.get("value"):
            card.add("url").value = str(extra["value"])
    return str(card.serialize())


def _decoded(data: bytes) -> str:
    """A file's text: UTF-8, else an old export's Latin-1 (a mark before a card is no card)."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def read_cards(data: bytes, at_most: int | None = None) -> list[dict[str, Any]]:
    """The contacts a file holds, in the vocabulary the three providers share.

    Args:
        data: The file; anybody's.
        at_most: Reading stops here: a bound refused needs no more of the file.

    Returns:
        Its cards in order, one nobody can read as an empty contact; none for a file holding none.
    """
    people: list[dict[str, Any]] = []
    for found in _CARD.finditer(_decoded(data)):
        if at_most is not None and len(people) >= at_most:
            break
        people.append(_person_of(found.group()))
    return people


def _person_of(card_text: str) -> dict[str, Any]:
    """A card as a contact: an empty one when nobody can read it, so it is said, not lost."""
    try:
        return normalize_vcard(vobject.readOne(card_text, ignoreUnreadable=True).serialize())
    except Exception as error:  # noqa: BLE001 - a card nobody can read costs only itself
        logger.debug("vcard_card_unreadable", error_type=type(error).__name__)
        return {}


__all__ = ["WrittenContact", "read_cards", "vcard_of_person", "written_contact"]
