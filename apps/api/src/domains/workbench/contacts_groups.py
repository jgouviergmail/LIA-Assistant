"""Contact groups by the person's own hand (ADR-369, lot 9).

A group is made by adding someone to a name, on every provider: Graph holds no empty group, so an
empty one would exist on one provider and vanish on another. A name is matched as a person would
(``fold_name``), so « famille » joins « Famille » rather than making a second one. Google's own
groups (« starred ») are read, and neither joined by name nor changed.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from src.domains.connectors.clients.contact_groups import USER_CONTACT_GROUP
from src.domains.connectors.clients.protocols import ContactsClientProtocol
from src.domains.shared.text_normalization import fold_name
from src.domains.workbench.calls import provider_call
from src.domains.workbench.clients import open_tool_client
from src.domains.workbench.contacts_service import group_of, refuse_other_contact
from src.domains.workbench.errors import NOT_SUPPORTED_BY_PROVIDER, refuse
from src.domains.workbench.features import WorkbenchTool
from src.domains.workbench.schemas.contacts import (
    ContactGroup,
    ContactGroups,
    GroupJoin,
    GroupLeave,
    GroupRename,
)

_TOOL = WorkbenchTool.CONTACTS


def _own(listed: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [
        group
        for group in listed.get("contactGroups") or []
        if group.get("groupType") == USER_CONTACT_GROUP
    ]


async def _refuse_a_provider_s_own(client: ContactsClientProtocol, group: str) -> None:
    """Refuse a group the provider keeps for itself; one a list did not reach goes on."""
    listed = await client.list_contact_groups()
    for entry in listed.get("contactGroups") or []:
        if entry.get("resourceName") == group and entry.get("groupType") != USER_CONTACT_GROUP:
            refuse(NOT_SUPPORTED_BY_PROVIDER)


async def groups_of(user_id: UUID, contact_id: str) -> ContactGroups:
    """The person's own groups a contact is in."""
    refuse_other_contact(contact_id)
    async with open_tool_client(_TOOL, user_id) as opened:
        client: ContactsClientProtocol = opened.client
        async with provider_call(_TOOL, "groups_of", act=False):
            held = await client.groups_of_contact(contact_id)
    return ContactGroups(groups=[group_of(group) for group in _own({"contactGroups": held})])


async def join_group(user_id: UUID, request: GroupJoin) -> ContactGroup:
    """A contact in the group of that name: one nobody holds is made with them in it."""
    refuse_other_contact(request.contact_id)
    wanted = fold_name(request.name)
    async with open_tool_client(_TOOL, user_id) as opened:
        client: ContactsClientProtocol = opened.client
        async with provider_call(_TOOL, "join_group", act=True):
            listed = await client.list_contact_groups()
            held = next(
                (
                    group
                    for group in _own(listed)
                    if fold_name(str(group.get("formattedName") or "")) == wanted
                ),
                None,
            )
            group = held or await client.create_contact_group(request.name)
            group_id = str(group["resourceName"])
            await client.change_group_members(group_id, add=[request.contact_id], remove=[])
    return ContactGroup(
        id=group_id,
        name=str(group.get("formattedName") or request.name),
        count=None,
    )


async def leave_group(user_id: UUID, request: GroupLeave) -> None:
    """A contact out of a group."""
    refuse_other_contact(request.contact_id)
    async with open_tool_client(_TOOL, user_id) as opened:
        client: ContactsClientProtocol = opened.client
        async with provider_call(_TOOL, "leave_group", act=True):
            await client.change_group_members(request.group_id, add=[], remove=[request.contact_id])


async def rename_group(user_id: UUID, request: GroupRename) -> None:
    """Rename one of the person's groups."""
    async with open_tool_client(_TOOL, user_id) as opened:
        client: ContactsClientProtocol = opened.client
        async with provider_call(_TOOL, "rename_group", act=True):
            await _refuse_a_provider_s_own(client, request.id)
            await client.rename_contact_group(request.id, request.name)


async def delete_group(user_id: UUID, group_id: str) -> None:
    """Delete one of the person's groups: its contacts stay."""
    async with open_tool_client(_TOOL, user_id) as opened:
        client: ContactsClientProtocol = opened.client
        async with provider_call(_TOOL, "delete_group", act=True):
            await _refuse_a_provider_s_own(client, group_id)
            await client.delete_contact_group(group_id)


__all__ = ["delete_group", "groups_of", "join_group", "leave_group", "rename_group"]
