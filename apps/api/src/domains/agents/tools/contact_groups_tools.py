"""Contact groups & other-contacts tools (lot C, 2026-08).

Surfaces two People API data families the granted scopes always allowed but
LIA never called:

- **Contact groups** (family, colleagues, clients): listing and member
  expansion, enabling group targeting ("send an email to the family group").
- **Other contacts** (people interacted with but never saved): search, feeding
  entity resolution and relations with identities that plain contact search
  cannot see.

Provider parity: these are Google People API concepts. Microsoft (categories/
contact folders) and Apple have no equivalent wired here — any non-Google
resolved client gets a localized graceful refusal, never an AttributeError.
"""

from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.core.i18n import normalize_language
from src.core.i18n_api_messages import APIMessages
from src.domains.agents.constants import AGENT_CONTACT, CONTEXT_DOMAIN_CONTACTS
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.base import ConnectorTool
from src.domains.agents.tools.decorators import connector_tool
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.connectors.clients.google_people_client import GooglePeopleClient
from src.domains.connectors.models import ConnectorType

logger = structlog.get_logger(__name__)

_USER_GROUP_TYPE = "USER_CONTACT_GROUP"


def _user_groups(response: dict[str, Any]) -> list[dict[str, Any]]:
    """User-defined groups only — Google's system groups are plumbing."""
    return [
        group
        for group in response.get("contactGroups", [])
        if group.get("groupType") == _USER_GROUP_TYPE
    ]


def _group_display_name(group: dict[str, Any]) -> str:
    """Display name of a group (formattedName wins over the raw name)."""
    return str(group.get("formattedName") or group.get("name", ""))


def _find_group(user_groups: list[dict[str, Any]], wanted: str) -> dict[str, Any] | None:
    """Case-insensitive group lookup by display name."""
    wanted_cf = wanted.casefold()
    return next(
        (group for group in user_groups if _group_display_name(group).casefold() == wanted_cf),
        None,
    )


def _person_to_contact(person: dict[str, Any]) -> dict[str, Any]:
    """Normalize a People API person to the compact dict the LLM consumes."""
    names = person.get("names") or []
    display_name = names[0].get("displayName", "") if names else ""
    return {
        "resource_name": person.get("resourceName", ""),
        "name": display_name,
        "emails": [e["value"] for e in (person.get("emailAddresses") or []) if e.get("value")],
    }


async def _provider_refusal_if_not_google(client: Any, runtime: Any) -> dict[str, Any] | None:
    """Return a localized refusal dict when the resolved client is not Google.

    The contacts category resolves to ONE active provider; groups and other
    contacts only exist on the Google People API. Graceful degradation is the
    documented parity behavior (CLAUDE.md, connector abstraction).
    """
    if isinstance(client, GooglePeopleClient):
        return None
    from src.domains.agents.tools.runtime_helpers import get_user_language_safe

    language = normalize_language(await get_user_language_safe(runtime))
    return {
        "success": False,
        "error": "provider_not_supported",
        "message": APIMessages.google_contacts_feature_only(language),
    }


class ListContactGroupsTool(ToolOutputMixin, ConnectorTool[GooglePeopleClient]):
    """List the user's contact groups (user-defined only, exact counts)."""

    connector_type = ConnectorType.GOOGLE_CONTACTS
    client_class = GooglePeopleClient
    functional_category = "contacts"
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize list contact groups tool."""
        super().__init__(tool_name="list_contact_groups_tool", operation="list")

    async def execute_api_call(
        self,
        client: GooglePeopleClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """List user contact groups, hiding Google's system plumbing groups."""
        refusal = await _provider_refusal_if_not_google(client, self.runtime)
        if refusal:
            return refusal

        response = await client.list_contact_groups()
        groups = [
            {
                "resource_name": group.get("resourceName", ""),
                "name": _group_display_name(group),
                # memberCount is the API aggregate over the whole group — the
                # only exact count (never derive it from a fetched page).
                "member_count": group.get("memberCount", 0),
            }
            for group in _user_groups(response)
        ]
        groups.sort(key=lambda g: str(g["name"]))
        return {"success": True, "groups": groups, "total": len(groups)}

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """Groups are a short structured list — no registry items needed."""
        if not result.get("success"):
            return UnifiedToolOutput.failure(
                message=result.get("message", "Contact groups request failed"),
                error_code=result.get("error"),
            )
        return UnifiedToolOutput.data_success(
            message=f"{result['total']} contact groups",
            structured_data={"groups": result["groups"], "total": result["total"]},
        )


