"""Contact groups on Graph: a category a contact carries (ADR-369, lot 9).

Graph has no group a contact can sit in several of. A contact folder is not one: a contact has one
folder, and deleting a folder deletes its contacts. A category is: measured, ``PATCH categories``
takes a free word, and ``categories/any(...)`` filters answer. So a group exists while someone is
in it, its id is its name, and deleting it takes the word off its members and nobody is deleted.

The list of groups is what the contacts carry, read a page at a time up to a bound: past it, no
count is claimed (ADR-185). A rename or a removal rewrites each member, one at a time.
"""

from __future__ import annotations

import base64
from collections import Counter
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any, Final

from src.core.exceptions import ConnectorAPIError
from src.domains.connectors.clients.base_google_client import apply_max_items_limit
from src.domains.connectors.clients.contact_directory import invalidate_contacts_cache
from src.domains.connectors.clients.contact_groups import group_entry
from src.domains.connectors.clients.normalizers.graph_paging import (
    graph_page_params,
    graph_page_token,
)
from src.domains.connectors.clients.normalizers.microsoft_contacts_normalizer import (
    normalize_graph_contact,
)
from src.domains.connectors.clients.path_segments import path_segment
from src.domains.connectors.models import ConnectorType

_ID_PREFIX: Final = "category:"
_ANY_CATEGORY: Final = "categories/any()"
#: Pages a list of groups reads: past them, it claims no count.
_SCAN_PAGES_MAX: Final = 40
_PAGE_SIZE: Final = 25


def contact_path(contact_id: str) -> str:
    """A contact's path, its id quoted: an id from a browser or a model never shapes a path."""
    segment = path_segment(contact_id, connector_type=ConnectorType.MICROSOFT_CONTACTS)
    return f"/me/contacts/{segment}"


def category_group_id(name: str) -> str:
    """The id of the group a category is: its name, safe to travel."""
    encoded = base64.urlsafe_b64encode(name.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{_ID_PREFIX}{encoded}"


def _no_such_group() -> ConnectorAPIError:
    return ConnectorAPIError(
        connector_type=ConnectorType.MICROSOFT_CONTACTS.value,
        status_code=404,
        detail="microsoft_contacts API error: no such group",
    )


def _category_of(group: str) -> str:
    """The category a group id names; an id this client did not mint names nothing."""
    encoded = group.removeprefix(_ID_PREFIX)
    if encoded == group or not encoded:
        raise _no_such_group()
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        return base64.b64decode(padded, altchars=b"-_", validate=True).decode("utf-8")
    except ValueError as error:
        raise _no_such_group() from error


def _in_category(category: str) -> str:
    quoted = category.replace("'", "''")
    return f"categories/any(a:a eq '{quoted}')"


def _contact_id(resource_name: str) -> str:
    return resource_name.removeprefix("people/")


class MicrosoftContactGroupsMixin:
    """Groups on Graph."""

    _make_request: Any
    user_id: Any
    #: What a contact is read with, from the client.
    _people_select: str

    async def _pages(
        self, filter_expression: str, select: str, *, pages_max: int | None = None
    ) -> AsyncIterator[tuple[list[Mapping[str, Any]], str | None]]:
        """The contacts a filter finds, page after page, and the token after each."""
        token: str | None = None
        read = 0
        while True:
            params = {
                "$filter": filter_expression,
                "$select": select,
                "$top": apply_max_items_limit(_PAGE_SIZE),
                **graph_page_params(token),
            }
            page = await self._make_request("GET", "/me/contacts", params=params)
            token = graph_page_token(page.get("@odata.nextLink"))
            read += 1
            yield list(page.get("value") or []), token
            if token is None or (pages_max is not None and read >= pages_max):
                return

    async def list_contact_groups(self) -> dict[str, Any]:
        """The categories the contacts carry, each with who carries it."""
        counts: Counter[str] = Counter()
        token: str | None = None
        async for found in self._pages(_ANY_CATEGORY, "categories", pages_max=_SCAN_PAGES_MAX):
            page, token = found
            for contact in page:
                counts.update(contact.get("categories") or [])
        whole = token is None
        return {
            "contactGroups": [
                group_entry(category_group_id(name), name, count if whole else None)
                for name, count in sorted(counts.items())
            ]
        }

    async def group_people(
        self, group: str, max_members: int, fields: list[str] | None = None
    ) -> dict[str, Any]:
        """A group's people up to a bound, and whether the bound cut them."""
        people: list[dict[str, Any]] = []
        more: str | None = None
        async for found in self._pages(_in_category(_category_of(group)), self._people_select):
            page, more = found
            people.extend(normalize_graph_contact(contact) for contact in page)
            if len(people) >= max_members:
                break
        cut = more is not None or len(people) > max_members
        return {"people": people[:max_members], "cut": cut}

    async def groups_of_contact(self, resource_name: str) -> list[dict[str, Any]]:
        """The groups a contact is in: a group's id is its name, so nothing more is read."""
        held = await self._categories(resource_name)
        return [group_entry(category_group_id(name), name, None) for name in held]

    async def create_contact_group(self, name: str) -> dict[str, Any]:
        """A group: it exists once someone is in it, so nothing is asked of Graph yet."""
        return group_entry(category_group_id(name), name, 0)

    async def rename_contact_group(self, group: str, name: str) -> None:
        """Rename a group, on each member in turn."""
        category = _category_of(group)

        def renamed(held: Sequence[str]) -> list[str]:
            return list(dict.fromkeys(name if item == category else item for item in held))

        await self._rewrite_members(category, renamed)

    async def delete_contact_group(self, group: str) -> None:
        """Delete a group: the word leaves each member, and nobody is deleted."""
        category = _category_of(group)

        def without(held: Sequence[str]) -> list[str]:
            return [item for item in held if item != category]

        await self._rewrite_members(category, without)

    async def change_group_members(
        self, group: str, *, add: Sequence[str], remove: Sequence[str]
    ) -> None:
        """Add and take off members: a contact's other categories stay."""
        category = _category_of(group)
        for resource_name in add:
            held = await self._categories(resource_name)
            if category not in held:
                await self._write_categories(_contact_id(resource_name), [*held, category])
        for resource_name in remove:
            held = await self._categories(resource_name)
            if category in held:
                kept = [item for item in held if item != category]
                await self._write_categories(_contact_id(resource_name), kept)
        await invalidate_contacts_cache(self.user_id)

    async def _categories(self, resource_name: str) -> list[str]:
        contact = await self._make_request(
            "GET", contact_path(_contact_id(resource_name)), params={"$select": "categories"}
        )
        return list(contact.get("categories") or [])

    async def _write_categories(self, contact_id: str, categories: list[str]) -> None:
        await self._make_request(
            "PATCH", contact_path(contact_id), json_data={"categories": categories}
        )

    async def _rewrite_members(self, category: str, change: Any) -> None:
        """Every member, whatever their number: a group half renamed is two groups."""
        members = [
            contact
            async for page, _ in self._pages(_in_category(category), "categories")
            for contact in page
        ]
        for contact in members:
            await self._write_categories(contact["id"], change(contact.get("categories") or []))
        await invalidate_contacts_cache(self.user_id)


__all__ = ["MicrosoftContactGroupsMixin", "category_group_id", "contact_path"]
