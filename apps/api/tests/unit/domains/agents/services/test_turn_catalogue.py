"""The turn's catalogue withholds every refused tool, for every execution mode.

The request snapshot is what the pipeline planner, the ReAct loop, the
router's ranking and the initiative all read. A switched-off capability used
to be dropped by the planner's own post-filter alone, so the ReAct loop bound
its tools and ran them: the exclusion now lives where the snapshot is built.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.registry.catalogue import CostProfile, PermissionProfile, ToolManifest
from src.domains.agents.services.turn_catalogue import build_turn_catalogue
from src.domains.feature_switches.registry import PlatformCapability

pytestmark = pytest.mark.unit


def _registry(tools_by_agent: dict[str, list[str]]) -> MagicMock:
    registry = MagicMock()

    def _list(agent: str | None = None) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(name=name, agent=agent or "test_agent")
            for name in tools_by_agent.get(agent or "", [])
        ]

    registry.list_tool_manifests.side_effect = _list
    return registry


def _catalogue(*names: str) -> list[ToolManifest]:
    """Real manifests: the turn's catalogue copies one it annotates (``dataclasses.replace``)."""
    return [
        ToolManifest(
            name=name,
            agent="test_agent",
            description=f"{name} under test",
            parameters=[],
            outputs=[],
            cost=CostProfile(),
            permissions=PermissionProfile(),
        )
        for name in names
    ]


async def test_a_switched_off_capability_and_an_unconnected_provider_are_both_withheld() -> None:
    registry = _registry({"image_generation_agent": ["generate_image", "edit_image"]})
    built = _catalogue(
        "get_emails_tool", "generate_image", "list_labels_tool", "edit_image", "get_events_tool"
    )
    with (
        patch("src.core.context.build_request_tool_manifests", return_value=built),
        patch(
            "src.domains.feature_switches.registry.disabled_capabilities",
            AsyncMock(return_value=frozenset({PlatformCapability.IMAGE_GENERATION})),
        ),
        patch(
            "src.domains.agents.tools.connector_requirements.unconnected_tool_names",
            return_value=frozenset({"list_labels_tool"}),
        ),
    ):
        offered = await build_turn_catalogue(registry, uuid4(), frozenset({"google_calendar"}))

    assert [manifest.name for manifest in offered] == ["get_emails_tool", "get_events_tool"]


async def test_a_source_nobody_serves_is_said_on_the_turn_s_copy_only() -> None:
    """The planner reads which category holds nothing for this account; the
    registry's manifest is every account's, so it is never the one annotated."""
    from src.domains.agents.tasks.catalogue_manifests import get_tasks_catalogue_manifest

    with (
        patch(
            "src.core.context.build_request_tool_manifests",
            return_value=[get_tasks_catalogue_manifest],
        ),
        patch(
            "src.domains.feature_switches.registry.disabled_capabilities",
            AsyncMock(return_value=frozenset()),
        ),
        patch(
            "src.domains.agents.tools.connector_requirements.unserved_category_tools",
            return_value={"get_tasks_tool": "tasks"},
        ),
    ):
        offered = await build_turn_catalogue(_registry({}), uuid4(), frozenset())

    assert [manifest.name for manifest in offered] == ["get_tasks_tool"]
    assert offered[0].unserved_category == "tasks"
    assert get_tasks_catalogue_manifest.unserved_category is None


async def test_every_capability_on_offers_the_whole_catalogue() -> None:
    built = _catalogue("get_emails_tool", "generate_image")
    with (
        patch("src.core.context.build_request_tool_manifests", return_value=built),
        patch(
            "src.domains.feature_switches.registry.disabled_capabilities",
            AsyncMock(return_value=frozenset()),
        ),
    ):
        offered = await build_turn_catalogue(_registry({}), uuid4(), None)

    assert [manifest.name for manifest in offered] == ["get_emails_tool", "generate_image"]
