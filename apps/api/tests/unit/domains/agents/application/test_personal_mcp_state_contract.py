"""A personal switch is draft-only, fully registered and distinct from MCP calls."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.application_tools import APPLICATION_TOOL_NAMES
from src.core.i18n_personal_mcp import PERSONAL_MCP_STATE_COPY
from src.domains.agents.application.catalogue_registration import APPLICATION_MANIFESTS
from src.domains.agents.application.management_editors import MANAGEMENT_EDITORS
from src.domains.agents.application.management_rendering import (
    MANAGEMENT_CANONICAL,
    MANAGEMENT_PREVIEW_NOTES,
)
from src.domains.agents.application.native_operations import NATIVE_OPERATIONS
from src.domains.agents.application.personal_mcp_state_manifest import PERSONAL_MCP_STATE_MANIFEST
from src.domains.agents.application.personal_mcp_state_schemas import PersonalMCPStateInput
from src.domains.agents.application.personal_mcp_state_spec import PERSONAL_MCP_STATE_OPERATION
from src.domains.agents.tools.application_personal_mcp_tools import (
    set_lia_personal_mcp_server_enabled_tool,
)

pytestmark = pytest.mark.unit


def test_personal_mcp_state_requires_exact_one_consent_and_complete_registries():
    operation = PERSONAL_MCP_STATE_OPERATION
    assert operation in NATIVE_OPERATIONS and operation.tool_name in APPLICATION_TOOL_NAMES
    assert (
        operation.operation_id in MANAGEMENT_CANONICAL
        and operation.operation_id in MANAGEMENT_EDITORS
    )
    assert operation.operation_id in MANAGEMENT_PREVIEW_NOTES
    assert PERSONAL_MCP_STATE_MANIFEST in APPLICATION_MANIFESTS
    assert PERSONAL_MCP_STATE_MANIFEST.mutation_policy == "draft"
    assert not PERSONAL_MCP_STATE_MANIFEST.permissions.hitl_required
    assert not PERSONAL_MCP_STATE_MANIFEST.initiative_eligible and not operation.administrative
    assert set(set_lia_personal_mcp_server_enabled_tool.tool_call_schema.model_fields) == {
        "request"
    }
    assert set(PERSONAL_MCP_STATE_COPY) == {"fr", "en", "es", "de", "it", "zh-CN"}


def test_personal_mcp_state_does_not_accept_model_identity_or_an_inversion():
    assert set(PersonalMCPStateInput.model_fields) == {"server_id", "enabled"}
    payload = {"server_id": str(uuid4()), "enabled": True}
    for field in ["actor_id", "user_id", "toggle", "credentials", "url"]:
        with pytest.raises(ValidationError):
            PersonalMCPStateInput.model_validate({**payload, field: "private"})
    for value in ["true", 1, None]:
        with pytest.raises(ValidationError):
            PersonalMCPStateInput.model_validate({**payload, "enabled": value})
