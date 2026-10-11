"""Full production menu fixtures and prompt boundaries, without provider calls."""

from contextlib import ExitStack, nullcontext
from unittest.mock import MagicMock, patch

import pytest

from scripts.semantic_simulation import taxonomy_fixtures, taxonomy_run
from scripts.semantic_simulation.taxonomy_corpus import TAXONOMY_CASES, MenuVariant
from scripts.semantic_simulation.taxonomy_fixtures import full_domain_menu
from src.core.config import settings
from src.core.context import (
    UserMCPToolsContext,
    admin_mcp_disabled_ctx,
    request_tool_manifests_ctx,
    user_mcp_tools_ctx,
)
from src.domains.agents.registry.catalogue import ToolManifest
from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY
from src.domains.agents.registry.semantic_inventory import collect_static_manifests
from src.domains.agents.services.analysis.domain_availability import (
    FLAG_GATED_DOMAINS,
    build_available_domains,
)
from src.infrastructure.mcp import registration

pytestmark = pytest.mark.unit

VARIANTS: tuple[MenuVariant, ...] = (
    "native",
    "user_mcp",
    "admin_mcp",
    "disabled_mcp",
    "user_mcp_iterative",
)
EXPECTED_MCP_DOMAINS: dict[MenuVariant, set[str]] = {
    "native": set(),
    "user_mcp": {"mcp_archives_atlas"},
    "admin_mcp": {"mcp_catalogue_polaris"},
    "disabled_mcp": set(),
    "user_mcp_iterative": {"mcp_canvas_orion"},
}


def _native_names() -> set[str]:
    return {
        name
        for name, config in DOMAIN_REGISTRY.items()
        if config.is_routable and not config.metadata.get("dynamic")
    }


def _names(menu: list[dict[str, str]]) -> set[str]:
    return {item["name"] for item in menu}


def _mcp_manifests() -> list[ToolManifest]:
    offered = request_tool_manifests_ctx.get()
    assert offered is not None
    return [manifest for manifest in offered if manifest.mcp_origin is not None]


@pytest.mark.parametrize("variant", VARIANTS)
def test_every_menu_keeps_all_native_domains_and_only_the_available_mcp_fixture(
    variant: MenuVariant,
) -> None:
    native_tools = {manifest.name for manifest in collect_static_manifests()}
    with ExitStack() as stack:
        # The fixture must enable every declared deployment flag itself and
        # restore it afterwards; a permissive inherited setting cannot mask it.
        for flag in FLAG_GATED_DOMAINS.values():
            stack.enter_context(patch.object(settings, flag, False))
        with full_domain_menu(variant) as menu:
            names = _names(menu)
            assert names == _native_names() | EXPECTED_MCP_DOMAINS[variant]
            assert len(menu) == len(names)
            assert all(
                set(item) == {"name", "description"} and item["description"] for item in menu
            )
            assert {"context", "query", "sub_agent", "python", "mcp"}.isdisjoint(names)
            offered = request_tool_manifests_ctx.get()
            assert offered is not None
            assert native_tools <= {manifest.name for manifest in offered}
            assert all(getattr(settings, flag) for flag in FLAG_GATED_DOMAINS.values())
        assert all(not getattr(settings, flag) for flag in FLAG_GATED_DOMAINS.values())


@pytest.mark.parametrize(
    ("variant", "domain", "origin", "key", "delegates"),
    [
        ("user_mcp", "mcp_archives_atlas", "user", "00000001-0000-0000-0000-000000000001", False),
        ("admin_mcp", "mcp_catalogue_polaris", "admin", "Catalogue Polaris", False),
        (
            "user_mcp_iterative",
            "mcp_canvas_orion",
            "user",
            "00000001-0000-0000-0000-000000000001",
            True,
        ),
    ],
)
def test_mcp_origins_keep_exact_configuration_keys_and_live_bound_manifests(
    variant: MenuVariant,
    domain: str,
    origin: str,
    key: str,
    delegates: bool,
) -> None:
    with full_domain_menu(variant) as menu:
        manifests = _mcp_manifests()
        assert len(manifests) == 1
        manifest = manifests[0]
        assert manifest.agent == f"{domain}_agent"
        assert manifest.mcp_origin == origin
        assert manifest.mcp_server_key == key
        assert manifest.mcp_server_key != domain
        assert manifest.delegates_execution is delegates
        assert domain in _names(menu)
        if origin == "user":
            context = user_mcp_tools_ctx.get()
            assert context is not None
            assert context.tool_manifests == manifests
            assert set(context.server_domains.values()) == {domain}
            assert set(context.server_description_sources.values()) == {"discovered"}
            assert len(context.server_catalogue_fingerprints) == 1
        else:
            assert user_mcp_tools_ctx.get() is None
            assert registration.get_admin_mcp_server_domains() == {key: domain}


def test_disabled_admin_description_cannot_publish_a_server_without_usable_tools() -> None:
    with full_domain_menu("disabled_mcp") as menu:
        assert "mcp_archives_atlas" in registration.get_admin_mcp_domains()
        assert registration.get_admin_mcp_server_domains() == {
            "Archives Atlas": "mcp_archives_atlas"
        }
        assert admin_mcp_disabled_ctx.get() == {"Archives Atlas"}
        assert _mcp_manifests() == []
        assert _names(menu) == _native_names()


