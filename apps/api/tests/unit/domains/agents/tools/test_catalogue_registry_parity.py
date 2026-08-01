"""Every advertised tool must exist — the catalogue and the registry agree.

The defect this closes, observed in production 2026-07-31: the catalogue
advertised ``get_person_overview_tool`` (manifest registered, ADR-141) while
the registry never imported its module. The planner did exactly the right
thing — it read the catalogue and planned the tool — and the executor then
answered ``Tool 'get_person_overview_tool' not found``. The whole plan failed
and the user was told the assistant could not gather anything.

That is the worst shape of this class of bug: nothing is broken at boot,
nothing is broken at import, and the failure only appears AFTER the planner
has committed — where it reads as "the assistant is incapable", not as a
missing line in a list.

A manifest is a PROMISE to the planner. This test is the promise being kept.
"""

from __future__ import annotations

import pytest

from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.registry.catalogue_loader import initialize_catalogue
from src.domains.agents.tools.tool_registry import _import_tool_modules, get_all_tools

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def advertised_and_registered() -> tuple[set[str], set[str]]:
    """The tool names the catalogue promises, and those the registry holds."""
    registry = AgentRegistry()
    initialize_catalogue(registry)
    advertised = {manifest.name for manifest in registry.list_tool_manifests()}
    # The registry fills as MODULES are imported — exactly what the app does at
    # boot. Reading it without that step measures the test process, not the
    # product (and would flag every tool as missing).
    _import_tool_modules()
    registered = set(get_all_tools())
    return advertised, registered


class TestCatalogueRegistryParity:
    def test_every_advertised_tool_is_registered(
        self, advertised_and_registered: tuple[set[str], set[str]]
    ) -> None:
        """A manifest without an implementation is a trap for the planner."""
        advertised, registered = advertised_and_registered
        missing = sorted(advertised - registered)
        assert not missing, (
            "The catalogue advertises tools the registry does not hold: "
            f"{missing}. The planner WILL select them and the executor WILL "
            "fail with 'Tool not found' — add the module to `tool_modules` in "
            "tools/tool_registry.py, or stop registering the manifest."
        )
