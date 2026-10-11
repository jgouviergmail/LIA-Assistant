"""Explicit bounded settings preview; complete original state remains privately sealed."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.infrastructure.mcp.personal_settings_contract import PersonalMCPSettingsValues
from src.infrastructure.mcp.personal_state_contract import PersonalMCPStateSnapshot


class PersonalMCPSettingsInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    server_id: UUID
    patch: PersonalMCPSettingsValues


class PersonalMCPSettingsObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: PersonalMCPSettingsInput
    expected: PersonalMCPStateSnapshot


class PersonalMCPSettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    personal_mcp_settings: PersonalMCPSettingsObservation


class PersonalMCPSettingsField(StrEnum):
    SETTINGS = "personal_mcp_settings"


def personal_mcp_settings_target(
    expected: PersonalMCPStateSnapshot, patch: PersonalMCPSettingsValues | None = None
) -> dict[str, JsonValue]:
    server = expected.server
    result: dict[str, JsonValue] = {
        "id": str(server.id),
        "endpoint_host": server.endpoint_host,
        "plugin_id": str(server.plugin_id) if server.plugin_id is not None else None,
        "name": server.name,
        "domain_description": server.domain_description,
        "timeout_seconds": server.timeout_seconds,
        "iterative_mode": server.iterative_mode,
    }
    if patch is not None:
        result.update(patch.model_dump(mode="json", exclude_unset=True))
    return result


def canonical_personal_mcp_settings(draft: ApplicationActionDraftContent) -> bool:
    selected = PersonalMCPSettingsPatch.model_validate(draft.intent).personal_mcp_settings
    return (
        selected.request.server_id == selected.expected.server.id
        and draft.before
        == {"personal_mcp_settings": personal_mcp_settings_target(selected.expected)}
        and draft.after
        == {
            "personal_mcp_settings": personal_mcp_settings_target(
                selected.expected, selected.request.patch
            )
        }
    )