def test_disabled_raw_admin_key_filters_an_opaque_domain_even_with_a_bound_manifest() -> None:
    with full_domain_menu("disabled_mcp"):
        manifest = registration.build_mcp_tool_manifest(
            adapter_name="mcp_opaque_archive_read_record",
            agent_name="mcp_opaque_archive_agent",
            tool_name="read_record",
            description="Read fictional archive records",
            input_schema={"type": "object", "properties": {}},
            semantic_keywords=[],
            hitl_required=False,
            annotations={"readOnlyHint": True},
            mcp_origin="admin",
            mcp_server_key="Archives Atlas",
        )
        offered = request_tool_manifests_ctx.get()
        assert offered is not None
        token = request_tool_manifests_ctx.set([*offered, manifest])
        try:
            with (
                patch.object(
                    registration,
                    "get_admin_mcp_domains",
                    return_value={"mcp_opaque_archive": "Read archives"},
                ),
                patch.object(
                    registration,
                    "get_admin_mcp_server_domains",
                    return_value={"Archives Atlas": "mcp_opaque_archive"},
                ),
            ):
                assert _names(build_available_domains()) == _native_names()
        finally:
            request_tool_manifests_ctx.reset(token)


def test_disabling_a_namesake_admin_server_does_not_hide_user_owned_tools() -> None:
    with full_domain_menu("user_mcp"):
        token = admin_mcp_disabled_ctx.set({"Archives Atlas"})
        try:
            assert _names(build_available_domains()) == _native_names() | {"mcp_archives_atlas"}
            assert _mcp_manifests()[0].mcp_origin == "user"
        finally:
            admin_mcp_disabled_ctx.reset(token)


@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize("consumer_raises", [False, True])
def test_fixture_restores_the_exact_outer_request_objects_and_flags(
    variant: MenuVariant,
    consumer_raises: bool,
) -> None:
    outer_user = UserMCPToolsContext(server_domains={"Prior user server": "mcp_prior"})
    outer_disabled = {"Prior raw admin key"}
    outer_offered: list[ToolManifest] = []
    original_flags = {flag: getattr(settings, flag) for flag in FLAG_GATED_DOMAINS.values()}
    tokens = (
        user_mcp_tools_ctx.set(outer_user),
        admin_mcp_disabled_ctx.set(outer_disabled),
        request_tool_manifests_ctx.set(outer_offered),
    )
    try:
        expectation = (
            pytest.raises(RuntimeError, match="fixture consumer")
            if consumer_raises
            else nullcontext()
        )
        with expectation:
            with full_domain_menu(variant) as menu:
                assert "mcp_prior" not in _names(menu)
                assert request_tool_manifests_ctx.get() is not outer_offered
                assert admin_mcp_disabled_ctx.get() is not outer_disabled
                if consumer_raises:
                    raise RuntimeError("fixture consumer")
        assert user_mcp_tools_ctx.get() is outer_user
        assert admin_mcp_disabled_ctx.get() is outer_disabled
        assert request_tool_manifests_ctx.get() is outer_offered
        assert outer_user.server_domains == {"Prior user server": "mcp_prior"}
        assert outer_disabled == {"Prior raw admin key"}
        assert outer_offered == []
        assert {flag: getattr(settings, flag) for flag in original_flags} == original_flags
    finally:
        request_tool_manifests_ctx.reset(tokens[2])
        admin_mcp_disabled_ctx.reset(tokens[1])
        user_mcp_tools_ctx.reset(tokens[0])


def test_fixture_restores_request_context_when_the_menu_builder_fails_before_yield() -> None:
    outer_user = user_mcp_tools_ctx.get()
    outer_disabled = admin_mcp_disabled_ctx.get()
    outer_offered = request_tool_manifests_ctx.get()
    original_flags = {flag: getattr(settings, flag) for flag in FLAG_GATED_DOMAINS.values()}
    with patch.object(
        taxonomy_fixtures, "build_available_domains", side_effect=RuntimeError("builder failure")
    ):
        with pytest.raises(RuntimeError, match="builder failure"):
            with full_domain_menu("user_mcp"):
                pytest.fail("Failed construction must not yield a menu")
    assert user_mcp_tools_ctx.get() is outer_user
    assert admin_mcp_disabled_ctx.get() is outer_disabled
    assert request_tool_manifests_ctx.get() is outer_offered
    assert {flag: getattr(settings, flag) for flag in original_flags} == original_flags


@pytest.mark.parametrize(
    "case_name",
    [
        "native_city_weather",
        "native_saved_setting",
        "english_image_editing",
        "chinese_peer_connections",
    ],
)
def test_prompt_keeps_the_complete_menu_for_disjoint_cases_and_languages(
    case_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    forbidden = MagicMock(side_effect=AssertionError("Prompt construction cannot call a model"))
    monkeypatch.setattr(taxonomy_run, "invoke", forbidden)
    case = next(item for item in TAXONOMY_CASES if item.name == case_name)
    with full_domain_menu(case.menu_variant) as menu:
        prompt = taxonomy_run._prompt(case, menu)
        assert case.query in prompt
        assert all(f"- **{domain}**:" in prompt for domain in _native_names())
        assert len(menu) > len(case.required_domains) + len(case.acceptable_domains)
    forbidden.assert_not_called()
