"""An authorization server whose issuer has a path is found where RFC 8414 puts it (2026-11-14).

RFC 8414 §3.1 inserts the well-known name between the host and the issuer's path
(``https://as.example.com/.well-known/oauth-authorization-server/mcp`` for the issuer
``https://as.example.com/mcp``); OpenID Connect inserts or appends its own; RFC 9728 does the same
for a protected resource, read after the host's own document (Asana publishes both). LIA read the
host's root alone, so a vendor publishing as the RFCs say was
refused. Measured 2026-11-14: Stripe's MCP server publishes exactly there, with dynamic
registration and PKCE ``S256``; Strava publishes there too, but announces no PKCE method, which LIA
refuses as the MCP specification requires.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from src.infrastructure.mcp.oauth_flow import (
    MCPOAuthFlowHandler,
    authorization_metadata_urls,
    resource_metadata_urls,
)

pytestmark = pytest.mark.unit

AS_METADATA = {
    "issuer": "https://access.example.com/mcp",
    "authorization_endpoint": "https://access.example.com/mcp/authorize",
    "token_endpoint": "https://access.example.com/mcp/token",
    "registration_endpoint": "https://access.example.com/mcp/register",
    "code_challenge_methods_supported": ["S256"],
}


@pytest.fixture
def handler(monkeypatch: pytest.MonkeyPatch) -> MCPOAuthFlowHandler:
    """A handler whose SSRF guard admits the example hosts (they do not resolve)."""
    monkeypatch.setattr(
        "src.infrastructure.mcp.oauth_flow.validate_http_endpoint",
        AsyncMock(return_value=(True, None)),
    )
    flow = MCPOAuthFlowHandler()
    flow._http_client = AsyncMock(spec=httpx.AsyncClient)
    return flow


def _serve(handler: MCPOAuthFlowHandler, documents: dict[str, dict[str, Any]]) -> list[str]:
    """Answer each URL with its document, every other one with a 404; return the probe order."""
    probed: list[str] = []

    async def get(url: str, **_kwargs: Any) -> Any:
        probed.append(url)
        resp = AsyncMock(spec=httpx.Response)
        if url in documents:
            resp.status_code = 200
            resp.json = lambda: documents[url]
        else:
            resp.status_code = 404
            resp.headers = {}
        return resp

    handler._http_client.get = get
    return probed


class TestWhereTheDocumentsAreRead:
    def test_an_issuer_with_a_path_reads_the_rfc_8414_address_first(self) -> None:
        assert authorization_metadata_urls("https://access.example.com/mcp") == [
            "https://access.example.com/.well-known/oauth-authorization-server/mcp",
            "https://access.example.com/.well-known/openid-configuration/mcp",
            "https://access.example.com/mcp/.well-known/openid-configuration",
            "https://access.example.com/.well-known/oauth-authorization-server",
            "https://access.example.com/.well-known/openid-configuration",
        ]

    @pytest.mark.parametrize("issuer", ["https://auth.example.com", "https://auth.example.com/"])
    def test_an_issuer_without_a_path_reads_the_host_s_documents(self, issuer: str) -> None:
        assert authorization_metadata_urls(issuer) == [
            "https://auth.example.com/.well-known/oauth-authorization-server",
            "https://auth.example.com/.well-known/openid-configuration",
        ]

    def test_a_resource_is_described_by_its_host_then_where_rfc_9728_inserts_its_path(
        self,
    ) -> None:
        """Measured 2026-11-14: Asana publishes both documents for ``…/v2/mcp``, naming two
        authorization servers; the host's one, with dynamic registration, is the one every
        sign-in was made against, so it keeps its precedence and the path's is the fallback."""
        assert resource_metadata_urls("https://mcp.example.com/mcp/") == [
            "https://mcp.example.com/.well-known/oauth-protected-resource",
            "https://mcp.example.com/.well-known/oauth-protected-resource/mcp",
        ]
        assert resource_metadata_urls("https://mcp.example.com") == [
            "https://mcp.example.com/.well-known/oauth-protected-resource",
        ]


