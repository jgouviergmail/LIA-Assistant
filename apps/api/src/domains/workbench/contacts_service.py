"""The contacts of the « Tools » section, by the person's own hand (ADR-369, D4).

Each call opens the account's contacts provider through the door — no session
held while it answers (ADR-304) — under the workbench's failure contract
(``provider_call``), and reads FRESH: the person's own view, never the
assistant's cache. A contact's e-mails, phones and addresses travel as typed
lists, the write contract the three clients share (``normalizers/
contact_values``): a list sent replaces that list, one left out is kept, one the
provider cannot hold is refused whole with its bound. A create runs once per
submission (``run_once``: the providers carry no idempotency of their own). A
search and a group, answered in one go, say when they may hold more (ADR-185).
« Other contacts » are Google's (the descriptor), and Google reads, changes and
deletes none of them by its id: refused unsent. What a contact
holds beyond its lists goes as ``ContactDetails`` (``clients/contact_details``).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final
from uuid import UUID

from src.core.constants import (
    GOOGLE_CONTACT_GROUP_MAX_MEMBERS,
    GOOGLE_CONTACTS_SEARCH_PAGE_MAX,
    GOOGLE_OTHER_CONTACTS_SEARCH_MAX,
)
from src.domains.connectors.clients.contact_details import ContactDetails, birthday_text
from src.domains.connectors.clients.normalizers.contact_order import contact_order_key
from src.domains.connectors.clients.normalizers.contact_values import (
    TypedAddress,
    TypedValue,
    addresses_read,
    values_read,
)
from src.domains.connectors.clients.protocols import ContactsClientProtocol
from src.domains.connectors.models import ConnectorType
from src.domains.workbench.availability import listing_page_size
from src.domains.workbench.calls import provider_call
from src.domains.workbench.clients import open_tool_client
from src.domains.workbench.errors import NOT_SUPPORTED_BY_PROVIDER, refuse
from src.domains.workbench.features import PROVIDER_FEATURES, WorkbenchFeature, WorkbenchTool
from src.domains.workbench.idempotency import run_once
from src.domains.workbench.schemas.contacts import (
    Contact,
    ContactAddress,
    ContactAddressInput,
    ContactChange,
    ContactGroup,
    ContactGroups,
    ContactsPage,
    ContactsQuery,
    ContactSummary,
    ContactValue,
    ContactValueInput,
    NewContact,
    OtherContactSave,
)

_TOOL = WorkbenchTool.CONTACTS
#: What a group's member page reads of each person.
_MEMBER_FIELDS: Final = ["names", "emailAddresses", "phoneNumbers", "organizations"]
_USER_GROUP: Final = "USER_CONTACT_GROUP"
#: What names a contact met in mail and never saved: the search's answer is all there is.
_OTHER_CONTACT_PREFIX: Final = "otherContacts/"


async def list_contacts(user_id: UUID, query: ContactsQuery) -> ContactsPage:
    """One page: the account's contacts by cursor, a search, or a group (Google)."""
    async with open_tool_client(_TOOL, user_id) as opened:
        client: ContactsClientProtocol = opened.client
        if query.group is not None:
            _require(opened.connector_type, WorkbenchFeature.CONTACT_GROUPS)
            return await _group_page(opened.client, query.group, query.page_token)
        size = _search_size() if query.q is not None else listing_page_size()
        async with provider_call(_TOOL, "list", act=False):
            if query.q is not None:
                raw = await client.search_contacts(query.q, max_results=size, use_cache=False)
            else:
                raw = await client.list_connections(
                    page_size=size, page_token=query.page_token, use_cache=False
                )
    if query.q is not None:
        return _found(raw.get("results") or [], size)
    return ContactsPage(
        items=[_summary(person) for person in raw.get("connections") or []],
        next_page_token=raw.get("next_page_token") or raw.get("nextPageToken") or None,
        truncated=False,
    )


async def search_other(user_id: UUID, q: str) -> ContactsPage:
    """« Other contacts » — met in mail, never saved (Google)."""
    async with open_tool_client(_TOOL, user_id) as opened:
        _require(opened.connector_type, WorkbenchFeature.OTHER_CONTACTS)
        size = _search_size()
        async with provider_call(_TOOL, "list_other", act=False):
            raw = await opened.client.search_other_contacts(q, max_results=size, use_cache=False)
    return _found(raw.get("results") or [], size)


