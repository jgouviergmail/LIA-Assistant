"""A model selects only an owned OAuth server; provider secrets remain private."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.personal_mcp_state_schemas import personal_mcp_state_target
from src.infrastructure.mcp.personal_state_contract import PersonalMCPStateSnapshot


class PersonalMCPOAuthInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    server_id: UUID


class PersonalMCPOAuthObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: PersonalMCPOAuthInput
    expected: PersonalMCPStateSnapshot


class PersonalMCPOAuthPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    personal_mcp_oauth: PersonalMCPOAuthObservation


class PersonalMCPOAuthField(StrEnum):
    OAUTH = "personal_mcp_oauth"


def oauth_before(expected: PersonalMCPStateSnapshot) -> dict[str, JsonValue]:
    return {
        **personal_mcp_state_target(expected),
        "auth_type": expected.server.auth_type,
        "status": expected.server.status,
    }


def oauth_after(expected: PersonalMCPStateSnapshot) -> dict[str, JsonValue]:
    return {
        **personal_mcp_state_target(expected),
        "requires_provider_authorization": True,
        "requires_original_browser_completion": True,
    }


def canonical_personal_mcp_oauth(draft: ApplicationActionDraftContent) -> bool:
    selected = PersonalMCPOAuthPatch.model_validate(draft.intent).personal_mcp_oauth
    return (
        selected.request.server_id == selected.expected.server.id
        and selected.expected.server.auth_type == "oauth2"
        and draft.before == {"personal_mcp_oauth": oauth_before(selected.expected)}
        and draft.after == {"personal_mcp_oauth": oauth_after(selected.expected)}
    )