class GetContactGroupMembersTool(ToolOutputMixin, ConnectorTool[GooglePeopleClient]):
    """Expand a contact group (by spoken name) into its members with emails."""

    connector_type = ConnectorType.GOOGLE_CONTACTS
    client_class = GooglePeopleClient
    functional_category = "contacts"
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize contact group members tool."""
        super().__init__(tool_name="get_contact_group_members_tool", operation="details")

    async def execute_api_call(
        self,
        client: GooglePeopleClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Resolve the group by name (case-insensitive) and expand its members."""
        refusal = await _provider_refusal_if_not_google(client, self.runtime)
        if refusal:
            return refusal

        group_name: str = (kwargs.get("group_name") or "").strip()
        response = await client.list_contact_groups()
        user_groups = _user_groups(response)
        match = _find_group(user_groups, group_name)
        if match is None:
            available = sorted(_group_display_name(group) for group in user_groups)
            from src.domains.agents.tools.runtime_helpers import get_user_language_safe

            language = normalize_language(await get_user_language_safe(self.runtime))
            return {
                "success": False,
                "error": "group_not_found",
                "message": APIMessages.contact_group_not_found(group_name, available, language),
                "available_groups": available,
            }

        group_detail = await client.get_contact_group(match["resourceName"])
        member_ids = group_detail.get("memberResourceNames", [])
        batch = await client.get_people_batch(member_ids)
        raw_persons = [item["person"] for item in batch.get("responses", []) if item.get("person")]
        members = [_person_to_contact(person) for person in raw_persons]

        logger.info(
            "contact_group_members_expanded",
            user_id=str(user_id),
            group=match.get("resourceName"),
            member_count=len(members),
        )
        return {
            "success": True,
            "group": {
                "resource_name": match.get("resourceName", ""),
                "name": _group_display_name(match),
            },
            "members": members,
            "total": len(members),
            "_raw_persons": raw_persons,
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """Members are real contacts: register them so contact cards render."""
        if not result.get("success"):
            return UnifiedToolOutput.failure(
                message=result.get("message", "Contact group request failed"),
                error_code=result.get("error"),
                metadata={"available_groups": result.get("available_groups", [])},
            )
        output = self.build_contacts_output(
            contacts=result.get("_raw_persons", []),
            query=result.get("group", {}).get("name"),
            operation="list",
        )
        output.structured_data = {
            "group": result["group"],
            "members": result["members"],
            "total": result["total"],
        }
        return output


class SearchOtherContactsTool(ToolOutputMixin, ConnectorTool[GooglePeopleClient]):
    """Search "other contacts" — interacted-with people never saved as contacts."""

    connector_type = ConnectorType.GOOGLE_CONTACTS
    client_class = GooglePeopleClient
    functional_category = "contacts"
    registry_enabled = True

    def __init__(self) -> None:
        """Initialize other-contacts search tool."""
        super().__init__(tool_name="search_other_contacts_tool", operation="search")

    async def execute_api_call(
        self,
        client: GooglePeopleClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Search other contacts and normalize the results."""
        refusal = await _provider_refusal_if_not_google(client, self.runtime)
        if refusal:
            return refusal

        query: str = (kwargs.get("query") or "").strip()
        response = await client.search_other_contacts(query)
        raw_persons = [item["person"] for item in response.get("results", []) if item.get("person")]
        contacts = [
            {**_person_to_contact(person), "source": "other_contacts"} for person in raw_persons
        ]
        return {
            "success": True,
            "query": query,
            "contacts": contacts,
            "total": len(contacts),
            "from_cache": response.get("from_cache", False),
            "_raw_persons": raw_persons,
        }

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """Register found people so contact cards render."""
        if not result.get("success"):
            return UnifiedToolOutput.failure(
                message=result.get("message", "Other contacts search failed"),
                error_code=result.get("error"),
            )
        output = self.build_contacts_output(
            contacts=result.get("_raw_persons", []),
            query=result.get("query"),
            from_cache=result.get("from_cache", False),
            operation="search",
        )
        output.structured_data = {
            "contacts": result["contacts"],
            "total": result["total"],
        }
        return output


_list_contact_groups_instance = ListContactGroupsTool()
_get_contact_group_members_instance = GetContactGroupMembersTool()
_search_other_contacts_instance = SearchOtherContactsTool()


@connector_tool(
    name="list_contact_groups",
    agent_name=AGENT_CONTACT,
    context_domain=CONTEXT_DOMAIN_CONTACTS,
    category="read",
)
async def list_contact_groups_tool(
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    List the user's contact groups (family, colleagues, ...) with exact member counts.

    Google Contacts only (other providers get a clear unsupported message).

    Returns:
        UnifiedToolOutput with the user-defined groups and their member counts.
    """
    return await _list_contact_groups_instance.execute(runtime=runtime)


@connector_tool(
    name="get_contact_group_members",
    agent_name=AGENT_CONTACT,
    context_domain=CONTEXT_DOMAIN_CONTACTS,
    category="read",
)
async def get_contact_group_members_tool(
    group_name: Annotated[
        str,
        "Contact group name as the user says it (e.g. 'famille', 'Collègues'). "
        "Matched case-insensitively against the user's groups.",
    ],
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Get the members of a contact group with their email addresses.

    Use before sending an email to a whole group ("send this to my family
    group"): the returned member emails feed the email tools' recipients.
    Google Contacts only.

    Returns:
        UnifiedToolOutput with the group, its members (name + emails) and count.
    """
    return await _get_contact_group_members_instance.execute(runtime=runtime, group_name=group_name)


@connector_tool(
    name="search_other_contacts",
    agent_name=AGENT_CONTACT,
    context_domain=CONTEXT_DOMAIN_CONTACTS,
    category="read",
)
async def search_other_contacts_tool(
    query: Annotated[
        str,
        "Name, email or phone prefix of the person to find among 'other "
        "contacts' (people the user interacted with but never saved).",
    ],
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """
    Search people the user has interacted with but never saved as contacts.

    Use when regular contact search finds nobody: correspondents, one-off
    email exchanges and meeting attendees usually live here. Google only.

    Returns:
        UnifiedToolOutput with normalized matches flagged source=other_contacts.
    """
    return await _search_other_contacts_instance.execute(runtime=runtime, query=query)
