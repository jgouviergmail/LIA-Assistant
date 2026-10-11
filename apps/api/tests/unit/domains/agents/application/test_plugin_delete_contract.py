"""New public/private removal fields and actual model-bound input require explicit review."""

import pytest
from pydantic import ValidationError

from src.domains.agents.application.plugin_delete_manifest import PLUGIN_DELETE_MANIFEST
from src.domains.agents.application.plugin_delete_schemas import (
    PluginDeleteInput,
    PluginDeleteSnapshot,
)
from src.domains.agents.tools.application_plugin_tools import delete_lia_plugin_tool

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {"plugin_id": True},
        {"plugin_id": "bad"},
        {"plugin_id": "11111111-1111-1111-1111-111111111111", "user_id": "other"},
    ],
)
def test_only_exact_plugin_identity_can_be_supplied(payload):
    with pytest.raises(ValidationError):
        PluginDeleteInput.model_validate(payload)


def test_fields_and_actual_tool_schema_are_reviewed():
    assert set(PluginDeleteSnapshot.model_fields) == {"request", "plugin", "state_digest"}
    assert PLUGIN_DELETE_MANIFEST.parameters[0].schema == PluginDeleteInput.model_json_schema()
    assert set(delete_lia_plugin_tool.tool_call_schema.model_json_schema()["properties"]) == {
        "request"
    }
    assert PLUGIN_DELETE_MANIFEST.mutation_policy == "draft"
    assert not PLUGIN_DELETE_MANIFEST.initiative_eligible
