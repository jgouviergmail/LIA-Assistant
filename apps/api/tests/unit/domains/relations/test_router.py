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

from src.domains.relations.router import add_relation_favorite, remove_relation_favorite, router


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
class TestRouteTable:
    """The favorites routes must beat the `/{name}` catch-all by literal match."""

    def test_favorites_paths_declared(self) -> None:
        paths = {(route.path, tuple(sorted(route.methods))) for route in router.routes}
        assert ("/relations/favorites/{name}", ("DELETE",)) in paths
        assert ("/relations/favorites/{name}", ("PUT",)) in paths
