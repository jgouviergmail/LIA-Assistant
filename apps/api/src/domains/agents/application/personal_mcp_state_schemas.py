"""Consent shows a concrete target value and seals the complete original row."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue, StrictBool

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.infrastructure.mcp.personal_state_contract import PersonalMCPStateSnapshot


class PersonalMCPStateInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    server_id: UUID
    enabled: StrictBool


class PersonalMCPStateObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: PersonalMCPStateInput
    expected: PersonalMCPStateSnapshot


class PersonalMCPStatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    personal_mcp_state: PersonalMCPStateObservation


class PersonalMCPStateField(StrEnum):
    STATE = "personal_mcp_state"


def personal_mcp_state_target(
    expected: PersonalMCPStateSnapshot, enabled: bool | None = None
) -> dict[str, JsonValue]:
    server = expected.server
    return {
        "id": str(server.id),
        "name": server.name,
        "endpoint_host": server.endpoint_host,
        "plugin_id": str(server.plugin_id) if server.plugin_id is not None else None,
        "is_enabled": server.is_enabled if enabled is None else enabled,
    }


def canonical_personal_mcp_state(draft: ApplicationActionDraftContent) -> bool:
    selected = PersonalMCPStatePatch.model_validate(draft.intent).personal_mcp_state
    previous = selected.expected.server
    return (
        selected.request.server_id == previous.id
        and draft.before == {"personal_mcp_state": personal_mcp_state_target(selected.expected)}
        and draft.after
        == {
            "personal_mcp_state": personal_mcp_state_target(
                selected.expected, selected.request.enabled
            )
        }
    )
