"""Standalone MCP deletion exposes only exact public identity in confirmation."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.personal_mcp_state_schemas import personal_mcp_state_target
from src.infrastructure.mcp.personal_state_contract import PersonalMCPStateSnapshot


class PersonalMCPDeleteInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    server_id: UUID


class PersonalMCPDeleteObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: PersonalMCPDeleteInput
    expected: PersonalMCPStateSnapshot


class PersonalMCPDeletePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    personal_mcp_server_delete: PersonalMCPDeleteObservation


class PersonalMCPDeleteField(StrEnum):
    DELETE = "personal_mcp_server_delete"


def canonical_personal_mcp_delete(draft: ApplicationActionDraftContent) -> bool:
    selected = PersonalMCPDeletePatch.model_validate(draft.intent).personal_mcp_server_delete
    return (
        selected.request.server_id == selected.expected.server.id
        and selected.expected.server.plugin_id is None
        and draft.before
        == {"personal_mcp_server_delete": personal_mcp_state_target(selected.expected)}
        and draft.after == {"personal_mcp_server_delete": None}
    )
