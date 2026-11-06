"""Contact groups on iCloud: a card of their own (ADR-369, lot 9).

The book is read whole anyway (``_get_all_contacts_cached``), so a group is found in it and its
members with it. Opening a contact reads the kept book, or each opening would read every card;
a write reads a fresh one, and clears what is kept. A group's card is no contact: the client's
listings leave it out. A member is named by the UID of their card, and a contact whose card
cannot be found is refused before anything is written. Deleting a group deletes its card and no
other.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from src.domains.connectors.clients.contact_groups import group_entry
from src.domains.connectors.clients.normalizers.contact_group_cards import (
    card_with_members,
    group_card,
    renamed_group_card,
)


def _name_of(card: Mapping[str, Any]) -> str:
    names = card.get("names") or [{}]
    return str(names[0].get("displayName") or "")


class AppleContactGroupsMixin:
    """Groups on CardDAV."""

    _execute_with_retry: Any
    _get_all_contacts_cached: Any
    _get_http_client: Any
    _discover_addressbook: Any
    _invalidate_contacts_cache: Any
    _card_text: Any
    _put_card: Any
    _delete_card: Any
    _check_http_status: Any

    async def _groups_and_people(
        self, *, kept: bool = True
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        book, _, _ = await self._get_all_contacts_cached(kept)
        return (
            [card for card in book if card.get("isGroup")],
            [card for card in book if not card.get("isGroup")],
        )

    async def _group_named(self, group: str) -> dict[str, Any]:
        groups, _ = await self._groups_and_people(kept=False)
        found = next((card for card in groups if card.get("resourceName") == group), None)
        if found is None:
            raise ValueError("no such group")
        return found

    async def list_contact_groups(self) -> dict[str, Any]:
        """The group cards, each with how many it names."""
        groups, _ = await self._execute_with_retry("list_groups", self._groups_and_people)
        return {
            "contactGroups": [
                group_entry(
                    card["resourceName"], _name_of(card), len(card.get("groupMembers") or [])
                )
                for card in groups
            ]
        }

    async def group_people(
        self, group: str, max_members: int, fields: list[str] | None = None
    ) -> dict[str, Any]:
        """A group's people up to a bound, and whether the bound cut them."""
        groups, people = await self._execute_with_retry("group_people", self._groups_and_people)
        card = next((item for item in groups if item.get("resourceName") == group), None)
        named = set(card.get("groupMembers") or []) if card else set()
        members = [person for person in people if person.get("uid") in named]
        return {"people": members[:max_members], "cut": len(members) > max_members}

    async def groups_of_contact(self, resource_name: str) -> list[dict[str, Any]]:
        """The groups naming a contact."""
        groups, people = await self._execute_with_retry("groups_of", self._groups_and_people)
        uids = _uids_of(people, [resource_name])
        return [
            group_entry(card["resourceName"], _name_of(card), len(card.get("groupMembers") or []))
            for card in groups
            if set(uids) & set(card.get("groupMembers") or [])
        ]

    async def create_contact_group(self, name: str) -> dict[str, Any]:
        """A new group's card, at a uid drawn before any retry (S1)."""
        uid = str(uuid.uuid4())
        return await self._execute_with_retry("create_group", self._create_group_impl, name, uid)

    async def _create_group_impl(self, name: str, uid: str) -> dict[str, Any]:
        addressbook = await self._discover_addressbook()
        url = f"{addressbook.rstrip('/')}/{uid}.vcf"
        client = await self._get_http_client()
        resp = await client.put(
            url,
            content=group_card(name, uid),
            headers={"Content-Type": "text/vcard; charset=utf-8"},
        )
        self._check_http_status(resp.status_code)
        await self._invalidate_contacts_cache()
        return group_entry(url, name, 0)

    async def rename_contact_group(self, group: str, name: str) -> None:
        """Rename a group, its members kept."""
        await self._execute_with_retry("rename_group", self._rename_group_impl, group, name)

    async def _rename_group_impl(self, group: str, name: str) -> None:
        await self._group_named(group)
        await self._put_card(group, renamed_group_card(await self._card_text(group), name))

    async def delete_contact_group(self, group: str) -> None:
        """Delete a group's card: its contacts stay, and a contact is never taken for one."""
        await self._execute_with_retry("delete_group", self._delete_group_impl, group)

    async def _delete_group_impl(self, group: str) -> None:
        await self._group_named(group)
        await self._delete_card(group)

    async def change_group_members(
        self, group: str, *, add: Sequence[str], remove: Sequence[str]
    ) -> None:
        """Add and take off members, by the UID of their cards."""
        await self._execute_with_retry(
            "change_group_members", self._change_members_impl, group, add, remove
        )

    async def _change_members_impl(
        self, group: str, add: Sequence[str], remove: Sequence[str]
    ) -> None:
        _, people = await self._groups_and_people(kept=False)
        added, removed = _uids_of(people, add), _uids_of(people, remove)
        written = card_with_members(await self._card_text(group), add=added, remove=removed)
        await self._put_card(group, written)


def _uids_of(people: Iterable[Mapping[str, Any]], resource_names: Sequence[str]) -> list[str]:
    """The UIDs of contacts' cards; one nobody knows is refused, nothing written."""
    by_name = {person.get("resourceName"): person.get("uid") for person in people}
    uids = [by_name.get(name) for name in resource_names]
    if not all(uids):
        raise ValueError("no such contact")
    return [str(uid) for uid in uids]


__all__ = ["AppleContactGroupsMixin"]
