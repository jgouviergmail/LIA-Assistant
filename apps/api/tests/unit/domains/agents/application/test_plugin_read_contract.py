"""Public plugin schema growth, execution modes and actor boundaries stay explicit."""

import pytest
from pydantic import ValidationError

from src.domains.agents.application.plugin_read_schemas import (
    PluginReadInput,
    PluginReadItem,
)
from src.domains.agents.application.plugin_read_spec import PLUGIN_READ_MANIFEST
from src.domains.agents.tools.application_plugin_tools import get_lia_plugins_tool
from src.domains.plugins.schemas import PluginResponse

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "query",
    [
        {"user_id": "other"},
        {"limit": True},
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"offset": False},
    ],
)
def test_scope_and_paging_are_strict(query):
    with pytest.raises(ValidationError):
        PluginReadInput.model_validate(query)


def test_new_ui_metadata_requires_explicit_native_review():
    assert (
        # Peer origin belongs to the settings UI, not the assistant's plugin inventory.
        set(PluginResponse.model_fields) - {"shared_origin"}
        == set(PluginReadItem.model_fields)
        == {
            "id",
            "name",
            "version",
            "description",
            "spec_version",
            "skill_names",
            "server_names",
            "created_at",
            "updated_at",
        }
    )


def test_bound_schema_matches_manifest_and_actor_is_injected():
    assert PLUGIN_READ_MANIFEST.parameters[0].schema == PluginReadInput.model_json_schema()
    assert set(get_lia_plugins_tool.tool_call_schema.model_json_schema()["properties"]) == {"query"}
    assert PLUGIN_READ_MANIFEST.mutation_policy == "read"
    assert not PLUGIN_READ_MANIFEST.initiative_eligible
