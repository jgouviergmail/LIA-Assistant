"""Public plugin schema growth, execution modes and actor boundaries stay explicit."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.capability_origin import CapabilityOrigin, CapabilityShare
from src.domains.agents.application import plugin_read
from src.domains.agents.application.plugin_read_schemas import (
    PluginReadInput,
    PluginReadItem,
)
from src.domains.agents.application.plugin_read_spec import PLUGIN_READ_MANIFEST
from src.domains.agents.tools.application_plugin_tools import get_lia_plugins_tool
from src.domains.plugins.schemas import PluginListResponse, PluginResponse

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("shared", [False, True])
async def test_real_settings_rows_remain_readable_without_exposing_sender_metadata(
    monkeypatch, shared
):
    source = PluginResponse(
        id=uuid4(),
        name="Visible plugin",
        spec_version="1.0.0",
        shared_origin=(
            CapabilityOrigin(
                sender_display_name="private-data",
                shared_at=datetime.now(UTC),
                transfer_id=uuid4(),
            )
            if shared
            else None
        ),
        shared_with=(
            [
                CapabilityShare(
                    recipient_id=uuid4(),
                    recipient_display_name="private-data",
                    shared_at=datetime.now(UTC),
                    transfer_id=uuid4(),
                    complete=False,
                    can_share_again=False,
                )
            ]
            if shared
            else []
        ),
    )
    before = source.model_dump()
    monkeypatch.setattr(plugin_read, "require_plugin_access", AsyncMock())
    monkeypatch.setattr(
        plugin_read,
        "list_plugin_projection",
        AsyncMock(return_value=PluginListResponse(plugins=[source], total=1)),
    )
    result = await plugin_read.read_plugins(AsyncMock(), uuid4(), PluginReadInput())
    assert result.total == 1 and result.next_offset is None
    assert result.items[0].id == source.id and result.items[0].name == "Visible plugin"
    assert all(
        value not in result.model_dump_json()
        for value in ["private-data", "shared_origin", "shared_with"]
    )
    assert source.model_dump() == before


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
        # Peer origin and recipients belong to the settings UI, not the
        # assistant's plugin inventory.
        set(PluginResponse.model_fields) - {"shared_origin", "shared_with"}
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
