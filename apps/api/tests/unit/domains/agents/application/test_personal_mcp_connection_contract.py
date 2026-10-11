"""Probe discovery cannot acquire caller-controlled authority or omit registry wiring."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.application_tools import APPLICATION_TOOL_NAMES
from src.core.i18n_personal_mcp import PERSONAL_MCP_CONNECTION_COPY
from src.domains.agents.application.catalogue_registration import APPLICATION_MANIFESTS
from src.domains.agents.application.management_editors import MANAGEMENT_EDITORS
from src.domains.agents.application.management_rendering import MANAGEMENT_CANONICAL
from src.domains.agents.application.native_operations import NATIVE_OPERATIONS
from src.domains.agents.application.personal_mcp_connection_manifest import (
    PERSONAL_MCP_CONNECTION_MANIFEST,
)
from src.domains.agents.application.personal_mcp_connection_schemas import (
    PersonalMCPConnectionInput,
)
from src.domains.agents.application.personal_mcp_connection_spec import (
    PERSONAL_MCP_CONNECTION_OPERATION,
)
from src.domains.agents.tools.application_personal_mcp_tools import (
    test_lia_personal_mcp_connection_tool as probe_tool,
)
from src.domains.user_mcp.schemas import UserMCPTestConnectionResponse

pytestmark = pytest.mark.unit


def test_probe_is_registered_as_one_owned_nonadministrative_draft():
    spec = PERSONAL_MCP_CONNECTION_OPERATION
    assert spec in NATIVE_OPERATIONS and spec.tool_name in APPLICATION_TOOL_NAMES
    assert spec.operation_id in MANAGEMENT_CANONICAL and spec.operation_id in MANAGEMENT_EDITORS
    assert PERSONAL_MCP_CONNECTION_MANIFEST in APPLICATION_MANIFESTS
    assert PERSONAL_MCP_CONNECTION_MANIFEST.mutation_policy == "draft"
    assert (
        not PERSONAL_MCP_CONNECTION_MANIFEST.permissions.hitl_required and not spec.administrative
    )
    assert not PERSONAL_MCP_CONNECTION_MANIFEST.initiative_eligible
    assert set(probe_tool.tool_call_schema.model_fields) == {"request"}
    assert set(PERSONAL_MCP_CONNECTION_COPY) == {"fr", "en", "es", "de", "it", "zh-CN"}


def test_original_probe_result_growth_requires_a_projection_review():
    # success -> connection_success; error -> error_kind; description/count ->
    # stored server metadata; schemas/raw errors stay private, tools use paged read.
    assert set(UserMCPTestConnectionResponse.model_fields) == {
        "success",
        "error",
        "domain_description",
        "tool_count",
        "tools",
    }
    for field in [
        "actor_id",
        "user_id",
        "url",
        "credentials",
        "model",
        "skip_quota",
        "timeout_seconds",
        "force_refresh",
    ]:
        with pytest.raises(ValidationError):
            PersonalMCPConnectionInput.model_validate({"server_id": str(uuid4()), field: "private"})
