"""The contact-card section, and the identity it unlocks (Bloc C, B1).

This fetcher is the keystone of the three provider sections: mail and calendar
are queried by ADDRESS, and the address book is where a CRM name becomes one.

The provider search is a HINT, never a verdict. Google's
``people:searchContacts`` matches prefixes and substrings, Apple filters
locally, Microsoft runs KQL — three different notions of "close enough". Every
candidate is therefore verified against ``fold_name``, the same chokepoint the
CRM buckets on, so a fuzzy match can never attach someone else's addresses to
this card. Under-matching costs an empty section; over-matching would show one
person's mail under another's name.

All three providers normalize their contacts to the Google People shape
(``{"results": [{"person": {...}}]}``) — see ``clients/normalizers`` — so one
parser serves them all. Their COVERAGE differs, though: names, emails, phones,
postal addresses, birthday, biography and organization come from all three;
relations, links, important dates and messaging handles exist only on Google.
A block a provider does not store comes back empty and the card omits it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from src.domains.relations.providers.client import open_category_client
from src.domains.relations.providers.schemas import (
    ContactCard,
    ContactEmail,
    ContactPhone,
    ContactValue,
)
from src.domains.shared.text_normalization import fold_name

if TYPE_CHECKING:
    from uuid import UUID

logger = structlog.get_logger(__name__)

#: Everything the address book holds about the person, minus the photo (a
#: third party's likeness — showing it is an identity decision, not a data
#: one). Parity is uneven and the card says so by omission: the first block is
#: normalized by all three providers, the second exists only on Google.
_CARD_FIELDS = [
    "names",
    "nicknames",
    "emailAddresses",
    "phoneNumbers",
    "addresses",
    "birthdays",
    "biographies",
    "organizations",
    # Google-only below.
    "occupations",
    "relations",
    "urls",
    "events",
    "imClients",
]

#: The provider search is fuzzy, so a few candidates may precede the right one.
_SEARCH_MAX_RESULTS = 10


def _display_name(person: dict[str, Any]) -> str:
    """Best display name of a normalized person record ("" when nameless)."""
    names = person.get("names") or []
    if not names or not isinstance(names[0], dict):
        return ""
    return str(names[0].get("displayName") or "").strip()


def _labelled_values(person: dict[str, Any], key: str) -> list[tuple[str, str | None]]:
    """Extract (value, label) pairs from one normalized multi-valued field."""
    pairs: list[tuple[str, str | None]] = []
    for entry in person.get(key) or []:
        if not isinstance(entry, dict):
            continue
        value = str(entry.get("value") or "").strip()
        if not value:
            continue  # a blank entry is not a way to reach anyone
        label = str(entry.get("type") or "").strip() or None
        pairs.append((value, label))
    return pairs


def _organization(person: dict[str, Any]) -> str | None:
    """First organization name, when the provider stored one."""
    for entry in person.get("organizations") or []:
        if isinstance(entry, dict):
            name = str(entry.get("name") or "").strip()
            if name:
                return name
    return None


def _first_text(person: dict[str, Any], field: str, *keys: str) -> str | None:
    """First non-empty value of a single-valued field, trying each key."""
    for entry in person.get(field) or []:
        if not isinstance(entry, dict):
            continue
        for key in keys:
            text = str(entry.get(key) or "").strip()
            if text:
                return text
    return None


def _occupation(person: dict[str, Any]) -> str | None:
    """Job title, from whichever field the provider filled.

    ``occupations`` is Google-only; the title carried INSIDE an organization is
    normalized by all three (Apple maps the vCard TITLE, Graph maps jobTitle).
    Reading both is what makes this line appear for an Apple contact at all.
    """
    return _first_text(person, "occupations", "value") or _first_text(
        person, "organizations", "title"
    )


def _partial_date(date: Any) -> str | None:
    """Format provider date PARTS as an ISO-ish token, year optional.

    All three providers normalize a birthday to Google's shape
    (``{"year": N, "month": N, "day": N}``) and an address book routinely
    holds a day and month with NO year. ``--MM-DD`` is RFC 6350's own notation
    for exactly that, so the missing year stays missing instead of being
    invented — and the frontend, which owns date formatting for six locales,
    gets a token it can parse rather than one country's digit order.
    """
    if not isinstance(date, dict):
        return None
    try:
        day, month = int(date["day"]), int(date["month"])
        year = int(date["year"]) if date.get("year") else None
    except KeyError, TypeError, ValueError:
        # A date this shape cannot express is dropped, never half-shown: the
        # card would otherwise carry a fragment nobody can read as a date.
        return None
    prefix = f"{year:04d}" if year else "-"
    return f"{prefix}-{month:02d}-{day:02d}"


def _birthday(person: dict[str, Any]) -> str | None:
    """Birthday: the date parts when stored, else the user's own words.

    Parts win over ``text`` — they are what every provider normalizes and what
    the frontend can localize. ``text`` is free-form (Google lets one type
    anything) so it is passed through untouched when it is all there is.
    """
    for entry in person.get("birthdays") or []:
        if not isinstance(entry, dict):
            continue
        token = _partial_date(entry.get("date"))
        if token:
            return token
        text = str(entry.get("text") or "").strip()
        if text:
            return text
    return None


def _values(
    person: dict[str, Any],
    field: str,
    *keys: str,
    label_keys: tuple[str, ...] = ("type",),
) -> list[ContactValue]:
    """Every labelled entry of one multi-valued field.

    Args:
        person: The normalized person record.
        field: Field to read.
        keys: Value keys, tried in order (providers name the same thing
            differently — ``person`` for a relation, ``username`` for a chat
            handle).
        label_keys: Label keys, tried in order (a chat handle is better
            labelled by its protocol than by home/work).
    """
    found: list[ContactValue] = []
    for entry in person.get(field) or []:
        if not isinstance(entry, dict):
            continue
        value = next((text for key in keys if (text := str(entry.get(key) or "").strip())), "")
        if not value:
            continue  # a blank entry says nothing
        label = next(
            (text for key in label_keys if (text := str(entry.get(key) or "").strip())), None
        )
        found.append(ContactValue(value=value, label=label))
    return found


def _dated_values(person: dict[str, Any], field: str) -> list[ContactValue]:
    """Entries whose value IS a date (Google's ``events``: anniversaries…).

    Separate from ``_values`` because the value is a parts dict, not a string:
    stringifying it would put ``{'year': 2011, ...}`` on the card.
    """
    found: list[ContactValue] = []
    for entry in person.get(field) or []:
        if not isinstance(entry, dict):
            continue
        token = _partial_date(entry.get("date"))
        if not token:
            continue
        label = str(entry.get("type") or "").strip() or None
        found.append(ContactValue(value=token, label=label))
    return found


def _to_card(person: dict[str, Any], display_name: str) -> ContactCard:
    """Map one normalized person record onto the CRM card contract.

    Everything the provider stored, block by block. A provider that holds none
    of a block yields an empty list — the card then simply does not show it,
    rather than showing a placeholder for something nobody wrote down.
    """
    return ContactCard(
        display_name=display_name,
        nickname=_first_text(person, "nicknames", "value"),
        organization=_organization(person),
        occupation=_occupation(person),
        birthday=_birthday(person),
        biography=_first_text(person, "biographies", "value"),
        emails=[
            ContactEmail(value=value, label=label)
            for value, label in _labelled_values(person, "emailAddresses")
        ],
        phones=[
            ContactPhone(value=value, label=label)
            for value, label in _labelled_values(person, "phoneNumbers")
        ],
        # All three providers pre-format the postal address (Apple and Graph
        # build `formattedValue` in their normalizers); rebuilding it from
        # parts would impose one country's ordering on every address book.
        addresses=_values(person, "addresses", "formattedValue"),
        relations=_values(person, "relations", "person"),
        links=_values(person, "urls", "value"),
        important_dates=_dated_values(person, "events"),
        messaging=_values(person, "imClients", "username", label_keys=("protocol", "type")),
    )


async def fetch_contact_card(
    user_id: UUID, *, target_key: str, search_name: str
) -> ContactCard | None:
    """The address-book entry for ONE relationship, verified by folding.

    Args:
        user_id: Owner of the address book.
        target_key: Folded CRM name — the identity that must match EXACTLY.
        search_name: Spelling handed to the provider search (a hint only).

    Returns:
        The matching card, or None when the address book holds no one under
        that exact identity.

    Raises:
        ProviderNotConfigured: When no contacts connector is usable. Left to
            propagate: "no address book" and "nobody by that name" are
            different answers, and only the caller can render the difference.
    """
    if not target_key:
        return None
    async with open_category_client("contacts", user_id) as opened:
        client = opened.client
        response = await client.search_contacts(
            search_name,
            max_results=_SEARCH_MAX_RESULTS,
            use_cache=True,
            fields=_CARD_FIELDS,
        )
    for result in response.get("results") or []:
        person = result.get("person") if isinstance(result, dict) else None
        if not isinstance(person, dict):
            continue
        name = _display_name(person)
        if fold_name(name) != target_key:
            continue  # the provider's idea of "close", not ours
        return _to_card(person, name)
    return None
