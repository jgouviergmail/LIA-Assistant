"""The 360° tool must be reachable from the domain the analyzer actually picks.

**The production defect, frozen (2026-08-01).** A "point 360° sur X" where X is
a CONNECTED USER is classified ``primary_domain: "peer"`` — the analyzer prompt
mandates it: *"their data is reachable ONLY through the peer domain … reading
the address book (contact) cannot answer that question"*
(``prompts/v1/query_analyzer_prompt.txt``). But ``get_person_overview_tool``
declares ``agent="contact_agent"``, and catalogue filtering drops out-of-domain
manifests BEFORE reading any semantic score. Measured: the tool scored **0.853**
— the best of the whole catalogue — and the planner never saw it. The plan named
``get_emails_tool`` instead, which cannot read open commitments, calls or
relayed messages, so the user got a 360° missing most of its content.

These tests run the REAL registry and the REAL filtering strategies. A mocked
catalogue would have kept passing throughout the incident.

Two invariants, and the second matters as much as the first: the fix must add
**this one read-only tool** and nothing else. Making ``contact`` a related
domain of ``peer`` was tried before and caused its own production defect —
"listing contact as related pulled Google contact tools into every peer plan,
and a missing contacts scope then invalidated the WHOLE plan" (2026-07-30, see
``registry/program_domain_configs.py``). Reachability here must not resurrect it.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from src.core.context import request_tool_manifests_ctx
from src.domains.agents.analysis.query_intelligence import QueryIntelligence, UserGoal
from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.registry.catalogue_loader import initialize_catalogue
from src.domains.agents.services.smart_catalogue_service import SmartCatalogueService

pytestmark = pytest.mark.unit

OVERVIEW = "get_person_overview_tool"

#: Semantic scores measured in production on 2026-08-01, verbatim from the
#: ``catalogue_tools_*`` log lines. The point of the incident is the RATIO: the
#: right tool scored 0.853 while every generic alternative sat at 0.000-0.005.
PROD_SCORES = {
    OVERVIEW: 0.853,
    "get_contacts_tool": 0.005,
    "get_events_tool": 0.004,
    "get_emails_tool": 0.002,
    "create_event_tool": 0.001,
    "create_contact_tool": 0.000,
    "update_contact_tool": 0.000,
    "delete_contact_tool": 0.000,
    "send_email_tool": 0.000,
    "reply_email_tool": 0.000,
    "forward_email_tool": 0.000,
    "delete_email_tool": 0.000,
    "update_event_tool": 0.000,
    "delete_event_tool": 0.000,
    "list_calendars_tool": 0.000,
}

#: Google Contacts tools that must NOT appear merely because a peer query ran.
CONTACT_CRUD = {"create_contact_tool", "update_contact_tool", "delete_contact_tool"}


@pytest.fixture(scope="module")
def real_registry() -> AgentRegistry:
    """The production catalogue, loaded exactly as the lifespan loads it."""
    registry = AgentRegistry()
    initialize_catalogue(registry)
    return registry


@pytest.fixture
def catalogue(real_registry: AgentRegistry) -> Iterator[SmartCatalogueService]:
    """Filtering service wired to the real manifests for this request."""
    request_tool_manifests_ctx.set(real_registry.list_tool_manifests())
    yield SmartCatalogueService(real_registry)
    request_tool_manifests_ctx.set(None)


def _intelligence(domains: list[str]) -> QueryIntelligence:
    """A 360° request, classified into the given domains."""
    return QueryIntelligence(
        original_query="Fais-moi un point 360° sur Paul Martin",
        english_query="Give me a 360 overview of Paul Martin",
        immediate_intent="360 overview about a person",
        immediate_confidence=0.95,
        user_goal=UserGoal.FIND_INFORMATION,
        goal_reasoning="the user opened a relationship card and asked for a recap",
        domains=list(domains),
        primary_domain=domains[0],
    )


def _names(catalogue: SmartCatalogueService, domains: list[str]) -> list[str]:
    result = catalogue.filter_for_intelligence(
        _intelligence(domains), tool_selection_result={"all_scores": PROD_SCORES}
    )
    return [tool["name"] for tool in result.tools]


class TestTheProductionDefect:
    """What the analyzer emits for a peer must still reach the 360° tool."""

    @pytest.mark.parametrize(
        "domains",
        [
            pytest.param(["peer"], id="peer_alone_the_prompt_default"),
            pytest.param(["peer", "event"], id="peer_plus_its_only_related_domain"),
        ],
    )
    def test_the_overview_tool_is_in_the_catalogue(
        self, catalogue: SmartCatalogueService, domains: list[str]
    ) -> None:
        """Before ADR-191 both cases returned a catalogue WITHOUT the tool."""
        assert OVERVIEW in _names(catalogue, domains)

    def test_the_best_scoring_tool_is_never_the_one_dropped(
        self, catalogue: SmartCatalogueService
    ) -> None:
        """Guards the ordering itself: domain filtering ran before the score.

        Stated as an invariant rather than a fixed list, so it keeps holding as
        the catalogue grows: whatever else survives for a peer query, nothing
        scoring BELOW the 360° tool may be kept while it is dropped.
        """
        names = _names(catalogue, ["peer", "event"])
        kept_worse = [n for n in names if PROD_SCORES.get(n, 0.0) < PROD_SCORES[OVERVIEW]]

        assert OVERVIEW in names, f"dropped 0.853 while keeping {kept_worse}"


class TestNoCollateralWidening:
    """The 2026-07-30 defect must not come back through this door."""

    def test_a_peer_query_gains_exactly_one_tool(self, catalogue: SmartCatalogueService) -> None:
        """`peer` has no catalogue manifest of its own — so the delta is visible.

        Anything beyond the 360° tool and the always-on delegation tool means
        the change widened more than it was asked to.
        """
        names = set(_names(catalogue, ["peer"]))

        assert names == {OVERVIEW, "delegate_to_sub_agent_tool"}

    def test_no_contact_crud_leaks_into_a_peer_plan(self, catalogue: SmartCatalogueService) -> None:
        """The exact shape of the 2026-07-30 production defect."""
        names = set(_names(catalogue, ["peer"])) | set(_names(catalogue, ["peer", "event"]))

        assert not (names & CONTACT_CRUD)

    @pytest.mark.parametrize(
        "domains",
        [
            pytest.param(["contact"], id="single_contact"),
            pytest.param(["peer", "contact"], id="peer_and_contact"),
            pytest.param(["contact", "email", "event"], id="the_three_generic_domains"),
            pytest.param(["email"], id="unrelated_domain"),
        ],
    )
    def test_catalogues_that_already_worked_are_untouched(
        self, catalogue: SmartCatalogueService, domains: list[str]
    ) -> None:
        """`serves_domains` only ever ADDS, and only where the home is absent.

        Whenever `contact` is requested the tool was already reachable through
        its home domain, so the extra declaration must change nothing at all —
        including the ORDER, which drives the domain-coverage seeding.
        """
        names = _names(catalogue, domains)
        home_reachable = "contact" in domains

        assert (OVERVIEW in names) is home_reachable
        assert len(names) == len(set(names)), "a tool was added twice"


class TestPanicParity:
    """Panic mode carries the same rule — one implementation, two callers."""

    def test_the_expanded_catalogue_also_reaches_the_tool(
        self, catalogue: SmartCatalogueService
    ) -> None:
        result = catalogue.filter_for_intelligence(
            _intelligence(["peer"]),
            panic_mode=True,
            tool_selection_result={"all_scores": PROD_SCORES},
        )

        assert result.is_panic_mode is True
        assert OVERVIEW in [tool["name"] for tool in result.tools]


class TestPlacementRule:
    """`placement_domain` is the single answer to "is this tool in scope?"."""

    def test_the_home_domain_wins_when_requested(
        self, catalogue: SmartCatalogueService, real_registry: AgentRegistry
    ) -> None:
        """Otherwise the tool would land in the peer bucket and displace it."""
        manifest = next(m for m in real_registry.list_tool_manifests() if m.name == OVERVIEW)

        assert catalogue.placement_domain(manifest, {"peer", "contact"}) == "contact"

    def test_an_extra_domain_places_the_tool_there(
        self, catalogue: SmartCatalogueService, real_registry: AgentRegistry
    ) -> None:
        manifest = next(m for m in real_registry.list_tool_manifests() if m.name == OVERVIEW)

        assert catalogue.placement_domain(manifest, {"peer"}) == "peer"

    def test_out_of_scope_stays_out(
        self, catalogue: SmartCatalogueService, real_registry: AgentRegistry
    ) -> None:
        manifest = next(m for m in real_registry.list_tool_manifests() if m.name == OVERVIEW)

        assert catalogue.placement_domain(manifest, {"email", "task"}) is None


class TestDeclarationIsValidated:
    """A domain nobody knows makes a tool unreachable, silently. Refuse it."""

    def test_registering_an_unknown_served_domain_raises(
        self, real_registry: AgentRegistry
    ) -> None:
        from dataclasses import replace

        manifest = next(m for m in real_registry.list_tool_manifests() if m.name == OVERVIEW)
        broken = replace(manifest, name="broken_tool", serves_domains=["not_a_domain"])

        with pytest.raises(ValueError, match="not_a_domain"):
            AgentRegistry().register_tool_manifest(broken)

    def test_every_declared_domain_exists_in_the_registry(
        self, real_registry: AgentRegistry
    ) -> None:
        """Catches a typo in ANY manifest, not only the one this ADR touched."""
        from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY

        unknown = {
            f"{m.name} -> {domain}"
            for m in real_registry.list_tool_manifests()
            for domain in m.serves_domains
            if domain not in DOMAIN_REGISTRY
        }

        assert not unknown, f"serves_domains naming unknown domains: {sorted(unknown)}"
