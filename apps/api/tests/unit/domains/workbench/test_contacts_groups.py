"""Contact groups by the person's own hand (ADR-369, lot 9).

A group is made by adding someone to a name, on every provider: an empty group would exist on one
and vanish on another. The name is matched as a person would (folded), so « famille » joins
« Famille » rather than making a second one. Google's own groups can be read, never changed.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.exceptions import BaseAPIException
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.models import ConnectorType
from src.domains.workbench import contacts_groups
from src.domains.workbench.errors import NOT_SUPPORTED_BY_PROVIDER, refusal_code_of
from src.domains.workbench.schemas.contacts import GroupJoin, GroupLeave, GroupRename

pytestmark = pytest.mark.unit

USER = uuid4()
GOOGLE = ConnectorType.GOOGLE_CONTACTS

FAMILY = {
    "resourceName": "contactGroups/f",
    "formattedName": "Famille",
    "groupType": "USER_CONTACT_GROUP",
    "memberCount": 2,
}
STARRED = {
    "resourceName": "contactGroups/starred",
    "formattedName": "Starred",
    "groupType": "SYSTEM_CONTACT_GROUP",
    "memberCount": 1,
}


def _door(client: Any) -> Any:
    @contextlib.asynccontextmanager
    async def opened(tool: Any, user_id: Any) -> AsyncIterator[ActiveClient]:
        yield ActiveClient(client=client, connector_type=GOOGLE, preferred_name=None)

    return patch.object(contacts_groups, "open_tool_client", opened)


def _client(**methods: Any) -> MagicMock:
    client = MagicMock(
        list_contact_groups=AsyncMock(return_value={"contactGroups": [FAMILY, STARRED]}),
        change_group_members=AsyncMock(),
        create_contact_group=AsyncMock(),
    )
    for name, value in methods.items():
        setattr(client, name, AsyncMock(return_value=value))
    return client


class TestTheGroupsOfAContact:
    async def test_they_are_named_and_only_the_person_s_own_are_said(self) -> None:
        client = _client(groups_of_contact=[FAMILY, STARRED])

        with _door(client):
            answer = await contacts_groups.groups_of(USER, "people/c1")

        assert [(group.id, group.name, group.own) for group in answer.groups] == [
            ("contactGroups/f", "Famille", True),
        ]

    async def test_a_contact_met_in_mail_is_in_none_it_can_read(self) -> None:
        client = _client(groups_of_contact=[])

        with _door(client), pytest.raises(BaseAPIException):
            await contacts_groups.groups_of(USER, "otherContacts/c9")

        client.groups_of_contact.assert_not_awaited()


class TestJoining:
    async def test_a_name_held_is_joined_however_it_is_written(self) -> None:
        client = _client()

        with _door(client):
            joined = await contacts_groups.join_group(
                USER, GroupJoin(contact_id="people/c1", name=" famille ")
            )

        assert joined.id == "contactGroups/f"
        client.create_contact_group.assert_not_awaited()
        client.change_group_members.assert_awaited_once_with(
            "contactGroups/f", add=["people/c1"], remove=[]
        )

    async def test_a_new_name_makes_the_group_with_them_in_it(self) -> None:
        client = _client(create_contact_group={"resourceName": "contactGroups/n"})

        with _door(client):
            joined = await contacts_groups.join_group(
                USER, GroupJoin(contact_id="people/c1", name="Work")
            )

        assert joined.id == "contactGroups/n"
        assert joined.name == "Work"
        client.create_contact_group.assert_awaited_once_with("Work")

    async def test_google_s_own_groups_are_no_name_to_join(self) -> None:
        client = _client(create_contact_group={"resourceName": "contactGroups/n"})

        with _door(client):
            await contacts_groups.join_group(
                USER, GroupJoin(contact_id="people/c1", name="Starred")
            )

        client.create_contact_group.assert_awaited_once_with("Starred")

    def test_an_empty_name_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            GroupJoin(contact_id="people/c1", name="   ")


class TestLeaving:
    async def test_a_contact_leaves(self) -> None:
        client = _client()

        with _door(client):
            await contacts_groups.leave_group(
                USER, GroupLeave(contact_id="people/c1", group_id="contactGroups/f")
            )

        client.change_group_members.assert_awaited_once_with(
            "contactGroups/f", add=[], remove=["people/c1"]
        )


class TestAGroupItself:
    async def test_it_is_renamed(self) -> None:
        client = _client(rename_contact_group=None)

        with _door(client):
            await contacts_groups.rename_group(USER, GroupRename(id="contactGroups/f", name="Kin"))

        client.rename_contact_group.assert_awaited_once_with("contactGroups/f", "Kin")

    async def test_it_goes_and_its_contacts_stay(self) -> None:
        client = _client(delete_contact_group=None)

        with _door(client):
            await contacts_groups.delete_group(USER, "contactGroups/f")

        client.delete_contact_group.assert_awaited_once_with("contactGroups/f")

    async def test_a_group_past_a_list_s_bound_still_goes(self) -> None:
        client = _client(rename_contact_group=None, list_contact_groups={"contactGroups": []})

        with _door(client):
            await contacts_groups.rename_group(USER, GroupRename(id="category:Rm", name="Kin"))

        client.rename_contact_group.assert_awaited_once()

    @pytest.mark.parametrize("act", ["rename", "delete"])
    async def test_google_s_own_are_refused_unsent(self, act: str) -> None:
        client = _client(rename_contact_group=None, delete_contact_group=None)

        with _door(client), pytest.raises(BaseAPIException) as refused:
            if act == "rename":
                await contacts_groups.rename_group(
                    USER, GroupRename(id="contactGroups/starred", name="Kin")
                )
            else:
                await contacts_groups.delete_group(USER, "contactGroups/starred")

        assert refusal_code_of(refused.value) == NOT_SUPPORTED_BY_PROVIDER
        client.rename_contact_group.assert_not_awaited()
        client.delete_contact_group.assert_not_awaited()
