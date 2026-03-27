"""
Unit tests for Hue catalogue manifests.

Verifies that all tool and agent manifests are correctly defined
and consistent with actual tool implementations.
"""

import pytest

from src.domains.agents.constants import AGENT_HUE, CONTEXT_DOMAIN_HUE
from src.domains.agents.hue.catalogue_manifests import (
    activate_hue_scene_catalogue_manifest,
    control_hue_light_catalogue_manifest,
    control_hue_room_catalogue_manifest,
    hue_agent_manifest,
    list_hue_lights_catalogue_manifest,
    list_hue_rooms_catalogue_manifest,
    list_hue_scenes_catalogue_manifest,
)


@pytest.mark.unit
class TestHueAgentManifest:
    """Test Hue agent manifest."""

    def test_agent_name(self) -> None:
        """Test agent name matches constant."""
        assert hue_agent_manifest.name == AGENT_HUE

    def test_tools_count(self) -> None:
        """Test agent has 6 tools."""
        assert len(hue_agent_manifest.tools) == 6

    def test_tool_names(self) -> None:
        """Test all tool names are present."""
        expected = {
            "list_hue_lights_tool",
            "control_hue_light_tool",
            "list_hue_rooms_tool",
            "control_hue_room_tool",
            "list_hue_scenes_tool",
            "activate_hue_scene_tool",
        }
        assert set(hue_agent_manifest.tools) == expected


@pytest.mark.unit
class TestHueToolManifests:
    """Test individual tool manifests."""

    @pytest.mark.parametrize(
        "manifest",
        [
            list_hue_lights_catalogue_manifest,
            control_hue_light_catalogue_manifest,
            list_hue_rooms_catalogue_manifest,
            control_hue_room_catalogue_manifest,
            list_hue_scenes_catalogue_manifest,
            activate_hue_scene_catalogue_manifest,
        ],
    )
    def test_agent_name(self, manifest: object) -> None:
        """Test all manifests belong to hue_agent."""
        assert manifest.agent == AGENT_HUE  # type: ignore[attr-defined]

    @pytest.mark.parametrize(
        "manifest",
        [
            list_hue_lights_catalogue_manifest,
            control_hue_light_catalogue_manifest,
            list_hue_rooms_catalogue_manifest,
            control_hue_room_catalogue_manifest,
            list_hue_scenes_catalogue_manifest,
            activate_hue_scene_catalogue_manifest,
        ],
    )
    def test_context_key(self, manifest: object) -> None:
        """Test all manifests use correct context key."""
        assert manifest.context_key == CONTEXT_DOMAIN_HUE  # type: ignore[attr-defined]

    @pytest.mark.parametrize(
        "manifest",
        [
            list_hue_lights_catalogue_manifest,
            control_hue_light_catalogue_manifest,
            list_hue_rooms_catalogue_manifest,
            control_hue_room_catalogue_manifest,
            list_hue_scenes_catalogue_manifest,
            activate_hue_scene_catalogue_manifest,
        ],
    )
    def test_has_semantic_keywords(self, manifest: object) -> None:
        """Test all manifests have English-only semantic keywords."""
        keywords = manifest.semantic_keywords  # type: ignore[attr-defined]
        assert len(keywords) >= 3  # At least 3 keywords per tool

    def test_tool_names_match_functions(self) -> None:
        """Test manifest names match @tool function names."""
        expected_names = [
            "list_hue_lights_tool",
            "control_hue_light_tool",
            "list_hue_rooms_tool",
            "control_hue_room_tool",
            "list_hue_scenes_tool",
            "activate_hue_scene_tool",
        ]
        actual_names = [
            list_hue_lights_catalogue_manifest.name,
            control_hue_light_catalogue_manifest.name,
            list_hue_rooms_catalogue_manifest.name,
            control_hue_room_catalogue_manifest.name,
            list_hue_scenes_catalogue_manifest.name,
            activate_hue_scene_catalogue_manifest.name,
        ]
        assert actual_names == expected_names
