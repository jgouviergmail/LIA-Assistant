"""OAuth additions must reach every action/consent registry without public secrets."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.application_tools import APPLICATION_TOOL_NAMES
from src.core.i18n_personal_mcp import PERSONAL_MCP_OAUTH_COPY
from src.domains.agents.application.catalogue_registration import APPLICATION_MANIFESTS
from src.domains.agents.application.management_editors import MANAGEMENT_EDITORS
from src.domains.agents.application.management_rendering import MANAGEMENT_CANONICAL
from src.domains.agents.application.native_operations import NATIVE_OPERATIONS
from src.domains.agents.application.operation_spec import OperationKind
from src.domains.agents.application.personal_mcp_oauth_manifest import PERSONAL_MCP_OAUTH_MANIFEST
from src.domains.agents.application.personal_mcp_oauth_schemas import PersonalMCPOAuthInput
from src.domains.agents.application.personal_mcp_oauth_spec import PERSONAL_MCP_OAUTH_OPERATION
from src.domains.agents.tools.application_personal_mcp_tools import (
    authorize_lia_personal_mcp_server_tool,
)


def test_original_browser_oauth_reaches_registries_and_excludes_secret_inputs():
    spec, manifest = PERSONAL_MCP_OAUTH_OPERATION, PERSONAL_MCP_OAUTH_MANIFEST
    assert spec in NATIVE_OPERATIONS and spec.tool_name in APPLICATION_TOOL_NAMES
    assert spec.kind == OperationKind.DEVICE and not spec.administrative
    assert spec.operation_id in MANAGEMENT_CANONICAL and spec.operation_id in MANAGEMENT_EDITORS
    assert manifest in APPLICATION_MANIFESTS and manifest.mutation_policy == "draft"
    assert not manifest.permissions.hitl_required and not manifest.initiative_eligible
    assert set(authorize_lia_personal_mcp_server_tool.tool_call_schema.model_fields) == {"request"}
    assert set(PERSONAL_MCP_OAUTH_COPY) == {"fr", "en", "es", "de", "it", "zh-CN"}
    for field in ["code", "token", "client_secret", "authorization_url", "actor_id"]:
        with pytest.raises(ValidationError):
            PersonalMCPOAuthInput.model_validate({"server_id": str(uuid4()), field: "private"})
