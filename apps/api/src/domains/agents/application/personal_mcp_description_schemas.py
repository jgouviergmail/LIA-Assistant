"""Consent promises regeneration, never an unknown generated description."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.personal_mcp_state_schemas import personal_mcp_state_target
from src.infrastructure.mcp.personal_state_contract import PersonalMCPStateSnapshot


class PersonalMCPDescriptionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    server_id: UUID


class PersonalMCPDescriptionObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: PersonalMCPDescriptionInput
    expected: PersonalMCPStateSnapshot


class PersonalMCPDescriptionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    personal_mcp_description: PersonalMCPDescriptionObservation


class PersonalMCPDescriptionField(StrEnum):
    DESCRIPTION = "personal_mcp_description"


def description_before(expected: PersonalMCPStateSnapshot) -> dict[str, JsonValue]:
    return {
        **personal_mcp_state_target(expected),
        "domain_description": expected.server.domain_description,
        "tool_count": expected.server.tool_count,
    }


def description_after(expected: PersonalMCPStateSnapshot) -> dict[str, JsonValue]:
    return {
        **personal_mcp_state_target(expected),
        "requested": True,
        "may_use_platform_llm": True,
        "uses_cached_metadata": True,
        "overwrites_description": True,
    }


def canonical_personal_mcp_description(draft: ApplicationActionDraftContent) -> bool:
    selected = PersonalMCPDescriptionPatch.model_validate(draft.intent).personal_mcp_description
    return (
        selected.request.server_id == selected.expected.server.id
        and selected.expected.server.tool_count > 0
        and draft.before == {"personal_mcp_description": description_before(selected.expected)}
        and draft.after == {"personal_mcp_description": description_after(selected.expected)}
    )
