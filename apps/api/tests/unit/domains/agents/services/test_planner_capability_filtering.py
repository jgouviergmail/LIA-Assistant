"""A disabled capability disappears from what a turn can reach.

Two layers protect a switched-off capability. The routes REFUSE it — that is
the enforcing one. This is the other: no turn may even be offered the tools,
for three reasons that all matter.

- **Honesty.** A turn that keeps proposing image generation on an instance
  where it is off produces calls that fail, and the user reads a refusal
  instead of an answer.
- **Cost.** Every tool in the catalogue is prompt tokens, on every call.
- **One answer for both modes.** The exclusion is applied where the request
  builds its catalogue, which the pipeline planner and the ReAct loop both
  read: it used to ride on the planner's post-filter alone, and the loop bound
  the tools of a switched-off capability.

Failure mode this pins: reading the switches must never take a turn down. An
unreachable settings store means "nothing disabled" — the product stays whole
and the routes still refuse what is off.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.feature_switches.registry import PlatformCapability

pytestmark = pytest.mark.unit


def _registry(tools_by_agent: dict[str, list[str]]) -> MagicMock:
    registry = MagicMock()

    def _list(agent: str | None = None) -> list[SimpleNamespace]:
        names = tools_by_agent.get(agent or "", [])
        return [SimpleNamespace(name=name) for name in names]

    registry.list_tool_manifests.side_effect = _list
    return registry


def _patch_disabled(capabilities: set[PlatformCapability]) -> object:
    return patch(
        "src.domains.feature_switches.registry.disabled_capabilities",
        AsyncMock(return_value=frozenset(capabilities)),
    )


async def test_the_tools_of_a_disabled_capability_are_excluded() -> None:
    from src.domains.agents.services.planner_capability_filter import (
        tools_hidden_by_capabilities,
    )

    registry = _registry(
        {
            "image_generation_agent": ["generate_image", "edit_image"],
            "browser_agent": ["browser_navigate"],
        }
    )
    with _patch_disabled({PlatformCapability.IMAGE_GENERATION}):
        hidden = await tools_hidden_by_capabilities(registry)

    assert hidden == {"generate_image", "edit_image"}


async def test_several_disabled_capabilities_union_their_tools() -> None:
    from src.domains.agents.services.planner_capability_filter import (
        tools_hidden_by_capabilities,
    )

    registry = _registry(
        {
            "image_generation_agent": ["generate_image"],
            "browser_agent": ["browser_navigate", "browser_click"],
        }
    )
    with _patch_disabled({PlatformCapability.IMAGE_GENERATION, PlatformCapability.BROWSER}):
        hidden = await tools_hidden_by_capabilities(registry)

    assert hidden == {"generate_image", "browser_navigate", "browser_click"}


async def test_nothing_disabled_costs_no_registry_lookup() -> None:
    from src.domains.agents.services.planner_capability_filter import (
        tools_hidden_by_capabilities,
    )

    registry = _registry({"image_generation_agent": ["generate_image"]})
    with _patch_disabled(set()):
        hidden = await tools_hidden_by_capabilities(registry)

    assert hidden == set()
    # The common case must be free: no capability off, no catalogue walk.
    registry.list_tool_manifests.assert_not_called()


async def test_a_capability_without_agents_hides_no_tool() -> None:
    from src.domains.agents.services.planner_capability_filter import (
        tools_hidden_by_capabilities,
    )

    registry = _registry({})
    # Speech is enforced at the route/WebSocket layer; it owns no catalogue
    # entry, so switching it off must not silently blank the catalogue.
    with _patch_disabled({PlatformCapability.STT, PlatformCapability.TTS}):
        hidden = await tools_hidden_by_capabilities(registry)

    assert hidden == set()


async def test_a_failing_switch_read_never_breaks_planning() -> None:
    from src.domains.agents.services.planner_capability_filter import (
        tools_hidden_by_capabilities,
    )

    registry = _registry({"browser_agent": ["browser_navigate"]})
    with patch(
        "src.domains.feature_switches.registry.disabled_capabilities",
        AsyncMock(side_effect=RuntimeError("store down")),
    ):
        hidden = await tools_hidden_by_capabilities(registry)

    # Degrade to the whole product rather than an amputated one: the routes
    # remain the layer that actually refuses.
    assert hidden == set()


def _manifests(*names: str) -> list[SimpleNamespace]:
    return [SimpleNamespace(name=name) for name in names]


async def test_the_turn_catalogue_loses_the_tools_of_a_disabled_capability() -> None:
    from src.domains.agents.services.planner_capability_filter import (
        without_disabled_capability_tools,
    )

    registry = _registry({"image_generation_agent": ["generate_image", "edit_image"]})
    catalogue = _manifests("get_emails_tool", "generate_image", "edit_image", "get_events_tool")
    with _patch_disabled({PlatformCapability.IMAGE_GENERATION}):
        offered = await without_disabled_capability_tools(catalogue, registry)

    # The rest keeps its order: the catalogue order is what the ReAct loop
    # binds in, and what the cross-turn cache depends on (ADR-308).
    assert [manifest.name for manifest in offered] == ["get_emails_tool", "get_events_tool"]


async def test_nothing_hidden_hands_the_same_catalogue_back() -> None:
    from src.domains.agents.services.planner_capability_filter import (
        without_disabled_capability_tools,
    )

    catalogue = _manifests("get_emails_tool", "generate_image")
    with _patch_disabled(set()):
        offered = await without_disabled_capability_tools(catalogue, _registry({}))

    assert offered is catalogue


async def test_a_failing_switch_read_keeps_the_whole_catalogue() -> None:
    from src.domains.agents.services.planner_capability_filter import (
        without_disabled_capability_tools,
    )

    catalogue = _manifests("browser_navigate", "get_emails_tool")
    with patch(
        "src.domains.feature_switches.registry.disabled_capabilities",
        AsyncMock(side_effect=RuntimeError("store down")),
    ):
        offered = await without_disabled_capability_tools(catalogue, _registry({}))

    assert offered is catalogue
