"""New UI metadata requires a reviewed native projection; identity stays injected."""

from typing import get_args
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.application_tools import APPLICATION_TOOL_NAMES
from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.agents.application.catalogue_registration import APPLICATION_MANIFESTS
from src.domains.agents.application.native_operations import NATIVE_OPERATIONS
from src.domains.agents.application.operation_spec import OperationKind
from src.domains.agents.application.personal_mcp_read_schemas import (
    PersonalMCPReadInput,
    PersonalMCPReadItem,
    PersonalMCPToolItem,
)
from src.domains.agents.application.personal_mcp_read_spec import (
    PERSONAL_MCP_READ_MANIFEST,
    PERSONAL_MCP_READ_OPERATION,
)
from src.domains.agents.tools.application_personal_mcp_tools import (
    get_lia_personal_mcp_servers_tool,
)
from src.domains.user_mcp.management_projection import read_personal_mcp_metadata
from src.domains.user_mcp.models import UserMCPAuthType, UserMCPServerStatus
from src.domains.user_mcp.schemas import (
    MCPDiscoveredToolResponse,
    UserMCPServerResponse,
)
from src.infrastructure.mcp.personal_metadata_gateway import (
    configure_personal_mcp_metadata,
    get_personal_mcp_metadata,
)
from src.infrastructure.startup.integrations import init_user_mcp_pool

pytestmark = pytest.mark.unit


def test_personal_mcp_fields_have_explicit_public_or_private_policy():
    assert set(get_args(PersonalMCPReadItem.model_fields["auth_type"].annotation)) == {
        item.value for item in UserMCPAuthType
    }
    assert set(get_args(PersonalMCPReadItem.model_fields["status"].annotation)) == {
        item.value for item in UserMCPServerStatus
    }
    native = set(PersonalMCPReadItem.model_fields) - {
        "endpoint_host",
        "has_connection_error",
        "next_tool_offset",
    }
    # The assistant inventory deliberately omits UI-only sender identity/time.
    assert set(UserMCPServerResponse.model_fields) == native | {
        "url",
        "last_error",
        "shared_origin",
    }
    assert set(MCPDiscoveredToolResponse.model_fields) == set(PersonalMCPToolItem.model_fields) | {
        "input_schema"
    }
    for field in ["actor_id", "user_id", "include_credentials", "include_errors"]:
        with pytest.raises(ValidationError):
            PersonalMCPReadInput.model_validate({field: str(uuid4())})
    for field in ["limit", "tools_limit"]:
        with pytest.raises(ValidationError):
            PersonalMCPReadInput.model_validate({field: True})


def test_personal_mcp_read_is_registered_for_both_modes_without_side_effects():
    operation = PERSONAL_MCP_READ_OPERATION
    assert operation.kind == OperationKind.READ and not operation.administrative
    assert operation in NATIVE_OPERATIONS and operation.tool_name in APPLICATION_TOOL_NAMES
    assert PERSONAL_MCP_READ_MANIFEST in APPLICATION_MANIFESTS
    assert PERSONAL_MCP_READ_MANIFEST.mutation_policy == "read"
    assert not PERSONAL_MCP_READ_MANIFEST.initiative_eligible
    assert set(get_lia_personal_mcp_servers_tool.tool_call_schema.model_fields) == {"query"}


async def test_personal_metadata_lifetime_fails_closed_and_survives_pool_failure(
    monkeypatch,
):
    previous = configure_personal_mcp_metadata(None)
    try:
        with pytest.raises(AuthorizationError):
            get_personal_mcp_metadata()
        monkeypatch.setattr(settings, "mcp_user_enabled", True)
        monkeypatch.setattr(
            "src.infrastructure.mcp.user_pool.initialize_user_mcp_pool",
            AsyncMock(side_effect=RuntimeError("test pool unavailable")),
        )
        await init_user_mcp_pool()
        assert get_personal_mcp_metadata() is read_personal_mcp_metadata
        monkeypatch.setattr(settings, "mcp_user_enabled", False)
        await init_user_mcp_pool()
        with pytest.raises(AuthorizationError):
            get_personal_mcp_metadata()
    finally:
        configure_personal_mcp_metadata(previous)
