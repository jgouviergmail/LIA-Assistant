"""Exact probe consent promises discovery effects rather than unknown outcomes."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.personal_mcp_state_schemas import personal_mcp_state_target
from src.infrastructure.mcp.personal_state_contract import PersonalMCPStateSnapshot


class PersonalMCPConnectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    server_id: UUID


class PersonalMCPConnectionObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: PersonalMCPConnectionInput
    expected: PersonalMCPStateSnapshot


class PersonalMCPConnectionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    personal_mcp_connection: PersonalMCPConnectionObservation


class PersonalMCPConnectionField(StrEnum):
    CONNECTION = "personal_mcp_connection"


def connection_before(expected: PersonalMCPStateSnapshot) -> dict[str, JsonValue]:
    return {
        **personal_mcp_state_target(expected),
        "status": expected.server.status,
        "tool_count": expected.server.tool_count,
    }


def connection_after(expected: PersonalMCPStateSnapshot) -> dict[str, JsonValue]:
    return {
        **personal_mcp_state_target(expected),
        "requested": True,
        "contacts_endpoint": True,
        "refreshes_discovery": True,
        "may_call_read_me": True,
        "may_use_platform_llm": not bool(expected.server.domain_description),
        "may_compute_embeddings": True,
        "may_refresh_oauth_tokens": expected.server.auth_type == "oauth2",
    }


def canonical_personal_mcp_connection(draft: ApplicationActionDraftContent) -> bool:
    selected = PersonalMCPConnectionPatch.model_validate(draft.intent).personal_mcp_connection
    return (
        selected.request.server_id == selected.expected.server.id
        and draft.before == {"personal_mcp_connection": connection_before(selected.expected)}
        and draft.after == {"personal_mcp_connection": connection_after(selected.expected)}
    )
