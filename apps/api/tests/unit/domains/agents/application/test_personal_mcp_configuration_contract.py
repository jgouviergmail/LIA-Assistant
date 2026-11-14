"""Private-form growth requires explicit source coverage; tool schemas never take secrets."""

import json
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
    MCP_FORM_EXCLUDED_FIELDS,
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
        == fields | MCP_FORM_EXCLUDED_FIELDS
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


class TestTheChatAddsAKnownServerByItsKey:
    """A known server is a public fact: its KEY may travel in the tool call, its address
    is read by the browser form from the published catalogue, never typed in the chat."""

    def test_a_published_key_selects_a_new_server_to_prefill(self):
        from src.infrastructure.mcp.known_servers import KNOWN_MCP_SERVER_KEYS

        for key in KNOWN_MCP_SERVER_KEYS:
            assert PersonalMCPConfigurationInput(known_server=key).known_server == key

    @pytest.mark.parametrize("key", ["", "not_in_the_catalogue", "https://mcp.example.com/mcp"])
    def test_a_key_the_catalogue_does_not_publish_is_refused(self, key):
        with pytest.raises(ValidationError):
            PersonalMCPConfigurationInput(known_server=key)

    def test_a_known_server_is_added_never_laid_over_an_existing_one(self):
        from src.infrastructure.mcp.known_servers import KNOWN_MCP_SERVER_KEYS

        with pytest.raises(ValidationError):
            PersonalMCPConfigurationInput(server_id=uuid4(), known_server=KNOWN_MCP_SERVER_KEYS[0])

    def test_the_tool_schema_publishes_the_keys_it_accepts(self):
        """What the validator refuses, the model can read (ADR-184)."""
        from src.infrastructure.mcp.known_servers import KNOWN_MCP_SERVER_KEYS

        schema = PersonalMCPConfigurationInput.model_json_schema()
        published = json.dumps(schema["properties"]["known_server"])

        assert all(f'"{key}"' in published for key in KNOWN_MCP_SERVER_KEYS)

    def test_the_draft_names_the_known_server_only_when_one_was_chosen(self):
        from src.domains.agents.application.personal_mcp_configuration_schemas import (
            PersonalMCPConfigurationObservation,
            configuration_after,
        )
        from src.infrastructure.mcp.known_servers import KNOWN_MCP_SERVER_KEYS

        key = KNOWN_MCP_SERVER_KEYS[0]
        chosen = PersonalMCPConfigurationObservation(
            request=PersonalMCPConfigurationInput(known_server=key), expected=None
        )
        typed = PersonalMCPConfigurationObservation(
            request=PersonalMCPConfigurationInput(), expected=None
        )

        assert configuration_after(chosen)["known_server"] == key
        # A browser bundle older than this lot parses the selection strictly: a
        # plain creation keeps the exact shape it always had.
        assert configuration_after(typed) == {
            "server_id": None,
            "creating": True,
            "requires_private_browser_form": True,
        }