async def list_groups(user_id: UUID) -> ContactGroups:
    """The account's contact groups, the person's own first."""
    async with open_tool_client(_TOOL, user_id) as opened:
        _require(opened.connector_type, WorkbenchFeature.CONTACT_GROUPS)
        async with provider_call(_TOOL, "list_groups", act=False):
            raw = await opened.client.list_contact_groups()
    groups = sorted(
        raw.get("contactGroups") or [],
        key=lambda group: group.get("groupType") != _USER_GROUP,
    )
    return ContactGroups(groups=[group_of(group) for group in groups])


def group_of(group: Mapping[str, Any]) -> ContactGroup:
    """A group as the screen reads it."""
    return ContactGroup(
        id=str(group.get("resourceName") or ""),
        name=str(group.get("formattedName") or group.get("name") or ""),
        count=group.get("memberCount"),
        own=group.get("groupType") == _USER_GROUP,
    )


async def read_contact(user_id: UUID, contact_id: str) -> Contact:
    """One contact, whole and typed."""
    refuse_other_contact(contact_id)
    async with open_tool_client(_TOOL, user_id) as opened:
        client: ContactsClientProtocol = opened.client
        async with provider_call(_TOOL, "read", act=False):
            raw = await client.get_person(contact_id, use_cache=False)
    return _contact(raw)


async def create_contact(user_id: UUID, request: NewContact) -> Contact:
    """Create a contact, once per submission."""

    async def create() -> Contact:
        async with open_tool_client(_TOOL, user_id) as opened:
            client: ContactsClientProtocol = opened.client
            async with provider_call(_TOOL, "create", act=True):
                raw = await client.create_contact(
                    request.name,
                    organization=request.organization,
                    notes=request.notes,
                    emails=_values(request.emails),
                    phones=_values(request.phones),
                    addresses=_addresses(request.addresses),
                    details=_details(request),
                )
        return _contact(raw)

    return await run_once(
        user_id,
        request.idempotency_key,
        create,
        tool=_TOOL.value,
        record=lambda made: {"contact_id": made.id},
    )


async def save_other_contact(user_id: UUID, request: OtherContactSave) -> Contact:
    """Keep a contact met in mail among the person's own, once per submission (Google)."""

    async def save() -> Contact:
        async with open_tool_client(_TOOL, user_id) as opened:
            _require(opened.connector_type, WorkbenchFeature.OTHER_CONTACTS)
            async with provider_call(_TOOL, "save_other", act=True):
                raw = await opened.client.save_other_contact(request.id)
        return _contact(raw)

    return await run_once(
        user_id,
        request.idempotency_key,
        save,
        tool=_TOOL.value,
        record=lambda made: {"contact_id": made.id},
    )


async def update_contact(user_id: UUID, request: ContactChange) -> Contact:
    """Change a contact: a list sent replaces that list, one left out is kept."""
    refuse_other_contact(request.id)
    async with open_tool_client(_TOOL, user_id) as opened:
        client: ContactsClientProtocol = opened.client
        async with provider_call(_TOOL, "update", act=True):
            raw = await client.update_contact(
                request.id,
                name=request.name,
                organization=request.organization,
                notes=request.notes,
                emails=None if request.emails is None else _values(request.emails),
                phones=None if request.phones is None else _values(request.phones),
                addresses=None if request.addresses is None else _addresses(request.addresses),
                details=_details(request),
            )
    return _contact(raw)


async def delete_contact(user_id: UUID, contact_id: str) -> None:
    """Delete one contact."""
    refuse_other_contact(contact_id)
    async with open_tool_client(_TOOL, user_id) as opened:
        client: ContactsClientProtocol = opened.client
        async with provider_call(_TOOL, "delete", act=True):
            await client.delete_contact(contact_id)


