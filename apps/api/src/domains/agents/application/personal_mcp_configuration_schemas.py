"""Assistant intent selects a target, never private endpoint/authentication values."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue, model_validator

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.personal_mcp_state_schemas import personal_mcp_state_target
from src.infrastructure.mcp.personal_state_contract import PersonalMCPStateSnapshot


class PersonalMCPConfigurationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    server_id: UUID | None = None


class PersonalMCPConfigurationSubmit(BaseModel):
    """Private HTTP body only; never a model tool schema or persisted intent."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    values: dict[str, JsonValue]


class PersonalMCPConfigurationObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: PersonalMCPConfigurationInput
    expected: PersonalMCPStateSnapshot | None

    @model_validator(mode="after")
    def exact_target(self) -> PersonalMCPConfigurationObservation:
        if (self.request.server_id is None) != (self.expected is None):
            raise ValueError("An existing configuration requires its exact owned snapshot")
        if self.expected and self.request.server_id != self.expected.server.id:
            raise ValueError("Configuration target mismatch")
        return self


class PersonalMCPConfigurationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    personal_mcp_configuration: PersonalMCPConfigurationObservation


class PersonalMCPConfigurationField(StrEnum):
    CONFIGURATION = "personal_mcp_configuration"


def configuration_before(
    selected: PersonalMCPConfigurationObservation,
) -> dict[str, JsonValue] | None:
    return personal_mcp_state_target(selected.expected) if selected.expected else None


def configuration_after(selected: PersonalMCPConfigurationObservation) -> dict[str, JsonValue]:
    return {
        "server_id": str(selected.request.server_id) if selected.request.server_id else None,
        "creating": selected.expected is None,
        "requires_private_browser_form": True,
    }


def canonical_personal_mcp_configuration(draft: ApplicationActionDraftContent) -> bool:
    selected = PersonalMCPConfigurationPatch.model_validate(draft.intent).personal_mcp_configuration
    return draft.before == {
        "personal_mcp_configuration": configuration_before(selected)
    } and draft.after == {"personal_mcp_configuration": configuration_after(selected)}
