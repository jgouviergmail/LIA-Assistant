"""A mail listing as ONE search the three clients carry (ADR-369, F12).

The person's words pass as written: the Gmail-style syntax is the screen's
search language, and the three clients translate it, so ``from:alice`` means
the sender everywhere. The chips follow, then the FOLDER, last — Graph and
IMAP read the last folder a query names, so the pane's folder stays the scope
whatever the words say (Gmail ANDs them). A Gmail label of the person's own is
read by its id (``labelIds``, documented), never by a ``label:`` term Gmail is
not known to read ids in; a folder elsewhere is named, between quotes when it
has spaces. A day is the person's: Gmail reads ``after:YYYY/MM/DD`` at
Pacific midnight, so it is given the instant itself; Graph and IMAP read the
day. What a provider cannot carry is refused before anything is sent — never
dropped in silence (IMAP has no criterion for attachments).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Final
from zoneinfo import ZoneInfo

from src.domains.connectors.models import ConnectorType
from src.domains.workbench.errors import INVALID_REQUEST, NOT_SUPPORTED_BY_PROVIDER, refuse
from src.domains.workbench.features import PROVIDER_FEATURES, WorkbenchFeature
from src.domains.workbench.schemas.mail import SYSTEM_FOLDER_PREFIX, MailListing, MailRole

#: The system places each provider has, in the order the pane draws them.
#: Gmail keeps no archive folder: an archived message is one without INBOX, and
#: « all mail » is where it is found again.
SYSTEM_PLACES: Final[dict[ConnectorType, tuple[MailRole, ...]]] = {
    ConnectorType.GOOGLE_GMAIL: ("inbox", "starred", "sent", "drafts", "all", "spam", "trash"),
    ConnectorType.MICROSOFT_OUTLOOK: (
        "inbox",
        "starred",
        "sent",
        "drafts",
        "archive",
        "spam",
        "trash",
    ),
    ConnectorType.APPLE_EMAIL: ("inbox", "starred", "sent", "drafts", "archive", "spam", "trash"),
}

#: How each place is named in the language the three clients translate.
_PLACE_TERMS: Final[dict[MailRole, str]] = {
    "inbox": "in:inbox",
    "starred": "is:starred",
    "sent": "in:sent",
    "drafts": "in:drafts",
    "archive": "in:archive",
    # Gmail's own default: a search with no place reads all but the spam and the trash.
    "all": "",
    "spam": "in:spam",
    "trash": "in:trash",
}
#: What a folder name cannot hold and still be one quoted value of the query.
_UNQUOTABLE: Final = frozenset('"\\')


@dataclass(frozen=True, slots=True)
class MailSearch:
    """What one listing asks its client: a query, and Gmail label ids."""

    query: str
    label_ids: tuple[str, ...] = ()


def compose_query(provider: ConnectorType, listing: MailListing, zone: ZoneInfo) -> MailSearch:
    """The search a listing amounts to on ``provider``.

    Args:
        provider: The account's mail provider.
        listing: The folder, the person's words and the chips.
        zone: The account's zone (where a day starts).

    Returns:
        The query, and the Gmail label ids a label folder is read by.

    Raises:
        BaseAPIException: ``not_supported_by_provider`` for a place or a chip
            the provider cannot carry; ``invalid_request`` for a folder name
            the language cannot hold.
    """
    terms = [words] if (words := (listing.q or "").strip()) else []
    if listing.unread:
        terms.append("is:unread")
    if listing.attachments:
        if WorkbenchFeature.ATTACHMENT_FILTER not in PROVIDER_FEATURES[provider]:
            refuse(NOT_SUPPORTED_BY_PROVIDER)
        terms.append("has:attachment")
    for operator, day in (("after", listing.after), ("before", listing.before)):
        if day is not None:
            terms.append(f"{operator}:{_day(provider, day, zone)}")
    folder = listing.folder
    if folder.startswith(SYSTEM_FOLDER_PREFIX):
        terms += [term for term in (_place(provider, folder),) if term]
    elif provider is ConnectorType.GOOGLE_GMAIL:
        return MailSearch(" ".join(terms), label_ids=(folder,))
    else:
        terms.append(_named(folder))
    return MailSearch(" ".join(terms))


def _day(provider: ConnectorType, day: date, zone: ZoneInfo) -> str:
    if provider is ConnectorType.GOOGLE_GMAIL:
        return str(int(datetime.combine(day, time.min, tzinfo=zone).timestamp()))
    return day.strftime("%Y/%m/%d")


def _place(provider: ConnectorType, folder: str) -> str:
    """A system place's term, refused where the provider has no such place."""
    for role in SYSTEM_PLACES[provider]:
        if folder == f"{SYSTEM_FOLDER_PREFIX}{role}":
            return _PLACE_TERMS[role]
    refuse(NOT_SUPPORTED_BY_PROVIDER)


def _named(folder: str) -> str:
    """A folder of the person's own, by name — one quoted value when it has spaces."""
    if _UNQUOTABLE & set(folder):
        refuse(INVALID_REQUEST)
    return f'label:"{folder}"' if any(char.isspace() for char in folder) else f"label:{folder}"
