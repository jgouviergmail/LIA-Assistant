"""The router is never offered a domain its turn's catalogue withholds entirely.

The deployment flags gate a few domains, and the turn's catalogue
(``build_turn_catalogue``) withholds the agents of a capability an operator
switched off. The router's menu read the flags alone: with the journal,
document, telephony, browser, web-search or generation switch off, it still
offered that domain, and the planner then planned over nothing. The menu now
reads the same snapshot — the one the request publishes before the graph runs.
"""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import ExitStack
from functools import cache
from unittest.mock import patch

import pytest

from src.core.config import settings
from src.core.context import request_tool_manifests_ctx
from src.domains.agents.registry.catalogue import ToolManifest
from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY, get_routable_domains
from src.domains.agents.registry.semantic_inventory import collect_static_manifests
from src.domains.agents.services.analysis.domain_availability import (
    FLAG_GATED_DOMAINS,
    build_available_domains,
)
from src.domains.feature_switches.registry import PlatformCapability, disabled_agent_names

pytestmark = pytest.mark.unit


@cache
def _catalogue() -> tuple[ToolManifest, ...]:
    """Every native manifest: the catalogue of a turn that withholds nothing."""
    return tuple(collect_static_manifests())


def _capability_domains() -> list[str]:
    """The routable domains whose every agent a capability switch can withhold."""
    switchable = disabled_agent_names(frozenset(PlatformCapability))
    return sorted(
        name
        for name in get_routable_domains()
        if set(DOMAIN_REGISTRY[name].agent_names) <= switchable
    )


def _menu(offered: Sequence[ToolManifest] | None) -> set[str]:
    """The domain menu with every deployment flag on, for a turn offering ``offered``.

    ``None`` is a call outside any turn: no catalogue is published.
    """
    with ExitStack() as stack:
        for flag in FLAG_GATED_DOMAINS.values():
            stack.enter_context(patch.object(settings, flag, True))
        stack.enter_context(
            patch("src.infrastructure.mcp.registration.get_admin_mcp_domains", return_value={})
        )
        if offered is not None:
            token = request_tool_manifests_ctx.set(list(offered))
            stack.callback(request_tool_manifests_ctx.reset, token)
        return {item["name"] for item in build_available_domains()}


def _without_agents(agents: set[str]) -> list[ToolManifest]:
    """The full catalogue minus every tool of ``agents``."""
    return [manifest for manifest in _catalogue() if manifest.agent not in agents]


def test_the_switchable_domains_are_derived_from_the_capability_specs() -> None:
    assert {
        "journal",
        "document",
        "telephony",
        "browser",
        "web_search",
        "image_generation",
        "document_generation",
    } <= set(_capability_domains())


@pytest.mark.parametrize("domain", _capability_domains())
def test_a_capability_domain_follows_its_turn_catalogue(domain: str) -> None:
    agents = set(DOMAIN_REGISTRY[domain].agent_names)

    assert domain in _menu(_catalogue())
    assert domain not in _menu(_without_agents(agents))


def test_a_withheld_domain_takes_no_other_domain_with_it() -> None:
    menu = _menu(_without_agents({"journal_agent"}))

    assert _menu(_catalogue()) - menu == {"journal"}


def test_a_connector_domain_stays_when_no_connector_serves_its_tools() -> None:
    """« No provider is connected » is the honest answer: the domain stays routable."""
    assert "email" in _menu(_without_agents({"email_agent"}))


def test_outside_a_turn_the_deployment_flags_alone_decide() -> None:
    assert request_tool_manifests_ctx.get() is None
    assert set(_capability_domains()) <= _menu(None)
