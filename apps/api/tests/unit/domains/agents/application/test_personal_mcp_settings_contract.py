"""API/form growth must explicitly extend the supported or secure MCP field policy."""

import re
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.application_tools import APPLICATION_TOOL_NAMES
from src.core.config import settings
from src.domains.agents.application.catalogue_registration import APPLICATION_MANIFESTS
from src.domains.agents.application.management_editors import MANAGEMENT_EDITORS
from src.domains.agents.application.management_rendering import MANAGEMENT_CANONICAL
from src.domains.agents.application.native_operations import NATIVE_OPERATIONS
from src.domains.agents.application.personal_mcp_settings_manifest import (
    PERSONAL_MCP_SETTINGS_MANIFEST,
)
from src.domains.agents.application.personal_mcp_settings_schemas import PersonalMCPSettingsInput
from src.domains.agents.application.personal_mcp_settings_spec import (
    PERSONAL_MCP_SETTINGS_OPERATION,
)
from src.domains.agents.tools.application_personal_mcp_tools import (
    update_lia_personal_mcp_server_settings_tool,
)
from src.domains.user_mcp.schemas import UserMCPServerUpdate
from src.infrastructure.mcp.personal_settings_contract import PersonalMCPSettingsValues

pytestmark = pytest.mark.unit

SECURE_FIELDS = {
    "url",
    "auth_type",
    "api_key",
    "header_name",
    "bearer_token",
    "oauth_client_id",
    "oauth_client_secret",
    "oauth_scopes",
}


def test_form_and_api_settings_have_explicit_reviewed_policy_and_original_bounds():
    ordinary = {"name", "domain_description", "timeout_seconds", "iterative_mode"}
    # Spec 2026-10-30 D7: the chat writes these only to make LIA ask more — a server's
    # confirmation (« true » alone) and the tools to always ask about — and who drives
    # the server is judged by the synthesis at proposal and at the write.
    tighten_only = {"hitl_required", "always_ask_tools"}
    shape = {"iterative_mode", "react_expand_iterative"}
    assert set(PersonalMCPSettingsValues.model_fields) == ordinary | tighten_only | shape
    assert set(UserMCPServerUpdate.model_fields) == ordinary | SECURE_FIELDS | {
        "hitl_required",
        "react_expand_iterative",
    }
    root = Path(__file__).resolve().parents[7]
    source = (root / "apps/web/src/lib/mcp-server-form.ts").read_text(encoding="utf-8")
    form = re.search(r"interface MCPServerFormState\s*\{([^}]+)\}", source)
    assert form is not None
    assert set(re.findall(r"^\s*(\w+):", form.group(1), re.MULTILINE)) == ordinary | SECURE_FIELDS
    original = UserMCPServerUpdate.model_json_schema()["properties"]
    native = PersonalMCPSettingsValues.model_json_schema()["properties"]
    for field in ordinary:
        for bound in ("minimum", "maximum", "minLength", "maxLength"):
            assert original[field]["anyOf"][0].get(bound) == native[field]["anyOf"][0].get(bound)


def test_non_secret_patch_refuses_credentials_identity_coercion_and_invalid_clear():
    for field in SECURE_FIELDS | {"actor_id", "user_id", "hitl_required", "react_expand_iterative"}:
        with pytest.raises(ValidationError):
            PersonalMCPSettingsValues.model_validate({field: "private"})
    for payload in [
        {},
        {"timeout_seconds": True},
        {"timeout_seconds": 4},
        {"timeout_seconds": 121},
        {"name": None},
        {"name": "   "},
        {"iterative_mode": None},
    ]:
        with pytest.raises(ValidationError):
            PersonalMCPSettingsValues.model_validate(payload)
    assert PersonalMCPSettingsInput(
        server_id=uuid4(), patch=PersonalMCPSettingsValues(domain_description=None)
    ).patch.model_fields_set == {"domain_description"}


def test_confirmation_travels_tighten_only_and_is_published_so():
    """Spec 2026-10-30 D7: what the model may write is what the schema publishes."""
    limit = settings.mcp_max_tools_per_server
    for payload in [
        {"hitl_required": None},
        {"hitl_required": "true"},
        {"react_expand_iterative": None},
        {"always_ask_tools": None},
        {"always_ask_tools": []},
        {"always_ask_tools": ["delete_note", "delete_note"]},
        {"always_ask_tools": [""]},
        {"always_ask_tools": [f"tool_{i}" for i in range(limit + 1)]},
    ]:
        with pytest.raises(ValidationError):
            PersonalMCPSettingsValues.model_validate(payload)
    published = PersonalMCPSettingsValues.model_json_schema()["properties"]
    assert published["hitl_required"]["const"] is True
    assert "Settings > MCP Servers" in published["hitl_required"]["description"]
    tools = published["always_ask_tools"]
    assert tools["uniqueItems"] is True
    assert tools["anyOf"][0]["maxItems"] == limit


def test_settings_draft_and_amendments_use_complete_native_registries():
    operation = PERSONAL_MCP_SETTINGS_OPERATION
    assert operation in NATIVE_OPERATIONS and operation.tool_name in APPLICATION_TOOL_NAMES
    assert (
        operation.operation_id in MANAGEMENT_CANONICAL
        and operation.operation_id in MANAGEMENT_EDITORS
    )
    assert PERSONAL_MCP_SETTINGS_MANIFEST in APPLICATION_MANIFESTS
    assert (
        PERSONAL_MCP_SETTINGS_MANIFEST.mutation_policy == "draft"
        and not PERSONAL_MCP_SETTINGS_MANIFEST.permissions.hitl_required
    )
    assert not operation.administrative
    assert set(update_lia_personal_mcp_server_settings_tool.tool_call_schema.model_fields) == {
        "request"
    }
