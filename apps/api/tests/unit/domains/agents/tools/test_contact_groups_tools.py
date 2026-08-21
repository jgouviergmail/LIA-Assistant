"""Contact groups & other-contacts tools (lot C, 2026-08).

Business behaviors pinned here:
- system groups (myContacts, chatBuddies, ...) are Google plumbing, never
  shown to the user; member counts come from the API aggregate (a count shown
  to the user is a claim: exact or absent — CLAUDE.md);
- group targeting resolves a spoken name ("famille") case-insensitively and
  returns the members' emails so the email tools can address them;
- these are Google-only capabilities: any other resolved contacts provider
  gets a localized graceful refusal, never an AttributeError.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.tools.contact_groups_tools import (
    GetContactGroupMembersTool,
    ListContactGroupsTool,
    SearchOtherContactsTool,
)
from src.domains.connectors.clients.google_people_client import GooglePeopleClient

pytestmark = pytest.mark.unit

_GROUPS_RESPONSE: dict[str, Any] = {
    "contactGroups": [
        {
            "resourceName": "contactGroups/myContacts",
            "groupType": "SYSTEM_CONTACT_GROUP",
            "name": "myContacts",
            "formattedName": "myContacts",
            "memberCount": 120,
        },
        {
            "resourceName": "contactGroups/fam123",
            "groupType": "USER_CONTACT_GROUP",
            "name": "Famille",
            "formattedName": "Famille",
            "memberCount": 6,
        },
        {
            "resourceName": "contactGroups/work456",
            "groupType": "USER_CONTACT_GROUP",
            "name": "Collègues",
            "formattedName": "Collègues",
            "memberCount": 14,
        },
    ]
}


def _google_client(**method_returns: Any) -> MagicMock:
    client = MagicMock(spec=GooglePeopleClient)
    for name, value in method_returns.items():
        setattr(client, name, AsyncMock(return_value=value))
    return client


def _tool_with_runtime(tool: Any) -> Any:
    tool.runtime = MagicMock()
    return tool


def _patch_language() -> Any:
    return patch(
        "src.domains.agents.tools.runtime_helpers.get_user_language_safe",
        new=AsyncMock(return_value="fr"),
    )


class TestListContactGroups:
    async def test_returns_user_groups_only_with_exact_counts(self) -> None:
        tool = _tool_with_runtime(ListContactGroupsTool())
        client = _google_client(list_contact_groups=_GROUPS_RESPONSE)

        with _patch_language():
            result = await tool.execute_api_call(client, uuid4())

        names = [g["name"] for g in result["groups"]]
        assert names == ["Collègues", "Famille"]  # sorted, no system groups
        famille = next(g for g in result["groups"] if g["name"] == "Famille")
        assert famille["member_count"] == 6
        assert famille["resource_name"] == "contactGroups/fam123"
        assert result["total"] == 2

    async def test_non_google_provider_gets_localized_refusal(self) -> None:
        tool = _tool_with_runtime(ListContactGroupsTool())
        client = MagicMock()  # not a GooglePeopleClient

        with _patch_language():
            result = await tool.execute_api_call(client, uuid4())

        assert result["success"] is False
        assert result["error"] == "provider_not_supported"
        assert result["message"]


class TestGetContactGroupMembers:
    async def test_resolves_group_name_case_insensitively_and_returns_emails(self) -> None:
        tool = _tool_with_runtime(GetContactGroupMembersTool())
        client = _google_client(
            list_contact_groups=_GROUPS_RESPONSE,
            get_contact_group={
                "resourceName": "contactGroups/fam123",
                "memberResourceNames": ["people/1", "people/2"],
            },
            get_people_batch={
                "responses": [
                    {
                        "person": {
                            "resourceName": "people/1",
                            "names": [{"displayName": "Marc Dupont"}],
                            "emailAddresses": [{"value": "marc@example.com"}],
                        }
                    },
                    {
                        "person": {
                            "resourceName": "people/2",
                            "names": [{"displayName": "Léa Dupont"}],
                            "emailAddresses": [
                                {"value": "lea@example.com"},
                                {"value": "lea.pro@example.com"},
                            ],
                        }
                    },
                ]
            },
        )

        with _patch_language():
            result = await tool.execute_api_call(client, uuid4(), group_name="famille")

        assert result["group"]["name"] == "Famille"
        members = result["members"]
        assert members[0] == {
            "resource_name": "people/1",
            "name": "Marc Dupont",
            "emails": ["marc@example.com"],
        }
        assert members[1]["emails"] == ["lea@example.com", "lea.pro@example.com"]
        assert result["total"] == 2

    async def test_unknown_group_lists_available_names(self) -> None:
        tool = _tool_with_runtime(GetContactGroupMembersTool())
        client = _google_client(list_contact_groups=_GROUPS_RESPONSE)

        with _patch_language():
            result = await tool.execute_api_call(client, uuid4(), group_name="copains")

        assert result["success"] is False
        assert result["error"] == "group_not_found"
        assert result["available_groups"] == ["Collègues", "Famille"]


class TestRegistryFormatting:
    def test_groups_success_formats_as_structured_data(self) -> None:
        tool = ListContactGroupsTool()
        output = tool.format_registry_response(
            {"success": True, "groups": [{"name": "Famille", "member_count": 6}], "total": 1}
        )
        assert output.success is True
        assert output.structured_data["groups"][0]["name"] == "Famille"

    def test_groups_failure_formats_as_failure(self) -> None:
        tool = ListContactGroupsTool()
        output = tool.format_registry_response(
            {"success": False, "error": "provider_not_supported", "message": "non"}
        )
        assert output.success is False
        assert output.error_message


class TestSearchOtherContacts:
    async def test_results_are_normalized_and_flagged(self) -> None:
        tool = _tool_with_runtime(SearchOtherContactsTool())
        client = _google_client(
            search_other_contacts={
                "results": [
                    {
                        "person": {
                            "resourceName": "otherContacts/x1",
                            "names": [{"displayName": "Paul Martin"}],
                            "emailAddresses": [{"value": "paul@example.com"}],
                        }
                    }
                ]
            }
        )

        with _patch_language():
            result = await tool.execute_api_call(client, uuid4(), query="paul")

        contact = result["contacts"][0]
        assert contact["name"] == "Paul Martin"
        assert contact["emails"] == ["paul@example.com"]
        assert contact["source"] == "other_contacts"
        assert result["total"] == 1