class TestAPathIssuerIsFound:
    async def test_where_rfc_8414_inserts_its_path(self, handler: MCPOAuthFlowHandler) -> None:
        address = "https://access.example.com/.well-known/oauth-authorization-server/mcp"
        probed = _serve(handler, {address: AS_METADATA})

        found = await handler._fetch_auth_server_metadata("https://access.example.com/mcp")

        assert found.issuer == "https://access.example.com/mcp"
        assert found.registration_endpoint and found.supports_pkce_s256
        assert probed[0] == address

    @pytest.mark.parametrize(
        "address",
        [
            "https://access.example.com/.well-known/openid-configuration/mcp",
            "https://access.example.com/mcp/.well-known/openid-configuration",
            "https://access.example.com/.well-known/oauth-authorization-server",
        ],
    )
    async def test_where_openid_or_the_host_publishes_it(
        self, handler: MCPOAuthFlowHandler, address: str
    ) -> None:
        _serve(handler, {address: AS_METADATA})

        found = await handler._fetch_auth_server_metadata("https://access.example.com/mcp")

        assert found.authorization_endpoint == "https://access.example.com/mcp/authorize"

    async def test_a_whole_discovery_from_the_resource_to_its_path_issuer(
        self, handler: MCPOAuthFlowHandler
    ) -> None:
        """The shape Stripe serves: the resource's root document names a path issuer."""
        _serve(
            handler,
            {
                "https://mcp.example.com/.well-known/oauth-protected-resource": {
                    "resource": "https://mcp.example.com",
                    "authorization_servers": ["https://access.example.com/mcp"],
                },
                "https://access.example.com/.well-known/oauth-authorization-server/mcp": (
                    AS_METADATA
                ),
            },
        )

        found = await handler.discover_auth_server("https://mcp.example.com")

        assert found.token_endpoint == "https://access.example.com/mcp/token"

    async def test_a_resource_described_only_under_its_path_is_still_found(
        self, handler: MCPOAuthFlowHandler
    ) -> None:
        own = "https://mcp.example.com/.well-known/oauth-protected-resource/mcp"
        probed = _serve(
            handler,
            {
                own: {"authorization_servers": ["https://access.example.com/mcp"]},
                "https://access.example.com/.well-known/oauth-authorization-server/mcp": (
                    AS_METADATA
                ),
            },
        )

        found = await handler.discover_auth_server("https://mcp.example.com/mcp")

        assert found.issuer == "https://access.example.com/mcp"
        assert probed[:2] == [
            "https://mcp.example.com/.well-known/oauth-protected-resource",
            own,
        ]

    async def test_the_host_s_resource_document_keeps_its_precedence(
        self, handler: MCPOAuthFlowHandler
    ) -> None:
        """The Asana shape: two documents, two authorization servers; the host's is read."""
        _serve(
            handler,
            {
                "https://mcp.example.com/.well-known/oauth-protected-resource": {
                    "authorization_servers": ["https://mcp.example.com"]
                },
                "https://mcp.example.com/.well-known/oauth-protected-resource/v2/mcp": {
                    "authorization_servers": ["https://app.example.com"]
                },
                "https://mcp.example.com/.well-known/oauth-authorization-server": {
                    **AS_METADATA,
                    "issuer": "https://mcp.example.com",
                },
            },
        )

        found = await handler.discover_auth_server("https://mcp.example.com/v2/mcp")

        assert found.issuer == "https://mcp.example.com"

    async def test_an_issuer_announcing_no_pkce_is_found_but_never_signed_in_to(
        self, handler: MCPOAuthFlowHandler
    ) -> None:
        """The shape Strava serves: found where RFC 8414 says, but no S256 announced."""
        no_pkce = {k: v for k, v in AS_METADATA.items() if k != "code_challenge_methods_supported"}
        _serve(
            handler,
            {"https://access.example.com/.well-known/oauth-authorization-server/mcp": no_pkce},
        )

        found = await handler._fetch_auth_server_metadata("https://access.example.com/mcp")

        assert not found.supports_pkce_s256
