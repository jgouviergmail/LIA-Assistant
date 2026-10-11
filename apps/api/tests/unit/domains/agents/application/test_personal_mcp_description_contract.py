"""Regeneration uses one consent and the original accounted bounded source contract."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.application_tools import APPLICATION_TOOL_NAMES
from src.core.i18n_personal_mcp import PERSONAL_MCP_DESCRIPTION_COPY
from src.domains.agents.application.catalogue_registration import APPLICATION_MANIFESTS
from src.domains.agents.application.management_editors import MANAGEMENT_EDITORS
from src.domains.agents.application.management_rendering import MANAGEMENT_CANONICAL
from src.domains.agents.application.native_operations import NATIVE_OPERATIONS
from src.domains.agents.application.personal_mcp_description_manifest import (
    PERSONAL_MCP_DESCRIPTION_MANIFEST,
)
from src.domains.agents.application.personal_mcp_description_schemas import (
    PersonalMCPDescriptionInput,
)
from src.domains.agents.application.personal_mcp_description_spec import (
    PERSONAL_MCP_DESCRIPTION_OPERATION,
)
from src.domains.agents.tools.application_personal_mcp_tools import (
    regenerate_lia_personal_mcp_description_tool,
)
from src.domains.user_mcp.schemas import UserMCPGenerateDescriptionResponse
from src.infrastructure.mcp.personal_description_contract import PersonalMCPDescriptionResult

pytestmark = pytest.mark.unit


def test_regeneration_is_registered_as_one_nonadministrative_draft():
    spec = PERSONAL_MCP_DESCRIPTION_OPERATION
    assert spec in NATIVE_OPERATIONS and spec.tool_name in APPLICATION_TOOL_NAMES
    assert spec.operation_id in MANAGEMENT_CANONICAL and spec.operation_id in MANAGEMENT_EDITORS
    assert PERSONAL_MCP_DESCRIPTION_MANIFEST in APPLICATION_MANIFESTS
    assert PERSONAL_MCP_DESCRIPTION_MANIFEST.mutation_policy == "draft"
    assert (
        not PERSONAL_MCP_DESCRIPTION_MANIFEST.permissions.hitl_required and not spec.administrative
    )
    assert not PERSONAL_MCP_DESCRIPTION_MANIFEST.initiative_eligible
    assert set(regenerate_lia_personal_mcp_description_tool.tool_call_schema.model_fields) == {
        "request"
    }
    assert set(PERSONAL_MCP_DESCRIPTION_COPY) == {"fr", "en", "es", "de", "it", "zh-CN"}


def test_original_result_growth_and_private_controls_require_explicit_review():
    assert set(PersonalMCPDescriptionResult.model_fields) == set(
        UserMCPGenerateDescriptionResponse.model_fields
    )
    for field in ["actor_id", "user_id", "model", "skip_quota", "max_tokens", "credentials"]:
        with pytest.raises(ValidationError):
            PersonalMCPDescriptionInput.model_validate(
                {"server_id": str(uuid4()), field: "private"}
            )
    for value in [0, True]:
        with pytest.raises(ValidationError):
            PersonalMCPDescriptionResult(domain_description="valid", tool_count=value)
    with pytest.raises(ValidationError):
        PersonalMCPDescriptionResult(domain_description="x" * 501, tool_count=1)
