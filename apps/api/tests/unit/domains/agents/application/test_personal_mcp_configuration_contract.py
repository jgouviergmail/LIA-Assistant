"""Private-form growth requires explicit source coverage; tool schemas never take secrets."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.application_tools import APPLICATION_TOOL_NAMES
from src.core.i18n_personal_mcp import PERSONAL_MCP_CONFIGURATION_COPY
from src.domains.agents.application.catalogue_registration import APPLICATION_MANIFESTS
from src.domains.agents.application.management_editors import MANAGEMENT_EDITORS
from src.domains.agents.application.management_rendering import MANAGEMENT_CANONICAL
from src.domains.agents.application.native_operations import NATIVE_OPERATIONS
from src.domains.agents.application.operation_spec import OperationKind
from src.domains.agents.application.personal_mcp_configuration_manifest import (
    PERSONAL_MCP_CONFIGURATION_MANIFEST,
)
from src.domains.agents.application.personal_mcp_configuration_schemas import (
    PersonalMCPConfigurationInput,
)
from src.domains.agents.application.personal_mcp_configuration_spec import (
    PERSONAL_MCP_CONFIGURATION_OPERATION,
)
from src.domains.agents.tools.application_personal_mcp_tools import (
    configure_lia_personal_mcp_server_tool,
)
from src.domains.user_mcp.personal_configuration import (
    MCP_FORM_API_ONLY_FIELDS,
    validate_configuration_fields,
)
from src.domains.user_mcp.schemas import UserMCPServerCreate, UserMCPServerUpdate

pytestmark = pytest.mark.unit


def test_original_form_fields_and_api_only_controls_require_explicit_review():
    fields = {
        "name",
        "url",
        "auth_type",
        "api_key",
        "header_name",
        "bearer_token",
        "oauth_client_id",
        "oauth_client_secret",
        "oauth_scopes",
        "domain_description",
        "timeout_seconds",
        "iterative_mode",
    }
    assert (
        set(UserMCPServerCreate.model_fields)
        == set(UserMCPServerUpdate.model_fields)
        == fields | MCP_FORM_API_ONLY_FIELDS
    )
    for creating in [False, True]:
        for field in [
            "hitl_required",
            "actor_id",
            "user_id",
            "plugin_id",
            "extra_headers",
            "skip_validation",
        ]:
            with pytest.raises(ValueError, match="Unsupported private form fields"):
                validate_configuration_fields({field: False}, creating=creating)
    for field in fields | {"actor_id", "user_id", "model"}:
        with pytest.raises(ValidationError):
            PersonalMCPConfigurationInput.model_validate(
                {"server_id": str(uuid4()), field: "private-key"}
            )


def test_configuration_requires_original_browser_continuation_and_one_hitl():
    spec, manifest = PERSONAL_MCP_CONFIGURATION_OPERATION, PERSONAL_MCP_CONFIGURATION_MANIFEST
    assert spec in NATIVE_OPERATIONS and spec.tool_name in APPLICATION_TOOL_NAMES
    assert spec.kind == OperationKind.DEVICE and not spec.administrative
    assert spec.operation_id in MANAGEMENT_CANONICAL and spec.operation_id in MANAGEMENT_EDITORS
    assert manifest in APPLICATION_MANIFESTS and manifest.mutation_policy == "draft"
    assert not manifest.permissions.hitl_required and not manifest.initiative_eligible
    assert set(configure_lia_personal_mcp_server_tool.tool_call_schema.model_fields) == {"request"}
    assert set(PERSONAL_MCP_CONFIGURATION_COPY) == {"fr", "en", "es", "de", "it", "zh-CN"}
