"""Contacts leave and arrive as vCard files, by the person's own hand (ADR-369, lot 9).

An export reads the address book a page at a time under the account's one transfer, up to
``WORKBENCH_CONTACTS_EXPORT_MAX``; a cut is said in the file's name, the one place a download can
say it. An import is bounded by its size and its count, runs once per submission (a replay would
make every contact twice), one card at a time (Google asks mutations for one person to be
sequential), and answers card by card: a card refused costs only itself. Reading a file and
writing one run off the event loop.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final
from uuid import UUID

from src.core.constants import (
    WORKBENCH_CONTACTS_EXPORT_MAX,
    WORKBENCH_CONTACTS_IMPORT_MAX_CARDS,
)
from src.domains.connectors.clients.normalizers.contact_cards import (
    WrittenContact,
    read_cards,
    vcard_of_person,
    written_contact,
)
from src.domains.connectors.clients.protocols import ContactsClientProtocol
from src.domains.workbench.availability import listing_page_size
from src.domains.workbench.calls import provider_call
from src.domains.workbench.clients import open_tool_client
from src.domains.workbench.contacts_service import refuse_other_contact
from src.domains.workbench.downloads import one_transfer
from src.domains.workbench.errors import NOT_A_CONTACTS_FILE, TOO_MANY_CARDS, refuse
from src.domains.workbench.features import WorkbenchTool
from src.domains.workbench.idempotency import run_once
from src.domains.workbench.schemas.contacts import ContactsImported, ImportFailure
from src.domains.workbench.selection_acts import act_outcome, settle_each

_TOOL = WorkbenchTool.CONTACTS
#: What a card carries of a contact, and no more: an export reads nothing it does not write.
_EXPORTED_FIELDS: Final = [
    "names",
    "emailAddresses",
    "phoneNumbers",
    "addresses",
    "organizations",
    "urls",
    "birthdays",
    "biographies",
]
_WHOLE_BOOK: Final = "contacts.vcf"
#: One card at a time: Google asks mutations for one person to be sequential.
_IMPORT_CONCURRENCY: Final = 1


@dataclass(frozen=True, slots=True)
class ContactsFile:
    """A vCard file and the name it leaves under."""

    data: bytes
    filename: str


async def export_contacts(user_id: UUID, contact_id: str | None) -> ContactsFile:
    """One contact, or the address book up to the published bound, as a vCard file.

    Args:
        user_id: The account.
        contact_id: The contact; None for the whole book.

    Returns:
        The file; an empty book is an empty file.
    """
    if contact_id is not None:
        refuse_other_contact(contact_id)
    async with one_transfer(user_id), open_tool_client(_TOOL, user_id) as opened:
        client: ContactsClientProtocol = opened.client
        async with provider_call(_TOOL, "export", act=False):
            if contact_id is None:
                people, cut = await _the_book(client)
            else:
                people, cut = [await client.get_person(contact_id, use_cache=False)], False
    data = await asyncio.to_thread(_cards_of, people)
    return ContactsFile(data, _filename(people, contact_id, cut=cut))


async def _the_book(client: ContactsClientProtocol) -> tuple[list[Mapping[str, Any]], bool]:
    """The account's contacts, fresh, and whether the bound cut them."""
    people: list[Mapping[str, Any]] = []
    token: str | None = None
    while True:
        raw = await client.list_connections(
            page_size=listing_page_size(),
            page_token=token,
            use_cache=False,
            fields=_EXPORTED_FIELDS,
        )
        people.extend(raw.get("connections") or [])
        token = raw.get("next_page_token") or raw.get("nextPageToken") or None
        if token is None or len(people) >= WORKBENCH_CONTACTS_EXPORT_MAX:
            break
    cut = token is not None or len(people) > WORKBENCH_CONTACTS_EXPORT_MAX
    return people[:WORKBENCH_CONTACTS_EXPORT_MAX], cut


def _cards_of(people: Sequence[Mapping[str, Any]]) -> bytes:
    return "".join(vcard_of_person(person) for person in people).encode("utf-8")


def _filename(people: Sequence[Mapping[str, Any]], contact_id: str | None, *, cut: bool) -> str:
    if contact_id is None:
        return f"contacts-first-{len(people)}.vcf" if cut else _WHOLE_BOOK
    written = written_contact(people[0])
    return f"{written.name}.vcf" if written else _WHOLE_BOOK


async def import_contacts(user_id: UUID, data: bytes, key: UUID) -> ContactsImported:
    """Make a contact of each card of a file, once per submission.

    Args:
        user_id: The account.
        data: The file; anybody's.
        key: The submission's key.

    Returns:
        How many became contacts, and each card that did not.
    """
    people = await asyncio.to_thread(read_cards, data, WORKBENCH_CONTACTS_IMPORT_MAX_CARDS + 1)
    if not people:
        refuse(NOT_A_CONTACTS_FILE)
    if len(people) > WORKBENCH_CONTACTS_IMPORT_MAX_CARDS:
        refuse(TOO_MANY_CARDS, max_items=WORKBENCH_CONTACTS_IMPORT_MAX_CARDS)
    cards = {str(place): written_contact(person) for place, person in enumerate(people, start=1)}

    async def create_each() -> ContactsImported:
        return await _create_each(user_id, cards)

    return await run_once(
        user_id,
        key,
        create_each,
        tool=_TOOL.value,
        record=lambda answer: {"imported": str(answer.done)},
    )


async def _create_each(
    user_id: UUID, cards: Mapping[str, WrittenContact | None]
) -> ContactsImported:
    """Each card that names someone, in the file's order; the others are said."""
    named = {place: card for place, card in cards.items() if card is not None}

    async with open_tool_client(_TOOL, user_id) as opened:
        client: ContactsClientProtocol = opened.client

        async def create(place: str) -> None:
            card = named[place]
            await client.create_contact(
                card.name,
                organization=card.organization,
                notes=card.notes,
                emails=card.emails,
                phones=card.phones,
                addresses=card.addresses,
                details=card.details,
            )

        async with provider_call(_TOOL, "import", act=True):
            places = list(named)
            settled = await settle_each(places, create, concurrency=_IMPORT_CONCURRENCY)
            outcome = act_outcome(places, settled, tool=_TOOL.value)
    refused = {item.id for item in outcome.failed} | set(cards) - set(named)
    return ContactsImported(
        done=len(outcome.done),
        failed=[
            ImportFailure(position=int(place), name=card.name if card else "")
            for place, card in cards.items()
            if place in refused
        ],
    )


__all__ = ["ContactsFile", "export_contacts", "import_contacts"]
