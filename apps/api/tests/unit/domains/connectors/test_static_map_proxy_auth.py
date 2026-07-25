"""The Google Static Maps proxies must not be reachable anonymously (FN-5).

Each proxied call is a **billed** Google Static Maps request made with the
server's API key. Both endpoints were public, justified by a comment claiming
that "browser <img> tags don't send session cookies". That is not true here: the
URL handed to the browser is relative (built in ``routes_tools`` /
``places_tools``), so it resolves against the frontend origin, the session cookie
is attached, and Next's ``/api/v1/:path*`` rewrite forwards it — which is exactly
how the already-authenticated ``profile-image-proxy`` renders avatars today.

Left open, anyone on the internet could loop on these endpoints and burn the
Google quota (OWASP API4 — Unrestricted Resource Consumption).

These tests assert the FastAPI contract (auth is declared on both routes) rather
than driving a browser: the browser-side behaviour is a web-platform guarantee,
and it is already demonstrated in production by the avatar proxy.
"""

from __future__ import annotations

import inspect

import pytest

from src.core.session_dependencies import get_current_active_session
from src.domains.connectors.router import (
    proxy_location_static_map,
    proxy_routes_static_map,
    rate_limit_static_map,
    router,
)

_STATIC_MAP_PATHS = {
    "/connectors/google-routes/static-map",
    "/connectors/google-location/static-map",
}


def _dependency_callables(endpoint) -> list:
    """Return the dependency callables declared in an endpoint's signature.

    Args:
        endpoint: The route handler function.

    Returns:
        The ``Depends(...)`` dependencies attached to its parameters.
    """
    return [
        param.default.dependency
        for param in inspect.signature(endpoint).parameters.values()
        if hasattr(param.default, "dependency")
    ]


class TestStaticMapProxiesRequireAuthentication:
    """Both proxies must declare the session dependency."""

    @pytest.mark.parametrize(
        "endpoint",
        [proxy_routes_static_map, proxy_location_static_map],
        ids=["routes", "location"],
    )
    def test_endpoint_declares_session_dependency(self, endpoint):
        """An anonymous caller cannot reach the billed Google request."""
        assert get_current_active_session in _dependency_callables(endpoint), (
            f"{endpoint.__name__} must depend on get_current_active_session — "
            "without it the endpoint spends the Google quota for anyone."
        )

    @pytest.mark.parametrize(
        "endpoint",
        [proxy_routes_static_map, proxy_location_static_map],
        ids=["routes", "location"],
    )
    def test_endpoint_declares_rate_limit(self, endpoint):
        """Defence in depth: a compromised session cannot loop unbounded."""
        assert rate_limit_static_map in _dependency_callables(
            endpoint
        ), f"{endpoint.__name__} must depend on the per-user static-map rate limit."

    def test_both_routes_are_registered(self):
        """Guard against a rename silently dropping these routes from the audit."""
        registered = {route.path for route in router.routes if hasattr(route, "path")}
        assert (
            _STATIC_MAP_PATHS <= registered
        ), f"missing static-map routes: {_STATIC_MAP_PATHS - registered}"


class TestStaticMapProxiesKeepTheirContract:
    """The hardening must not change what the cards already stored expect."""

    @pytest.mark.parametrize(
        ("endpoint", "expected"),
        [
            (proxy_routes_static_map, {"polyline", "width", "height", "origin", "dest"}),
            (proxy_location_static_map, {"lat", "lng", "width", "height", "zoom"}),
        ],
        ids=["routes", "location"],
    )
    def test_query_parameters_are_unchanged(self, endpoint, expected):
        """Query parameters stay identical, so history URLs keep resolving.

        Static-map URLs are persisted inside registry items, so a conversation
        opened months later replays the exact same query string. Renaming or
        dropping a parameter would break those cards retroactively — the reason
        a signature-based scheme was rejected for this endpoint.
        """
        params = set(inspect.signature(endpoint).parameters)
        assert expected <= params, f"missing/renamed query params: {expected - params}"
