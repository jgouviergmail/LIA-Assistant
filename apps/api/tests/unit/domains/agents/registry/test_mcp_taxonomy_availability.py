"""Real availability and exact identity precede MCP routing descriptions."""

from dataclasses import replace
from unittest.mock import patch

import pytest

from src.core.context import (
    UserMCPToolsContext,
    admin_mcp_disabled_ctx,
    request_tool_manifests_ctx,
    user_mcp_tools_ctx,
)
from src.domains.agents.registry.domain_taxonomy import (
    auto_generate_server_description,
    collect_all_mcp_domains,
    deduplicate_mcp_slugs,
    filter_admin_mcp_disabled_manifests,
)
from src.domains.agents.services.analysis.domain_availability import build_available_domains
from src.infrastructure.mcp.registration import build_mcp_react_task_manifest

pytestmark = pytest.mark.unit


def _manifest(name: str, domain: str):
    return build_mcp_react_task_manifest(
        name, f"{domain}_agent", "Server", "Declared capability", [], [], hitl_required=False
    )


def test_literal_names_and_generated_suffixes_never_collide() -> None:
    mapping = deduplicate_mcp_slugs(["foo", "foo!", "foo_2"])
    assert len(set(mapping.values())) == 3
    assert mapping["foo"] == "mcp_foo"
    assert mapping["foo_2"] == "mcp_foo_2"


def test_normalization_cannot_reenable_a_disabled_raw_admin_key() -> None:
    manifest = _manifest("mcp_Flights-v2_task", "mcp_flights_v2")
    assert filter_admin_mcp_disabled_manifests([manifest], {"Flights-v2"}) == []
    assert collect_all_mcp_domains({"mcp_flights_v2": "Flights"}, {"Flights-v2"}, None) == []


def test_user_server_without_a_registered_tool_never_becomes_routable() -> None:
    ctx = UserMCPToolsContext()
    ctx.server_domains = {"Healthy": "mcp_healthy", "Failed": "mcp_failed"}
    ctx.tool_manifests = [_manifest("mcp_user_healthy_task", "mcp_healthy")]
    result = collect_all_mcp_domains({}, set(), ctx)
    assert [item["name"] for item in result] == ["mcp_healthy"]


def test_an_explicit_empty_catalogue_never_offers_a_generic_mcp_domain() -> None:
    token = request_tool_manifests_ctx.set([])
    user_token = user_mcp_tools_ctx.set(None)
    disabled_token = admin_mcp_disabled_ctx.set({"Flights-v2"})
    try:
        with patch(
            "src.infrastructure.mcp.registration.get_admin_mcp_domains",
            return_value={"mcp_flights_v2": "Flights"},
        ):
            assert not any(item["name"].startswith("mcp") for item in build_available_domains())
    finally:
        admin_mcp_disabled_ctx.reset(disabled_token)
        user_mcp_tools_ctx.reset(user_token)
        request_tool_manifests_ctx.reset(token)


def test_every_short_capability_including_the_sixth_is_published() -> None:
    descriptions = [
        "Read issues",
        "Find users",
        "List teams",
        "Get labels",
        "Find pages",
        "Create invoices",
    ]
    result = auto_generate_server_description(descriptions, "Business")
    assert all(description in result for description in descriptions)


def test_periods_inside_urls_never_end_a_capability_sentence() -> None:
    result = auto_generate_server_description(
        ["Search https://example.com/report for invoices."], "Search"
    )
    assert "https://example.com/report" in result


def test_exact_admin_identity_does_not_disable_a_colliding_user_server() -> None:
    admin = replace(
        _manifest("mcp_Flights-v2_task", "mcp_flights_v2"),
        mcp_origin="admin",
        mcp_server_key="Flights-v2",
    )
    user = replace(
        _manifest("mcp_user_00110011_task", "mcp_flights_v2_2"),
        mcp_origin="user",
        mcp_server_key="00110011-0011-0011-0011-001100110011",
    )
    assert filter_admin_mcp_disabled_manifests([admin, user], {"Flights-v2"}) == [user]


def test_suffix_allocation_never_reinterprets_a_raw_disabled_admin_key() -> None:
    servers = {"foo": "mcp_foo", "foo!": "mcp_foo_3", "foo_2": "mcp_foo_2"}
    descriptions = {value: key for key, value in servers.items()}
    result = collect_all_mcp_domains(descriptions, {"foo!"}, None, admin_server_domains=servers)
    assert {item["name"] for item in result} == {"mcp_foo", "mcp_foo_2"}


def test_reserved_admin_domains_keep_user_tool_domains_distinct() -> None:
    result = deduplicate_mcp_slugs(["foo", "foo!", "foo_2"], reserved={"mcp_foo", "mcp_foo_2"})
    assert len(set(result.values())) == 3
    assert not set(result.values()).intersection({"mcp_foo", "mcp_foo_2"})


def test_bounded_description_discloses_capabilities_it_cannot_fit() -> None:
    result = auto_generate_server_description(
        [f"Capability {index}" for index in range(100)], "Many"
    )
    assert len(result) <= 400 and "more tools" in result
