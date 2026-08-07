"""A disabled capability disappears from what the planner can reach.

Two layers protect a switched-off capability. The routes REFUSE it — that is
the enforcing one. This is the other: the planner must not even be offered
the tools, for three reasons that all matter.

- **Honesty.** A planner that keeps proposing image generation on an instance
  where it is off produces plans that fail at execution, and the user reads a
  refusal instead of an answer.
- **Cost.** Every tool in the catalogue is prompt tokens, on every planning
  call.
- **Reuse over invention.** The exclusion rides on ``exclude_tools``, the
  post-filter that already exists for sub-agent rejection (F6). One mechanism,
  one place to reason about, one place to break.

Failure mode this pins: reading the switches must never take planning down.
An unreachable settings store means "nothing disabled" — the product stays
whole and the routes still refuse what is off.
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


async def test_the_planner_merges_the_hidden_tools_into_its_own_exclusions() -> None:
    """The wiring: capability exclusions ride on the existing F6 post-filter."""
    from src.domains.agents.services.planner_capability_filter import (
        merge_capability_exclusions,
    )

    with patch(
        "src.domains.agents.services.planner_capability_filter.tools_hidden_by_capabilities",
        AsyncMock(return_value={"generate_image"}),
    ):
        merged = await merge_capability_exclusions(MagicMock(), {"delegate_to_sub_agent"})

    # Both survive: a user rejection and an operator switch are independent.
    assert merged == {"delegate_to_sub_agent", "generate_image"}


async def test_merging_with_no_prior_exclusion_returns_only_capability_tools() -> None:
    from src.domains.agents.services.planner_capability_filter import (
        merge_capability_exclusions,
    )

    with patch(
        "src.domains.agents.services.planner_capability_filter.tools_hidden_by_capabilities",
        AsyncMock(return_value={"generate_image"}),
    ):
        merged = await merge_capability_exclusions(MagicMock(), None)

    assert merged == {"generate_image"}


async def test_merging_returns_none_when_there_is_nothing_to_exclude() -> None:
    from src.domains.agents.services.planner_capability_filter import (
        merge_capability_exclusions,
    )

    with patch(
        "src.domains.agents.services.planner_capability_filter.tools_hidden_by_capabilities",
        AsyncMock(return_value=set()),
    ):
        merged = await merge_capability_exclusions(MagicMock(), None)

    # None, not an empty set: the caller's fast path checks truthiness, and an
    # empty set would walk the whole tool list for nothing.
    assert merged is None
