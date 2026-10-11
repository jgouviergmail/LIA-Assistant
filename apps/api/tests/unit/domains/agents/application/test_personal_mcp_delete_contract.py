"""Standalone deletion cannot opt out of ownership, group safety or confirmation."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.application_tools import APPLICATION_TOOL_NAMES
from src.core.i18n_personal_mcp import PERSONAL_MCP_DELETE_COPY
from src.domains.agents.application.catalogue_registration import APPLICATION_MANIFESTS
from src.domains.agents.application.management_editors import MANAGEMENT_EDITORS
from src.domains.agents.application.management_rendering import MANAGEMENT_CANONICAL
from src.domains.agents.application.native_operations import NATIVE_OPERATIONS
from src.domains.agents.application.personal_mcp_delete_manifest import PERSONAL_MCP_DELETE_MANIFEST
from src.domains.agents.application.personal_mcp_delete_schemas import PersonalMCPDeleteInput
from src.domains.agents.application.personal_mcp_delete_spec import PERSONAL_MCP_DELETE_OPERATION
from src.domains.agents.tools.application_personal_mcp_tools import (
    delete_lia_personal_mcp_server_tool,
)

pytestmark = pytest.mark.unit


def test_personal_mcp_delete_has_complete_registries_and_one_exact_confirmation():
    spec = PERSONAL_MCP_DELETE_OPERATION
    assert spec in NATIVE_OPERATIONS and spec.tool_name in APPLICATION_TOOL_NAMES
    assert spec.operation_id in MANAGEMENT_CANONICAL and spec.operation_id in MANAGEMENT_EDITORS
    assert PERSONAL_MCP_DELETE_MANIFEST in APPLICATION_MANIFESTS
    assert PERSONAL_MCP_DELETE_MANIFEST.mutation_policy == "draft"
    assert not PERSONAL_MCP_DELETE_MANIFEST.permissions.hitl_required and not spec.administrative
    assert not PERSONAL_MCP_DELETE_MANIFEST.initiative_eligible
    assert set(delete_lia_personal_mcp_server_tool.tool_call_schema.model_fields) == {"request"}
    assert set(PERSONAL_MCP_DELETE_COPY) == {"fr", "en", "es", "de", "it", "zh-CN"}


def test_personal_mcp_delete_request_never_grants_plugin_or_cross_account_access():
    assert set(PersonalMCPDeleteInput.model_fields) == {"server_id"}
    for field in ["actor_id", "user_id", "allow_plugin_owned", "plugin_id", "force"]:
        with pytest.raises(ValidationError):
            PersonalMCPDeleteInput.model_validate({"server_id": str(uuid4()), field: True})
