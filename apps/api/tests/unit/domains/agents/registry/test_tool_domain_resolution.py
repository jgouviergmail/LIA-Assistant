"""A tool's domain is DECLARED by its manifest, not guessed from its name.

Two guards read "which domain does this tool belong to?" and both got it wrong
for the same reason — the answer was derived from the tool NAME:

- ``get_result_key_for_tool`` matched ``browser_task_tool`` on the ``task``
  domain and answered ``tasks`` instead of ``browsers``;
- ``plan_covers_domain`` asked the same function about
  ``place_phone_call_tool``, whose name starts with ``place_``, and concluded a
  phone-call plan covers ``places`` but NOT ``telephony``. So the
  "primary_domain_uncovered" rule — the one that exists to catch a plan that
  drops its own domain — fired on every single-step call request (a false
  positive costing an LLM validation) while staying silent on the two-step
  plan that actually dropped it.

Same doctrine as ``_declared_mutation_flag`` right next door: an explicitly
declared catalogue value WINS over the name heuristic, which stays as the
fallback for tools with no manifest (MCP, skills).
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.agents.orchestration.plan_predicates import plan_covers_domain
from src.domains.agents.registry import reset_global_registry, set_global_registry
from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.registry.catalogue_loader import initialize_catalogue
from src.domains.agents.registry.domain_taxonomy import get_result_key_for_tool

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _global_catalogue() -> Any:
    """Both functions read the GLOBAL registry; give them the real catalogue.

    The telephony manifests are registered explicitly rather than through the
    loader: the loader gates them on ``TELEPHONY_ENABLED``, which is off in the
    test environment, and this test is about how a manifest is READ — not about
    which deployment ships it. Registering the real objects keeps the assertion
    on production data.
    """
    from src.domains.agents.telephony.catalogue_manifests import (
        TELEPHONY_AGENT_MANIFEST,
        place_phone_call_catalogue_manifest,
    )

    registry = AgentRegistry()
    initialize_catalogue(registry)
    registry.register_agent_manifest(TELEPHONY_AGENT_MANIFEST)
    registry.register_tool_manifest(place_phone_call_catalogue_manifest, override=True)
    set_global_registry(registry)
    yield registry
    # Never leak this registry: with telephony registered, later tests
    # would see place_phone_call_tool as a DECLARED mutation.
    reset_global_registry()


class _Step:
    def __init__(self, tool_name: str) -> None:
        self.tool_name = tool_name
        self.step_id = tool_name


class _Plan:
    def __init__(self, *tool_names: str) -> None:
        self.steps = [_Step(name) for name in tool_names]


class TestResultKeyComesFromTheManifest:
    def test_declared_context_key_wins_over_the_name(self) -> None:
        """``browser_task_tool`` produces browsers, whatever its name suggests."""
        assert get_result_key_for_tool("browser_task_tool") == "browsers"

    @pytest.mark.parametrize(
        ("tool_name", "expected"),
        [
            ("get_contacts_tool", "contacts"),
            ("get_emails_tool", "emails"),
            ("get_events_tool", "events"),
            ("get_tasks_tool", "tasks"),
            ("get_files_tool", "files"),
            ("get_places_tool", "places"),
        ],
    )
    def test_unified_read_tools_keep_their_result_key(self, tool_name: str, expected: str) -> None:
        """Non-regression: the tools whose key was already right stay right."""
        assert get_result_key_for_tool(tool_name) == expected

    def test_unknown_tool_still_falls_back_to_the_name(self) -> None:
        """A tool with no manifest (MCP, skill) keeps the heuristic."""
        assert get_result_key_for_tool("some_unregistered_events_tool") == "events"

    def test_unresolvable_name_returns_none(self) -> None:
        assert get_result_key_for_tool("totally_unknown") is None


class TestPlanCoversDomain:
    def test_a_call_plan_covers_telephony(self) -> None:
        """The regression that made the primary-domain rule fire on every call."""
        assert plan_covers_domain(_Plan("place_phone_call_tool"), "telephony") is True

    def test_a_call_plan_does_not_cover_places(self) -> None:
        """It never belonged to the places domain — only its name did."""
        assert plan_covers_domain(_Plan("place_phone_call_tool"), "place") is False

    def test_serves_domains_counts_as_coverage(self) -> None:
        """CRITICAL non-regression: the 360° tool lives in `contact` and SERVES
        `peer` (ADR-191). Resolving by home domain alone would make a
        single-step 360° on a peer look like it dropped its primary domain, and
        send a perfectly good plan back for a replan."""
        assert plan_covers_domain(_Plan("get_person_overview_tool"), "peer") is True
        assert plan_covers_domain(_Plan("get_person_overview_tool"), "contact") is True

    def test_an_unrelated_tool_does_not_cover(self) -> None:
        assert plan_covers_domain(_Plan("get_emails_tool"), "contact") is False

    def test_multi_step_plan_covers_if_any_step_does(self) -> None:
        assert plan_covers_domain(_Plan("get_contacts_tool", "place_phone_call_tool"), "telephony")

    def test_unresolvable_tools_fail_open(self) -> None:
        """No evidence either way must not be read as 'the domain was dropped'.

        A name that resolves to NO domain at all (neither manifest nor
        convention) leaves the check without evidence — unlike ``mcp_*``, which
        the convention legitimately places in the ``mcp`` domain.
        """
        assert plan_covers_domain(_Plan("unregistered_widget"), "telephony") is True

    def test_empty_plan_fails_open(self) -> None:
        assert plan_covers_domain(_Plan(), "telephony") is True
