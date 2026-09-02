"""A safety category must be declared, not invented (ADR-256).

``infer_tool_category`` reads LIA's naming conventions (``get_*`` -> search,
``create_*`` -> create...) and, when none applies, returns ``"readonly"``
— the safe-looking default. Measured on the native catalogue: 17 manifests out
of 96 reach it, and four of them WRITE.

Nothing unconfirmed follows: those tools return a HITL draft, and their
manifests say so. What follows is a classification that is wrong in two places
— they become ``initiative_eligible`` (a phase that is meant to be read-only)
and ``tool_is_mutation()`` returns False, so they sit outside the net that
reroutes an unconverged mutation plan to a HITL clarification.

The defect RECURS: ``plan_predicates`` already documents three earlier victims
of the same shape — ``cancel_reminder_tool``, ``edit_image``,
``generate_image`` — each fixed on its own, with nothing stopping the fourth.

Guessing from a CONVENTION is legitimate; inventing an intention is not
(ADR-184's distinction). So the guard demands a declaration only where no
convention applies, and it runs over the loaded catalogue — a guard that runs
before the manifests are registered would validate an empty registry and pass
forever.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from src.domains.agents.orchestration.plan_predicates import tool_is_mutation
from src.domains.agents.registry import agent_registry as registry_module
from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.registry.catalogue import (
    assert_tool_category_completeness,
    get_tool_category,
    infer_tool_category,
    infer_tool_category_or_none,
    is_initiative_eligible,
)
from src.domains.agents.registry.catalogue_loader import initialize_catalogue

pytestmark = [pytest.mark.unit]


@pytest.fixture
def catalogue() -> Iterator[AgentRegistry]:
    """Install a catalogue-populated global registry, then restore the previous one.

    Same save/restore as ``test_tool_mutation_classification`` — the pattern
    exists because the registry is a process-wide singleton. Loading into it
    directly made this suite green alone and RED in the full run: a sibling had
    already registered the same manifests, and ``initialize_catalogue`` refuses
    a duplicate (measured 2026-09-02 under the xdist gate). A private registry
    that is not ALSO installed as the global is not enough either — the
    category lookups read the singleton.
    """
    previous = registry_module._global_registry
    registry = AgentRegistry()
    initialize_catalogue(registry)
    registry_module._global_registry = registry
    try:
        yield registry
    finally:
        registry_module._global_registry = previous


class TestTheConventionStillDecidesWhereItApplies:
    """No behaviour change for the 75 manifests that follow the naming rules."""

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("get_emails_tool", "search"),
            ("search_events_tool", "search"),
            ("list_contacts_tool", "search"),
            ("create_event_tool", "create"),
            ("update_contact_tool", "update"),
            ("delete_file_tool", "delete"),
            ("send_email_tool", "send"),
            ("reply_email_tool", "send"),
            ("get_weather_tool", "readonly"),
        ],
    )
    def test_a_conventional_name_resolves_without_a_declaration(
        self, name: str, expected: str
    ) -> None:
        assert infer_tool_category_or_none(name) == expected
        assert infer_tool_category(name) == expected

    def test_an_unconventional_name_resolves_to_nothing(self) -> None:
        """The distinction the guard is built on."""
        assert infer_tool_category_or_none("write_spreadsheet_tool") is None
        assert infer_tool_category_or_none("frobnicate_the_widget") is None

    def test_the_public_contract_still_falls_back_to_readonly(self) -> None:
        """Third-party MCP tools name themselves however they like; ADR-255 keeps
        the safe default there, since an annotation may only ever TIGHTEN."""
        assert infer_tool_category("mcp_era_billing__cancel_subscription") == "readonly"


class TestTheGuardRefusesAnUndeclaredCategory:
    def test_a_manifest_with_neither_declaration_nor_convention_is_refused(self) -> None:
        class _Manifest:
            name = "frobnicate_the_widget"
            tool_category = None

        with pytest.raises(AssertionError, match="frobnicate_the_widget"):
            assert_tool_category_completeness([_Manifest()])

    def test_a_declared_category_satisfies_the_guard(self) -> None:
        class _Manifest:
            name = "frobnicate_the_widget"
            tool_category = "update"

        assert_tool_category_completeness([_Manifest()])

    def test_a_conventional_name_satisfies_the_guard(self) -> None:
        class _Manifest:
            name = "get_widgets_tool"
            tool_category = None

        assert_tool_category_completeness([_Manifest()])

    def test_the_live_catalogue_passes(self, catalogue: AgentRegistry) -> None:
        """The real assertion: every native manifest is now decided, not guessed."""
        assert_tool_category_completeness(catalogue.list_tool_manifests())

    def test_no_native_manifest_reaches_the_readonly_default(
        self, catalogue: AgentRegistry
    ) -> None:
        undeclared = [
            m.name
            for m in catalogue.list_tool_manifests()
            if m.tool_category is None and infer_tool_category_or_none(m.name) is None
        ]

        assert undeclared == []


class TestTheGuardCannotRefuseAProductionBoot:
    """The guard runs at boot over the catalogue AS LOADED, and the catalogue is
    built behind eight feature flags. A manifest gated OFF in the test
    environment would escape the guard in CI and refuse the boot in production
    — the very defect this guard exists to prevent, pointing the other way.
    """

    FLAGS = (
        "health_metrics_enabled",
        "sub_agents_enabled",
        "image_generation_enabled",
        "document_generation_enabled",
        "devops_enabled",
        "diagnostics_enabled",
        "python_sandbox_tool_enabled",
        "telephony_enabled",
        "peer_connections_enabled",
        "skills_enabled",
        "mcp_enabled",
    )

    def test_every_feature_flag_on_still_boots(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.core.config import settings

        for flag in self.FLAGS:
            if hasattr(settings, flag):
                monkeypatch.setattr(settings, flag, True, raising=False)

        registry = AgentRegistry(checkpointer=None, store=None)
        initialize_catalogue(registry)
        manifests = registry.list_tool_manifests()

        # Guard against a vacuous pass: the flags must actually have loaded more
        # than the default catalogue, or this test proves nothing.
        assert len(manifests) > 96, f"only {len(manifests)} manifests — flags did not take"
        assert_tool_category_completeness(manifests)


class TestTheFourWritersAreNowClassified:
    """The behaviour change, stated tool by tool."""

    @pytest.mark.parametrize(
        "name",
        [
            "write_spreadsheet_tool",
            "append_document_text_tool",
            "set_vacation_responder_tool",
        ],
    )
    def test_a_writing_tool_is_a_mutation(self, catalogue: AgentRegistry, name: str) -> None:
        assert tool_is_mutation(name) is True, "it escaped the unconverged-mutation-plan safety net"

    @pytest.mark.parametrize(
        "name",
        [
            "write_spreadsheet_tool",
            "append_document_text_tool",
            "set_vacation_responder_tool",
            "activate_skill_tool",
        ],
    )
    def test_a_side_effecting_tool_is_not_initiative_eligible(
        self, catalogue: AgentRegistry, name: str
    ) -> None:
        manifest = next(m for m in catalogue.list_tool_manifests() if m.name == name)

        assert (
            is_initiative_eligible(manifest) is False
        ), "the initiative phase performs proactive enrichment and is read-only"


class TestTheReadOnlyOnesAreUnchanged:
    """Twelve of the seventeen declare the value they already had."""

    READERS = [
        "brave_news_tool",
        "brave_search_tool",
        "fetch_web_page_tool",
        "read_document_tool",
        "read_spreadsheet_tool",
        "read_skill_resource",
        "unified_web_search_tool",
        "find_availability_tool",
        "delegate_to_sub_agent_tool",
        "compare_steps_to_baseline_tool",
        "compare_heart_rate_to_baseline_tool",
        "detect_health_changes_tool",
    ]

    @pytest.mark.parametrize("name", READERS)
    def test_a_reader_stays_read_only_and_out_of_the_mutation_net(
        self, catalogue: AgentRegistry, name: str
    ) -> None:
        manifest = next(m for m in catalogue.list_tool_manifests() if m.name == name)

        assert get_tool_category(manifest) in ("readonly", "search")
        assert tool_is_mutation(name) is False

    @pytest.mark.parametrize(
        "name",
        ["read_document_tool", "read_spreadsheet_tool", "find_availability_tool"],
    )
    def test_a_reader_without_an_override_stays_initiative_eligible(
        self, catalogue: AgentRegistry, name: str
    ) -> None:
        """Category-derived eligibility, unchanged by the declaration."""
        manifest = next(m for m in catalogue.list_tool_manifests() if m.name == name)

        assert manifest.initiative_eligible is None, "this test covers the derived path"
        assert is_initiative_eligible(manifest) is True

    @pytest.mark.parametrize(
        "name",
        ["brave_search_tool", "fetch_web_page_tool", "unified_web_search_tool"],
    )
    def test_an_explicit_override_still_wins_over_the_category(
        self, catalogue: AgentRegistry, name: str
    ) -> None:
        """These three already opted OUT of the initiative by hand. Declaring
        their category must not quietly opt them back in."""
        manifest = next(m for m in catalogue.list_tool_manifests() if m.name == name)

        assert manifest.initiative_eligible is False
        assert is_initiative_eligible(manifest) is False
