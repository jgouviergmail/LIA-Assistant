"""Application startup binds the existing personal MCP switch owner."""

from dataclasses import dataclass

from src.core.exceptions import AuthorizationError
from src.infrastructure.mcp.personal_configuration_contract import PersonalMCPConfigurationWriter
from src.infrastructure.mcp.personal_connection_contract import PersonalMCPConnectionWriter
from src.infrastructure.mcp.personal_description_contract import PersonalMCPDescriptionWriter
from src.infrastructure.mcp.personal_oauth_contract import (
    PersonalMCPOAuthStarter,
    PersonalMCPOAuthWriter,
)
from src.infrastructure.mcp.personal_settings_contract import PersonalMCPSettingsWriter
from src.infrastructure.mcp.personal_state_contract import (
    PersonalMCPDeleteWriter,
    PersonalMCPOAuthDisconnectWriter,
    PersonalMCPStateReader,
    PersonalMCPStateWriter,
)


@dataclass(frozen=True)
class PersonalMCPStateGateway:
    read: PersonalMCPStateReader
    write: PersonalMCPStateWriter
    settings: PersonalMCPSettingsWriter | None = None
    remove: PersonalMCPDeleteWriter | None = None
    describe: PersonalMCPDescriptionWriter | None = None
    connect: PersonalMCPConnectionWriter | None = None
    oauth_disconnect: PersonalMCPOAuthDisconnectWriter | None = None
    configure: PersonalMCPConfigurationWriter | None = None
    oauth_start: PersonalMCPOAuthStarter | None = None
    oauth_save: PersonalMCPOAuthWriter | None = None


_gateway: PersonalMCPStateGateway | None = None


def configure_personal_mcp_state(
    gateway: PersonalMCPStateGateway | None,
) -> PersonalMCPStateGateway | None:
    global _gateway
    previous, _gateway = _gateway, gateway
    return previous


def get_personal_mcp_state() -> PersonalMCPStateGateway:
    if _gateway is None:
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})
    return _gateway
