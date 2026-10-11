"""Token purge consent contains only owned identity and safe authentication state."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.personal_mcp_state_schemas import personal_mcp_state_target
from src.infrastructure.mcp.personal_state_contract import PersonalMCPStateSnapshot


class PersonalMCPOAuthDisconnectInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    server_id: UUID


class PersonalMCPOAuthDisconnectObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: PersonalMCPOAuthDisconnectInput
    expected: PersonalMCPStateSnapshot


class PersonalMCPOAuthDisconnectPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    personal_mcp_oauth_disconnect: PersonalMCPOAuthDisconnectObservation


class PersonalMCPOAuthDisconnectField(StrEnum):
    OAUTH = "personal_mcp_oauth_disconnect"


def oauth_disconnect_before(expected: PersonalMCPStateSnapshot) -> dict[str, JsonValue]:
    return {
        **personal_mcp_state_target(expected),
        "auth_type": expected.server.auth_type,
        "status": expected.server.status,
    }


def oauth_disconnect_after(expected: PersonalMCPStateSnapshot) -> dict[str, JsonValue]:
    return {
        **personal_mcp_state_target(expected),
        "status": "auth_required",
        "connection_tokens_removed": True,
        "keeps_client_credentials": True,
    }


def canonical_personal_mcp_oauth_disconnect(draft: ApplicationActionDraftContent) -> bool:
    selected = PersonalMCPOAuthDisconnectPatch.model_validate(
        draft.intent
    ).personal_mcp_oauth_disconnect
    return (
        selected.request.server_id == selected.expected.server.id
        and selected.expected.server.auth_type == "oauth2"
        and draft.before
        == {"personal_mcp_oauth_disconnect": oauth_disconnect_before(selected.expected)}
        and draft.after
        == {"personal_mcp_oauth_disconnect": oauth_disconnect_after(selected.expected)}
    )
