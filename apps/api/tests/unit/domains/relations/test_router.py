"""Relations router — favorites write surface (delegation + idempotent 204).

The read endpoints are covered through the service tests; what the router
adds is the favorites star: both verbs must delegate the RAW name (the
service owns the folding) and answer 204 with no body.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.relations.overview_scope import OverviewSection, RelationOverviewScope
from src.domains.relations.router import (
    add_relation_favorite,
    get_overview_scope,
    get_relation_context,
    remove_relation_favorite,
    router,
    set_overview_scope,
)


def _user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid4())


@pytest.mark.unit
class TestFavoritesEndpoints:
    async def test_put_delegates_raw_name_and_answers_204(self) -> None:
        service = MagicMock(add_favorite=AsyncMock())
        user = _user()
        with patch("src.domains.relations.router.RelationsService", return_value=service) as ctor:
            response = await add_relation_favorite(name="Mémé Jeanne", current_user=user)
        ctor.assert_called_once_with(user.id)
        service.add_favorite.assert_awaited_once_with("Mémé Jeanne")
        assert response.status_code == 204

    async def test_delete_delegates_and_answers_204_even_when_absent(self) -> None:
        service = MagicMock(remove_favorite=AsyncMock(return_value=False))
        with patch("src.domains.relations.router.RelationsService", return_value=service):
            response = await remove_relation_favorite(
                name="Personne Inconnue", current_user=_user()
            )
        service.remove_favorite.assert_awaited_once_with("Personne Inconnue")
        assert response.status_code == 204


@pytest.mark.unit
class TestContextEndpoint:
    """The provider sections live on their OWN endpoint (Bloc C).

    Separate from the 360° detail on purpose: it reaches the connectors, so it
    is slower and fails differently — the detail must never wait for it.
    """

    async def test_delegates_the_raw_name_to_the_context_service(self) -> None:
        context = MagicMock()
        service = MagicMock(build=AsyncMock(return_value=context))
        user = _user()
        with patch(
            "src.domains.relations.router.RelationContextService", return_value=service
        ) as ctor:
            result = await get_relation_context(
                name="Gérard Dupont", refresh=None, current_user=user
            )
        ctor.assert_called_once_with(user.id)
        service.build.assert_awaited_once_with("Gérard Dupont", refresh=frozenset())
        assert result is context

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("contact", {"contact"}),
            ("emails,events", {"emails", "events"}),
            (" contact , emails ", {"contact", "emails"}),
            ("", set()),
            (",,", set()),
            ("contact,inconnue", {"contact", "inconnue"}),
        ],
    )
    async def test_the_refresh_list_is_parsed_leniently(self, raw, expected) -> None:
        """A cache bypass is not a command surface: an unknown or malformed
        section name is ignored downstream, never turned into a 4xx on a READ."""
        service = MagicMock(build=AsyncMock(return_value=MagicMock()))
        with patch("src.domains.relations.router.RelationContextService", return_value=service):
            await get_relation_context(name="X", refresh=raw, current_user=_user())
        assert service.build.await_args.kwargs["refresh"] == frozenset(expected)


@pytest.mark.unit
class TestRouteTable:
    """The specific routes must beat the `/{name}` catch-all by literal match."""

    def test_favorites_paths_declared(self) -> None:
        paths = {(route.path, tuple(sorted(route.methods))) for route in router.routes}
        assert ("/relations/favorites/{name}", ("DELETE",)) in paths
        assert ("/relations/favorites/{name}", ("PUT",)) in paths

    def test_the_context_route_is_rate_limited(self) -> None:
        """It spends EXTERNAL quota — up to 1 + 2×addresses + 1 API calls —
        and every distinct name is its own cache entry, so the cache cannot
        bound a caller walking through names."""
        context_route = next(
            route for route in router.routes if route.path == "/relations/{name}/context"
        )
        guards = {
            getattr(dependency.call, "__name__", "")
            for dependency in context_route.dependant.dependencies
        }
        assert "rate_limit_dependency" in guards

    def test_the_database_local_reads_are_not_rate_limited(self) -> None:
        """The overview and the detail are indexed queries on our own database:
        a budget there would only punish a user for browsing their own data."""
        for path in ("/relations", "/relations/{name}"):
            route = next(candidate for candidate in router.routes if candidate.path == path)
            guards = {
                getattr(dependency.call, "__name__", "")
                for dependency in route.dependant.dependencies
            }
            assert "rate_limit_dependency" not in guards

    def test_context_is_declared_before_the_catch_all(self) -> None:
        """Starlette matches in declaration order: `/{name}` declared first
        would swallow `/{name}/context`… and answer with the wrong payload."""
        paths = [route.path for route in router.routes]
        assert "/relations/{name}/context" in paths
        assert paths.index("/relations/{name}/context") < paths.index("/relations/{name}")

    def test_the_scope_routes_are_declared_before_the_catch_all(self) -> None:
        """Same hazard, worse symptom: `/{name}` would match "overview-scope"
        as a PERSON and answer a RelationDetail where a scope is expected."""
        paths = [route.path for route in router.routes]
        assert paths.index("/relations/overview-scope") < paths.index("/relations/{name}")


@pytest.mark.unit
class TestOverviewScopeEndpoints:
    """The scope is written BEFORE the chat opens — that is the whole point.

    The `?intent=` carries prose, so the tool reads this. An endpoint that
    silently dropped or reshaped the selection would turn a guarantee back
    into a hint.
    """

    async def test_get_delegates_to_the_service(self) -> None:
        scope = RelationOverviewScope(sections=[OverviewSection.EMAILS], max_items=3)
        service = MagicMock(get_overview_scope=AsyncMock(return_value=scope))
        user = _user()
        with patch("src.domains.relations.router.RelationsService", return_value=service) as ctor:
            result = await get_overview_scope(current_user=user)
        ctor.assert_called_once_with(user.id)
        assert result is scope

    async def test_put_persists_and_echoes_what_it_stored(self) -> None:
        """The caller adopts the ECHO, not what it sent: a value the server
        clamped is what the panel must pre-fill next time."""
        payload = RelationOverviewScope(sections=[OverviewSection.CONTACT], max_items=2)
        service = MagicMock(set_overview_scope=AsyncMock())
        user = _user()
        with patch("src.domains.relations.router.RelationsService", return_value=service) as ctor:
            result = await set_overview_scope(payload=payload, current_user=user)
        ctor.assert_called_once_with(user.id)
        service.set_overview_scope.assert_awaited_once_with(payload)
        assert result == payload

    def test_the_scope_routes_are_not_rate_limited(self) -> None:
        """One row of our own database. A budget there would only punish a
        reader for changing their mind."""
        for route in router.routes:
            if route.path != "/relations/overview-scope":
                continue
            guards = {
                getattr(dependency.call, "__name__", "")
                for dependency in route.dependant.dependencies
            }
            assert "rate_limit_dependency" not in guards
