"""Offline corpus/scorer contracts; these tests are not evidence of model decisions."""

import pytest

from scripts.semantic_simulation.taxonomy_corpus import (
    TAXONOMY_CASES,
    TAXONOMY_EXEMPTIONS,
    TaxonomyRoutingCase,
    assess_routing,
)
from src.core.constants import SUPPORTED_LANGUAGES
from src.domains.agents.registry.domain_exemptions import is_platform_domain
from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY

pytestmark = pytest.mark.unit


def _case(name: str) -> TaxonomyRoutingCase:
    return next(case for case in TAXONOMY_CASES if case.name == name)


def test_real_probe_corpus_is_bounded_and_names_and_requests_are_unique() -> None:
    assert 0 < len(TAXONOMY_CASES) <= 49  # One explicit additional native SMS routing probe.
    assert len({case.name for case in TAXONOMY_CASES}) == len(TAXONOMY_CASES)
    assert len({case.query for case in TAXONOMY_CASES}) == len(TAXONOMY_CASES)


def test_each_native_routable_domain_has_an_independent_explicit_single_domain_case() -> None:
    singles = {
        case.required_domains[0]
        for case in TAXONOMY_CASES
        if case.menu_variant == "native" and len(case.required_domains) == 1
    }
    routable = {
        name
        for name, config in DOMAIN_REGISTRY.items()
        if config.is_routable and not config.metadata.get("dynamic")
    }
    assert singles == routable
    # A NEW internal or dynamic entry must also receive a conscious exclusion;
    # selecting only routable entries above must not hide taxonomy drift.
    assert set(DOMAIN_REGISTRY) - singles == set(TAXONOMY_EXEMPTIONS) - {"python"}


def test_exemptions_are_narrow_explained_and_still_legitimate() -> None:
    assert all(TAXONOMY_EXEMPTIONS.values())
    for name in TAXONOMY_EXEMPTIONS:
        if name in DOMAIN_REGISTRY:
            config = DOMAIN_REGISTRY[name]
            assert not config.is_routable or config.metadata.get("dynamic")
        else:
            assert is_platform_domain(name)


def test_case_domains_are_known_and_cover_the_six_actual_languages() -> None:
    assert {case.language for case in TAXONOMY_CASES} == set(SUPPORTED_LANGUAGES)
    for case in TAXONOMY_CASES:
        if case.menu_variant == "native":
            assert set(case.required_domains) | set(case.acceptable_domains) <= set(DOMAIN_REGISTRY)
        assert set(case.required_domains).isdisjoint(case.acceptable_domains)
        if case.expected_primary is not None:
            assert case.expected_primary in case.required_domains


@pytest.mark.parametrize(
    ("name", "domains", "mutation"),
    [
        ("chain_contact_to_email", {"contact", "email"}, True),
        ("chain_event_to_weather", {"event", "weather"}, False),
        ("chain_event_to_route", {"event", "route"}, False),
        ("distinguish_uploaded_documents_and_drive", {"document", "file"}, False),
        ("distinguish_memory_and_lia_journal", {"memory", "journal"}, False),
        ("distinguish_reminder_task_and_automation", {"reminder", "task", "automation"}, True),
    ],
)
def test_multi_domain_business_expectations_do_not_collapse_distinct_requests(
    name: str,
    domains: set[str],
    mutation: bool,
) -> None:
    case = _case(name)
    assert set(case.required_domains) == domains
    assert case.expected_mutation is mutation
    assert case.acceptable_domains == ()


def test_mcp_fixture_names_and_menu_variants_are_explicit() -> None:
    cases = {case.menu_variant: case for case in TAXONOMY_CASES if case.menu_variant != "native"}
    assert set(cases) == {"user_mcp", "admin_mcp", "disabled_mcp", "user_mcp_iterative"}
    assert cases["user_mcp"].required_domains == ("mcp_archives_atlas",)
    assert cases["admin_mcp"].required_domains == ("mcp_catalogue_polaris",)
    assert cases["user_mcp_iterative"].required_domains == ("mcp_canvas_orion",)
    assert cases["user_mcp_iterative"].expected_mutation
    assert cases["disabled_mcp"].required_domains == ("contact",)
    assert not cases["disabled_mcp"].expected_mutation


@pytest.mark.parametrize(
    ("name", "primary", "secondary", "mutation", "failure"),
    [
        ("chain_contact_to_email", "email", (), True, "missing_domains:contact"),
        ("native_contact_directory", "contact", ("task",), False, "unwanted_domains:task"),
        ("native_saved_setting", "contact", ("setting",), False, "primary_domain:contact"),
        ("native_health_steps", "health", (), True, "mutation_intent:True"),
        ("native_outbound_call", "telephony", (), False, "mutation_intent:False"),
        (
            "distinguish_memory_and_lia_journal",
            None,
            ("memory", "journal"),
            False,
            "missing_primary_domain",
        ),
        (
            "disabled_mcp_does_not_capture_native_request",
            "contact",
            ("mcp_archives_atlas",),
            False,
            "unwanted_domains:mcp_archives_atlas",
        ),
    ],
)
def test_scorer_rejects_missing_or_unwanted_scope_and_false_mutation_claims(
    name: str,
    primary: str | None,
    secondary: tuple[str, ...],
    mutation: bool,
    failure: str,
) -> None:
    assert failure in assess_routing(
        _case(name),
        primary_domain=primary,
        secondary_domains=secondary,
        is_mutation_intent=mutation,
    )


def test_only_explicit_optional_source_domains_are_admitted_as_extras() -> None:
    case = _case("native_multi_source_web_search")
    assert (
        assess_routing(
            case,
            primary_domain="web_search",
            secondary_domains=("brave", "wikipedia"),
            is_mutation_intent=False,
        )
        == ()
    )
    assert "unwanted_domains:email" in assess_routing(
        case,
        primary_domain="web_search",
        secondary_domains=("brave", "email"),
        is_mutation_intent=False,
    )


def test_optional_primary_keeps_multi_result_order_flexible_but_requires_every_source() -> None:
    case = _case("distinguish_uploaded_documents_and_drive")
    for primary, secondary in (("file", "document"), ("document", "file")):
        assert (
            assess_routing(
                case,
                primary_domain=primary,
                secondary_domains=(secondary,),
                is_mutation_intent=False,
            )
            == ()
        )


def test_homonymous_city_and_person_requests_have_independent_source_expectations() -> None:
    assert _case("nancy_explicit_city").required_domains == ("weather",)
    assert _case("nancy_contact_home").required_domains == ("contact", "weather")
    assert "unwanted_domains:contact" in assess_routing(
        _case("nancy_explicit_city"),
        primary_domain="weather",
        secondary_domains=("contact",),
        is_mutation_intent=False,
    )
    assert "missing_domains:contact" in assess_routing(
        _case("nancy_contact_home"),
        primary_domain="weather",
        secondary_domains=(),
        is_mutation_intent=False,
    )
