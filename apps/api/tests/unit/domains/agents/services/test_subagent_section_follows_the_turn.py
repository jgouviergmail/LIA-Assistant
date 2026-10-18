"""The planner is told to delegate only when its turn can hold the delegation tool.

The delegation section was gated on the deployment flag alone. With the
operator's switch off, the turn's catalogue withholds
``delegate_to_sub_agent_tool`` (``build_turn_catalogue``) while the prompt still
told the planner when and how to delegate — an instruction toward a tool absent
from its AVAILABLE TOOLS, the contradiction F6 already removed for a rejected
delegation.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import replace

import pytest

from src.core.config import settings
from src.core.constants import TOOL_NAME_DELEGATE_SUB_AGENT
from src.core.context import request_tool_manifests_ctx
from src.domains.agents.registry.catalogue import ToolManifest
from src.domains.agents.services.smart_planner_service import SmartPlannerService
from src.domains.agents.sub_agents.catalogue_manifests import (
    delegate_to_sub_agent_catalogue_manifest,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _delegation_deployed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The deployment ships delegation: what remains to decide is the turn's."""
    monkeypatch.setattr(settings, "sub_agents_enabled", True)


@contextmanager
def _turn(offered: Sequence[ToolManifest]) -> Iterator[None]:
    """Publish the turn's catalogue, as the request does before the graph runs."""
    token = request_tool_manifests_ctx.set(list(offered))
    try:
        yield
    finally:
        request_tool_manifests_ctx.reset(token)


_ANOTHER_TOOL = replace(delegate_to_sub_agent_catalogue_manifest, name="get_event_tool")


class TestTheSectionFollowsTheTurnCatalogue:
    def test_a_turn_that_withholds_the_tool_gets_no_section(self) -> None:
        with _turn([_ANOTHER_TOOL]):
            assert SmartPlannerService._build_sub_agents_section() == ""

    def test_a_turn_that_offers_the_tool_gets_the_section(self) -> None:
        with _turn([_ANOTHER_TOOL, delegate_to_sub_agent_catalogue_manifest]):
            section = SmartPlannerService._build_sub_agents_section()

        assert TOOL_NAME_DELEGATE_SUB_AGENT in section

    def test_outside_a_turn_the_deployment_flag_decides(self) -> None:
        assert request_tool_manifests_ctx.get() is None
        assert TOOL_NAME_DELEGATE_SUB_AGENT in SmartPlannerService._build_sub_agents_section()

    def test_the_deployment_flag_still_withholds_it_from_a_turn_that_offers_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "sub_agents_enabled", False)
        with _turn([delegate_to_sub_agent_catalogue_manifest]):
            assert SmartPlannerService._build_sub_agents_section() == ""
