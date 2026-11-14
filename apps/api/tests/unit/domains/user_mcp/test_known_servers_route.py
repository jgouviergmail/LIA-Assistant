"""The known servers are published where the personal servers are — and closed with them."""

from __future__ import annotations

import pytest

from src.domains.feature_switches.registry import PlatformCapability
from src.domains.user_mcp.router import list_known_servers, router
from src.infrastructure.mcp.known_servers import KNOWN_MCP_SERVERS
from tests._routes import capabilities_closing, served_routes

pytestmark = pytest.mark.unit


async def test_the_route_publishes_the_whole_catalogue_in_its_order() -> None:
    published = await list_known_servers()

    assert [server.key for server in published.servers] == [
        server.key for server in KNOWN_MCP_SERVERS
    ]
    for served, declared in zip(published.servers, KNOWN_MCP_SERVERS, strict=True):
        assert (
            served.name,
            served.url,
            served.auth_type.value,
            served.domain_description,
            served.icon,
            served.header_name,
            served.oauth_scopes,
            served.own_oauth_client,
        ) == (
            declared.name,
            declared.url,
            declared.auth_type,
            declared.domain_description,
            declared.icon,
            declared.header_name,
            declared.oauth_scopes,
            declared.own_oauth_client,
        )


async def test_it_publishes_the_callback_a_person_declares_in_their_own_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.core.config import settings
    from src.core.constants import MCP_USER_OAUTH_CALLBACK_PATH

    monkeypatch.setattr(settings, "mcp_user_oauth_callback_base_url", "https://lia.example")

    published = await list_known_servers()

    # The address the OAuth flow sends, through the same door: one fact, one reader.
    assert published.oauth_redirect_uri == f"https://lia.example{MCP_USER_OAUTH_CALLBACK_PATH}"


async def test_with_oauth_unconfigured_it_publishes_no_callback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.core.config import settings

    monkeypatch.setattr(settings, "mcp_user_oauth_callback_base_url", None)

    assert (await list_known_servers()).oauth_redirect_uri is None


def test_it_is_served_under_the_personal_servers_and_closed_by_their_switch() -> None:
    known = [
        route
        for route in served_routes(router)
        if route.path == "/mcp/servers/known" and "GET" in (route.methods or ())
    ]

    assert len(known) == 1
    assert PlatformCapability.MCP.value in capabilities_closing(known[0])


def test_it_is_matched_before_any_route_that_reads_a_server_id() -> None:
    # « known » is not a server id: declared after a `/{server_id}` GET, it would be
    # read as one the day such a route exists.
    paths = [route.path for route in served_routes(router) if "GET" in (route.methods or ())]
    with_id = [index for index, path in enumerate(paths) if "{server_id}" in path]

    assert paths.index("/mcp/servers/known") < min(with_id)
