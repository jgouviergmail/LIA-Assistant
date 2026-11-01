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
Groups and « other contacts » are Google's (the descriptor).
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
)

_TOOL = WorkbenchTool.CONTACTS
#: What a group's member page reads of each person.
_MEMBER_FIELDS: Final = ["names", "emailAddresses", "phoneNumbers", "organizations"]
_USER_GROUP: Final = "USER_CONTACT_GROUP"


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
    """The account's contact groups, the person's own first (Google)."""
    async with open_tool_client(_TOOL, user_id) as opened:
        _require(opened.connector_type, WorkbenchFeature.CONTACT_GROUPS)
        async with provider_call(_TOOL, "list_groups", act=False):
            raw = await opened.client.list_contact_groups()
    groups = sorted(
        raw.get("contactGroups") or [],
        key=lambda group: group.get("groupType") != _USER_GROUP,
    )
    return ContactGroups(
        groups=[
            ContactGroup(
                id=str(group.get("resourceName") or ""),
                name=str(group.get("formattedName") or group.get("name") or ""),
                count=group.get("memberCount"),
            )
            for group in groups
        ]
    )


async def read_contact(user_id: UUID, contact_id: str) -> Contact:
    """One contact, whole and typed."""
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
                )
        return _contact(raw)

    return await run_once(
        user_id,
        request.idempotency_key,
        create,
        tool=_TOOL.value,
        record=lambda made: {"contact_id": made.id},
    )


async def update_contact(user_id: UUID, request: ContactChange) -> Contact:
    """Change a contact: a list sent replaces that list, one left out is kept."""
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
            )
    return _contact(raw)


async def delete_contact(user_id: UUID, contact_id: str) -> None:
    """Delete one contact."""
    async with open_tool_client(_TOOL, user_id) as opened:
        client: ContactsClientProtocol = opened.client
        async with provider_call(_TOOL, "delete", act=True):
            await client.delete_contact(contact_id)


async def _group_page(client: Any, group: str, page_token: str | None) -> ContactsPage:
    """A page of a group, through its members (the group lists names, not people).

    Google lists the members in no order, so the group — read whole, at most
    ``GOOGLE_CONTACT_GROUP_MAX_MEMBERS``, one batch — is sorted by family then given
    name before it is paged (owner request 2026-10-31).
    """
    size = listing_page_size()
    start = int(page_token) if page_token and page_token.isdigit() else 0
    async with provider_call(_TOOL, "list", act=False):
        raw = await client.get_contact_group(group, max_members=GOOGLE_CONTACT_GROUP_MAX_MEMBERS)
        members: list[str] = list(raw.get("memberResourceNames") or [])
        batch = await client.get_people_batch(members, fields=_MEMBER_FIELDS) if members else {}
    people = sorted(
        (person for item in batch.get("responses") or [] if (person := item.get("person"))),
        key=contact_order_key,
    )[start : start + size]
    more = start + size < len(members)
    return ContactsPage(
        items=[_summary(person) for person in people],
        next_page_token=str(start + size) if more else None,
        # The group read only so many members: the rest is said, never implied away.
        truncated=int(raw.get("memberCount") or 0) > len(members),
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
    )


def _values(values: Sequence[ContactValueInput]) -> list[TypedValue]:
    return [{"value": item.value, "type": item.type} for item in values]


def _addresses(addresses: Sequence[ContactAddressInput]) -> list[TypedAddress]:
    return [{"formatted": item.formatted, "type": item.type} for item in addresses]
