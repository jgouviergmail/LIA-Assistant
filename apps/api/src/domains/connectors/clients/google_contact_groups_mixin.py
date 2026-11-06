"""Writing and reading Google's contact groups (ADR-369, lot 9).

Out of ``google_people_client.py``, which holds the contacts themselves. ``memberCount`` is the
group's own aggregate: it says when a read was cut. Deleting a group keeps its contacts.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from src.domains.connectors.clients.people_names import GROUP_NAME, named_path


class GoogleContactGroupsMixin:
    """Groups on the People API."""

    _make_request: Any
    get_contact_group: Any
    get_people_batch: Any
    get_person: Any
    list_contact_groups: Any
    _forget_people: Any

    async def group_people(
        self, group: str, max_members: int, fields: list[str] | None = None
    ) -> dict[str, Any]:
        """A group's people up to a bound, and whether the bound cut them."""
        raw = await self.get_contact_group(group, max_members)
        members: list[str] = list(raw.get("memberResourceNames") or [])
        batch = await self.get_people_batch(members, fields=fields) if members else {}
        people = [item["person"] for item in batch.get("responses") or [] if item.get("person")]
        return {"people": people, "cut": int(raw.get("memberCount") or 0) > len(members)}

    async def groups_of_contact(self, resource_name: str) -> list[dict[str, Any]]:
        """The groups a contact is in."""
        person = await self.get_person(resource_name, fields=["memberships"], use_cache=False)
        held = {
            (item.get("contactGroupMembership") or {}).get("contactGroupResourceName")
            for item in person.get("memberships") or []
        }
        listed = await self.list_contact_groups()
        return [
            group for group in listed.get("contactGroups") or [] if group["resourceName"] in held
        ]

    async def create_contact_group(self, name: str) -> dict[str, Any]:
        """A new group."""
        made: dict[str, Any] = await self._make_request(
            "POST", "/contactGroups", json_data={"contactGroup": {"name": name}}
        )
        return made

    async def rename_contact_group(self, group: str, name: str) -> None:
        """Rename a group."""
        await self._make_request(
            "PUT",
            named_path(group, GROUP_NAME),
            json_data={"contactGroup": {"name": name}},
        )
        await self._forget_people()

    async def delete_contact_group(self, group: str) -> None:
        """Delete a group: its contacts stay."""
        await self._make_request(
            "DELETE", named_path(group, GROUP_NAME), params={"deleteContacts": "false"}
        )
        await self._forget_people()

    async def change_group_members(
        self, group: str, *, add: Sequence[str], remove: Sequence[str]
    ) -> None:
        """Add and take off members, in one request."""
        await self._make_request(
            "POST",
            f"{named_path(group, GROUP_NAME)}/members:modify",
            json_data={"resourceNamesToAdd": list(add), "resourceNamesToRemove": list(remove)},
        )
        await self._forget_people()


__all__ = ["GoogleContactGroupsMixin"]
