"""Assistant intent selects a target, never private endpoint/authentication values."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.personal_mcp_state_schemas import personal_mcp_state_target
from src.infrastructure.mcp.known_servers import KNOWN_MCP_SERVER_KEYS, find_known_server
from src.infrastructure.mcp.personal_state_contract import PersonalMCPStateSnapshot


class PersonalMCPConfigurationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    server_id: UUID | None = None
    # A known server's KEY is public (infrastructure/mcp/known_servers): it selects what the
    # private form opens prefilled with. The address itself never travels in the call.
    known_server: str | None = Field(
        default=None,
        description=(
            "Key of one of LIA's known servers to ADD (omit server_id): the private "
            "form opens prefilled with its public name, address and authentication type"
        ),
        json_schema_extra={
            "anyOf": [{"type": "string", "enum": list(KNOWN_MCP_SERVER_KEYS)}, {"type": "null"}]
        },
    )

    @model_validator(mode="after")
    def known_server_is_published_and_new(self) -> PersonalMCPConfigurationInput:
        if self.known_server is None:
            return self
        if self.server_id is not None:
            raise ValueError("A known server is added, never laid over an existing server")
        if find_known_server(self.known_server) is None:
            raise ValueError("Unknown known_server key; the schema publishes the accepted keys")
        return self


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
    after: dict[str, JsonValue] = {
        "server_id": str(selected.request.server_id) if selected.request.server_id else None,
        "creating": selected.expected is None,
        "requires_private_browser_form": True,
    }
    # Present only when chosen: a plain creation keeps the shape every browser bundle
    # parses strictly.
    if selected.request.known_server is not None:
        after["known_server"] = selected.request.known_server
    return after


def canonical_personal_mcp_configuration(draft: ApplicationActionDraftContent) -> bool:
    selected = PersonalMCPConfigurationPatch.model_validate(draft.intent).personal_mcp_configuration
    return draft.before == {
        "personal_mcp_configuration": configuration_before(selected)
    } and draft.after == {"personal_mcp_configuration": configuration_after(selected)}