async def _group_page(client: Any, group: str, page_token: str | None) -> ContactsPage:
    """A page of a group.

    A provider lists a group's people in no order, so the group — read whole, at most
    ``GOOGLE_CONTACT_GROUP_MAX_MEMBERS`` — is sorted by family then given name before it
    is paged (owner request 2026-10-31).
    """
    size = listing_page_size()
    start = int(page_token) if page_token and page_token.isdigit() else 0
    async with provider_call(_TOOL, "list", act=False):
        found = await client.group_people(
            group, GOOGLE_CONTACT_GROUP_MAX_MEMBERS, fields=_MEMBER_FIELDS
        )
    everyone = sorted(found["people"], key=contact_order_key)
    more = start + size < len(everyone)
    return ContactsPage(
        items=[_summary(person) for person in everyone[start : start + size]],
        next_page_token=str(start + size) if more else None,
        # The group read only so many members: the rest is said, never implied away.
        truncated=bool(found["cut"]),
    )


def _search_size() -> int:
    """A search's page: a listing's, under Google's cap on both its searches.

    Google answers at most so many whatever it is asked, so a page set larger
    would read a full answer as the whole. One page for every provider.
    """
    return min(
        listing_page_size(), GOOGLE_CONTACTS_SEARCH_PAGE_MAX, GOOGLE_OTHER_CONTACTS_SEARCH_MAX
    )


def _found(results: Sequence[Mapping[str, Any]], size: int) -> ContactsPage:
    """A page answered in one go: its contacts by family then given name, and whether it
    may hold more."""
    people = sorted((item.get("person") or item for item in results), key=contact_order_key)
    return ContactsPage(
        items=[_summary(person) for person in people],
        next_page_token=None,
        truncated=len(people) >= size,
    )


def refuse_other_contact(contact_id: str) -> None:
    """Refuse, unsent, an act on a contact Google only lists and searches."""
    if contact_id.startswith(_OTHER_CONTACT_PREFIX):
        refuse(NOT_SUPPORTED_BY_PROVIDER)


def _require(provider: ConnectorType, feature: WorkbenchFeature) -> None:
    """Refuse, unsent, a gesture the active provider does not accept."""
    if feature not in PROVIDER_FEATURES[provider]:
        refuse(NOT_SUPPORTED_BY_PROVIDER)


def _first(entries: object, field: str) -> str | None:
    if isinstance(entries, list) and entries and isinstance(entries[0], Mapping):
        value = entries[0].get(field)
        return str(value) if value else None
    return None


def _summary(person: Mapping[str, Any]) -> ContactSummary:
    return ContactSummary(
        id=str(person.get("resourceName") or ""),
        name=_first(person.get("names"), "displayName") or "",
        given_name=_first(person.get("names"), "givenName"),
        family_name=_first(person.get("names"), "familyName"),
        email=_first(person.get("emailAddresses"), "value"),
        phone=_first(person.get("phoneNumbers"), "value"),
        organization=_first(person.get("organizations"), "name"),
    )


def _contact(person: Mapping[str, Any]) -> Contact:
    return Contact(
        **_summary(person).model_dump(),
        emails=[ContactValue(**value) for value in values_read(person.get("emailAddresses"))],
        phones=[ContactValue(**value) for value in values_read(person.get("phoneNumbers"))],
        addresses=[ContactAddress(**item) for item in addresses_read(person.get("addresses"))],
        notes=_first(person.get("biographies"), "value"),
        job_title=_first(person.get("organizations"), "title"),
        website=_first(person.get("urls"), "value"),
        birthday=birthday_text(person.get("birthdays")),
    )


def _details(request: NewContact | ContactChange) -> ContactDetails:
    """What a write carries beyond a name, a company and notes."""
    return ContactDetails(
        given_name=request.given_name,
        family_name=request.family_name,
        job_title=request.job_title,
        website=request.website,
        birthday=request.birthday,
        clear_birthday=isinstance(request, ContactChange) and request.clear_birthday,
    )


def _values(values: Sequence[ContactValueInput]) -> list[TypedValue]:
    return [{"value": item.value, "type": item.type} for item in values]


def _addresses(addresses: Sequence[ContactAddressInput]) -> list[TypedAddress]:
    return [{"formatted": item.formatted, "type": item.type} for item in addresses]
