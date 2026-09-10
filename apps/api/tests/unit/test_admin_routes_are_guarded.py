"""Every served ``/admin`` route asks who is calling, or says why it does not.

ADR-263 paid for this rule once already: a property test that checked admin
routes for ``require_superuser`` passed on two routes where the guard was wired
as a ``Depends``, which FastAPI turns into a required query parameter — both
answered 422 and authorised nothing. The fix was to read an AST **call** rather
than a name. That guard was then scoped to one domain, while the application
serves eighty-eight ``/admin`` routes.

This is the same predicate, applied to every route the API actually serves. It
answers the COVERAGE question — is any admin route unprotected — where
``domains/agents/effects/test_register_routes_wired`` answers the SHAPE
questions on its own domain (the imperative helper used as a dependency, a
phantom query parameter). Two different questions, two guards.

Measured 2026-09-10: 88 admin routes, 5 of them deliberately not superuser-only
and each one verified by reading it. Nothing was unprotected — and until this
file, nothing would have said so the day one was.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
from typing import Any

import pytest

pytestmark = pytest.mark.unit

#: The guard, called imperatively inside the endpoint.
GUARD_CALLS = frozenset({"require_superuser", "raise_admin_required"})

#: The guard, wired as a session dependency.
GUARD_DEPENDENCIES = frozenset(
    {"get_current_superuser_session", "get_current_superuser", "require_admin"}
)

#: Routes whose path says « admin » while the authorisation is legitimately
#: something else. Each entry is a route somebody READ, and the reason says
#: what protects it instead — an exemption with no verified mechanism is a hole
#: with a comment on it.
NOT_SUPERUSER_ONLY: dict[str, str] = {
    "/mcp/admin-servers": (
        "the segment names who PROVISIONED the server, not who may call it: an "
        "admin configures MCP servers globally and each account toggles them "
        "for itself through `users.admin_mcp_disabled_servers`. Session-scoped "
        "(`get_current_active_session`) and read per account."
    ),
    "/mcp/admin-servers/{server_key}/toggle": (
        "the per-account toggle itself — the caller changes their OWN list, "
        "never anybody else's."
    ),
    "/mcp/admin-servers/{server_key}/app/call-tool": (
        "an account calling a server the admin provisioned FOR it: the proxy "
        "refuses a key that account disabled, and refuses any key absent from "
        "the discovered set, so no arbitrary host is reachable."
    ),
    "/mcp/admin-servers/{server_key}/app/read-resource": (
        "the same proxy on the resource side, with the same two refusals: a "
        "key the account disabled, and a key absent from the discovered set."
    ),
    "/usage-limits/admin/ws": (
        "a browser cannot set an Authorization header on a WebSocket handshake, "
        "so this authenticates with a single-use ticket that the superuser-only "
        "`POST /usage-limits/admin/ws/ticket` issues, validated and consumed "
        "BEFORE `accept()`. Same BFF pattern as the voice socket."
    ),
}


def _admin_routes() -> list[Any]:
    """Every served route whose path carries an ``/admin`` segment.

    Read from the router that is actually mounted, never from a hand-kept list:
    a route the guard does not know about is a route it cannot protect.

    Returns:
        The routes, in mount order.
    """
    from src.api.v1.routes import api_router

    return [route for route in api_router.routes if "/admin" in getattr(route, "path", "")]


def _calls_the_guard(endpoint: Any) -> bool:
    """Whether the endpoint's body CALLS the guard.

    A name is not a call: a docstring naming ``require_superuser`` is exactly
    what the two unprotected routes of ADR-263 carried.

    Args:
        endpoint: The route's function.

    Returns:
        True when the source contains a call to one of :data:`GUARD_CALLS`.
    """
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(endpoint)))
    except OSError, TypeError, SyntaxError:  # pragma: no cover - source unavailable
        return False
    return any(
        isinstance(node, ast.Call)
        and getattr(node.func, "id", getattr(node.func, "attr", None)) in GUARD_CALLS
        for node in ast.walk(tree)
    )


def _has_guard_dependency(route: Any) -> bool:
    """Whether the route resolves a superuser session as a dependency.

    Args:
        route: The route.

    Returns:
        True when one of :data:`GUARD_DEPENDENCIES` is in its dependency tree.
    """
    dependant = getattr(route, "dependant", None)
    return any(
        getattr(dependency.call, "__name__", "") in GUARD_DEPENDENCIES
        for dependency in getattr(dependant, "dependencies", [])
    )


def _is_guarded(route: Any) -> bool:
    """Whether anything at all establishes the caller is an administrator."""
    endpoint = getattr(route, "endpoint", None)
    if endpoint is None:  # pragma: no cover - a mount, not an endpoint
        return True
    return _calls_the_guard(endpoint) or _has_guard_dependency(route)


class TestEveryAdminRouteEstablishesWhoIsCalling:
    def test_the_scan_actually_reaches_the_routes(self) -> None:
        """A guard over an empty list is a green that means nothing."""
        routes = _admin_routes()
        assert len(routes) > 50, f"only {len(routes)} admin routes found — the scan is wrong"

    def test_no_admin_route_is_served_without_a_check_or_a_reason(self) -> None:
        unguarded = sorted(
            route.path
            for route in _admin_routes()
            if not _is_guarded(route) and route.path not in NOT_SUPERUSER_ONLY
        )
        assert not unguarded, (
            f"admin routes nothing protects: {unguarded} — call `require_superuser` "
            "in the endpoint, resolve a superuser session, or add the path to "
            "NOT_SUPERUSER_ONLY with the mechanism that protects it instead"
        )

    def test_every_exemption_names_a_mechanism(self) -> None:
        """An exemption with no verified reason is a hole with a comment on it."""
        unexplained = sorted(path for path, why in NOT_SUPERUSER_ONLY.items() if len(why) < 60)
        assert not unexplained, f"exemptions with no stated mechanism: {unexplained}"

    def test_no_exemption_outlives_the_route_it_names(self) -> None:
        """Shrink-only: a path that is gone, or now guarded, leaves the list."""
        served = {route.path: route for route in _admin_routes()}
        stale = sorted(path for path in NOT_SUPERUSER_ONLY if path not in served)
        assert not stale, f"exempted paths that are no longer served: {stale}"
        now_guarded = sorted(path for path in NOT_SUPERUSER_ONLY if _is_guarded(served[path]))
        assert not now_guarded, f"exempted paths that are now guarded — drop them: {now_guarded}"


class TestThePredicateCanActuallyFail:
    """A guard whose own falsification cannot break it is decoration."""

    def test_a_route_that_only_MENTIONS_the_guard_is_not_guarded(self) -> None:
        async def pretender() -> None:
            """Admin only. current_user: must pass require_superuser."""

        assert not _calls_the_guard(pretender)

    def test_a_route_that_CALLS_the_guard_is_seen(self) -> None:
        from src.core.security.authorization import require_superuser

        async def honest(current_user: object = None) -> None:
            require_superuser(current_user, "read")  # type: ignore[arg-type]

        assert _calls_the_guard(honest)
