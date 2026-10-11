"""OAuth withdrawal is a single explicit owned draft, with no secret arguments."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.application_tools import APPLICATION_TOOL_NAMES
from src.core.i18n_personal_mcp import PERSONAL_MCP_OAUTH_DISCONNECT_COPY
from src.domains.agents.application.catalogue_registration import APPLICATION_MANIFESTS
from src.domains.agents.application.management_editors import MANAGEMENT_EDITORS
from src.domains.agents.application.management_rendering import MANAGEMENT_CANONICAL
from src.domains.agents.application.native_operations import NATIVE_OPERATIONS
from src.domains.agents.application.personal_mcp_oauth_disconnect_manifest import (
    PERSONAL_MCP_OAUTH_DISCONNECT_MANIFEST,
)
from src.domains.agents.application.personal_mcp_oauth_disconnect_schemas import (
    PersonalMCPOAuthDisconnectInput,
)
from src.domains.agents.application.personal_mcp_oauth_disconnect_spec import (
    PERSONAL_MCP_OAUTH_DISCONNECT_OPERATION,
)
from src.domains.agents.tools.application_personal_mcp_tools import (
    disconnect_lia_personal_mcp_oauth_tool,
)

pytestmark = pytest.mark.unit


def test_withdrawal_is_registered_without_extra_approval_or_administrator_scope():
    spec = PERSONAL_MCP_OAUTH_DISCONNECT_OPERATION
    manifest = PERSONAL_MCP_OAUTH_DISCONNECT_MANIFEST
    assert spec in NATIVE_OPERATIONS and spec.tool_name in APPLICATION_TOOL_NAMES
    assert spec.operation_id in MANAGEMENT_CANONICAL and spec.operation_id in MANAGEMENT_EDITORS
    assert manifest in APPLICATION_MANIFESTS and manifest.mutation_policy == "draft"
    assert not manifest.permissions.hitl_required and not spec.administrative
    assert not manifest.initiative_eligible
    assert set(disconnect_lia_personal_mcp_oauth_tool.tool_call_schema.model_fields) == {"request"}
    assert set(PERSONAL_MCP_OAUTH_DISCONNECT_COPY) == {"fr", "en", "es", "de", "it", "zh-CN"}


def test_caller_cannot_choose_tokens_credentials_authority_or_revocation_target():
    for field in [
        "actor_id",
        "user_id",
        "url",
        "access_token",
        "refresh_token",
        "client_secret",
        "revoke_provider_grant",
        "keep_client_credentials",
    ]:
        with pytest.raises(ValidationError):
            PersonalMCPOAuthDisconnectInput.model_validate(
                {"server_id": str(uuid4()), field: "private"}
            )
