"""A declared context type that no tool produces is a trap for the planner.

Two registries describe the same world: ``ContextTypeRegistry`` names the context
keys (``browsers``, ``routes``, ``web_searchs``…) and the tool manifests declare
what an execution actually returns. Nothing kept them in agreement, and the
disagreement is not cosmetic — the analyzer speaks the FIRST vocabulary while
the plan can only satisfy the SECOND.

Production dev, 2026-08-02: "envoie-moi les 3 premiers résultats" set
``for_each_collection_key="browsers"`` — a legitimately declared context type —
while ``browser_task_tool`` returns a single ``content`` string. The validator
demanded an iteration nothing could provide, and the clarification loop that
followed had no exit (ADR-195).

Measured when this guard was written: 5 of the 18 context types had no manifest
producing a collection of that name — ``browsers``, ``health_signals``,
``querys``, ``routes``, ``web_searchs``.

This is a REPORTING guard, not a blocking one: several of those five are
legitimate (a domain may genuinely return one object rather than a list). What
must not happen is the gap growing silently, so the allowlist below is
shrink-only, exactly like the repository's other ratchets.
"""

from __future__ import annotations

import pytest

from src.domains.agents.registry.catalogue import ToolManifest

pytestmark = pytest.mark.unit


#: Context keys with no manifest declaring a collection of the same name, as
#: measured on 2026-08-02. Shrink-only: an entry may leave when its manifest
#: starts declaring the collection, never join without a written reason.
_KNOWN_WITHOUT_A_PRODUCER = frozenset(
    {
        "browsers",  # browser_task_tool returns `content` (a string)
        "health_signals",  # get_health_overview_tool returns `overview` (an object)
        "querys",  # local_query_engine_tool returns `summary_for_llm` (a string)
        "routes",  # get_route_tool returns `route` (an object holding `route.steps`)
        "web_searchs",  # unified_web_search_tool returns its list under `results`
    }
)


def _context_keys(manifests: dict[str, ToolManifest]) -> set[str]:
    """The context keys the MANIFESTS themselves declare.

    Deliberately not ``ContextTypeRegistry.list_all()``: that registry is a
    class-level dict, populated at import time and mutated by any test that
    registers a type of its own — reading it makes this guard pass or fail on
    test ORDER, which is no measurement at all. The manifests are the same
    source ``catalogue_loader`` validates against, and they are stable.
    """
    return {
        manifest.context_key
        for manifest in manifests.values()
        if getattr(manifest, "context_key", None)
    }


def _declared_collections(manifests: dict[str, ToolManifest]) -> set[str]:
    """Root keys of every array output in the catalogue."""
    return {
        output.path.split("[")[0].split(".")[0]
        for manifest in manifests.values()
        for output in manifest.outputs or []
        if output.type == "array"
    }


class TestContextTypesAndManifestsAgree:
    def test_no_new_context_type_lacks_a_producer(self, manifests: dict[str, ToolManifest]) -> None:
        produced = _declared_collections(manifests)
        orphans = _context_keys(manifests) - produced

        assert orphans <= _KNOWN_WITHOUT_A_PRODUCER, (
            f"new context type(s) with no tool producing a collection of that name: "
            f"{sorted(orphans - _KNOWN_WITHOUT_A_PRODUCER)}. The analyzer speaks this "
            f"vocabulary, so a plan can be asked to iterate over something no tool "
            f"returns — see ADR-195. Either declare the collection in the manifest, "
            f"or add the key here with the reason."
        )

    # NOTE: there is deliberately no "an entry that now has a producer must be
    # removed" test. Which tools load depends on feature flags (81 tools under
    # the test settings, 88 in the dev container), so such a check would fail
    # for a reason that says nothing about the catalogue's correctness. The list
    # is reviewed by hand when a manifest starts declaring its collection.

    def test_the_registries_are_actually_loaded(self, manifests: dict[str, ToolManifest]) -> None:
        """Comparing two empty sets would pass while checking nothing."""
        assert len(_context_keys(manifests)) >= 15
        assert len(_declared_collections(manifests)) >= 30
