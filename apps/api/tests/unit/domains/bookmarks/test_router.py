"""The bookmarks routes (ADR-282): auth binding, bounds, and what each answers.

What a route promises and this pins:

- every call is bound to the AUTHENTICATED account, never a query parameter;
- keeping answers 201 when a row was created and 200 when it already existed
  (the toggle asked for a state);
- the listing publishes the bounds it enforces (ADR-184) and an EXACT total;
- the operator's switch guards the act of KEEPING only — listing, the toggle
  state and deleting stay open (ADR-279's doctrine).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.constants import BOOKMARKS_PAGE_MAX_LIMIT
from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.bookmarks import router as router_module
from src.domains.bookmarks.router import router
from src.domains.feature_switches.registry import PlatformCapability

pytestmark = pytest.mark.unit

USER_ID = uuid.uuid4()
MODULE = "src.domains.bookmarks.router"


def _bookmark(**overrides: object) -> SimpleNamespace:
    base = {
        "id": uuid.uuid4(),
        "message_id": uuid.uuid4(),
        "conversation_id": uuid.uuid4(),
        "content": "**Réservé** : salle B, 14 h.",
        "request_content": "Réserve la salle B à 14 h",
        "answered_at": datetime(2026, 9, 12, 10, 0, tzinfo=UTC),
        "created_at": datetime(2026, 9, 12, 10, 5, tzinfo=UTC),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_active_session] = lambda: SimpleNamespace(
        id=USER_ID, language="fr"
    )
    app.dependency_overrides[get_db] = lambda: MagicMock()
    # The operator's switch is a dependency of its own; the wiring test checks
    # it sits where it must, this suite lets it through.
    guard = router_module.KEEP_GUARD[0].dependency
    assert guard is not None
    app.dependency_overrides[guard] = lambda: None
    return TestClient(app)


class TestKeeping:
    def test_a_new_bookmark_answers_201_with_the_row(self, client: TestClient) -> None:
        kept = _bookmark()
        with patch(f"{MODULE}.BookmarkService") as service_cls:
            service_cls.return_value.keep = AsyncMock(return_value=(kept, True))
            response = client.post("/bookmarks", json={"message_id": str(kept.message_id)})

        assert response.status_code == 201
        assert response.json()["id"] == str(kept.id)
        assert response.json()["request_content"] == "Réserve la salle B à 14 h"
        service_cls.return_value.keep.assert_awaited_once_with(
            USER_ID, kept.message_id, language="fr"
        )

    def test_an_existing_bookmark_answers_200(self, client: TestClient) -> None:
        kept = _bookmark()
        with patch(f"{MODULE}.BookmarkService") as service_cls:
            service_cls.return_value.keep = AsyncMock(return_value=(kept, False))
            response = client.post("/bookmarks", json={"message_id": str(kept.message_id)})

        assert response.status_code == 200

    def test_the_act_of_keeping_is_the_guarded_route(self) -> None:
        """ADR-279: a switch removes the capability, never the record."""
        guarded = {
            getattr(route, "path", "")
            for route in router.routes
            if any(
                getattr(getattr(d, "dependency", None), "__name__", "")
                == f"require_capability_{PlatformCapability.BOOKMARKS.value}"
                for d in getattr(route, "dependencies", [])
            )
        }
        assert guarded == {"/bookmarks"}
        assert not getattr(router, "dependencies", [])


class TestListing:
    def test_it_publishes_the_bounds_and_the_exact_total(self, client: TestClient) -> None:
        rows = [_bookmark(), _bookmark()]
        with (
            patch(f"{MODULE}.BookmarkService") as service_cls,
            patch(f"{MODULE}.settings") as fake_settings,
        ):
            fake_settings.bookmarks_max_per_user = 500
            service_cls.return_value.list_page = AsyncMock(return_value=(rows, 41))
            response = client.get("/bookmarks?q=salle&limit=2&offset=4")

        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) == 2
        assert body["total"] == 41
        assert body["limit"] == 2
        assert body["offset"] == 4
        assert body["max_limit"] == BOOKMARKS_PAGE_MAX_LIMIT
        assert body["max_per_user"] == 500
        filters = service_cls.return_value.list_page.await_args.args[1]
        assert (filters.query, filters.limit, filters.offset) == ("salle", 2, 4)

    def test_limit_bounds_are_enforced(self, client: TestClient) -> None:
        assert client.get("/bookmarks?limit=0").status_code == 422
        assert client.get(f"/bookmarks?limit={BOOKMARKS_PAGE_MAX_LIMIT + 1}").status_code == 422
        assert client.get("/bookmarks?offset=-1").status_code == 422

    def test_the_state_is_the_map_of_attached_messages(self, client: TestClient) -> None:
        message_id, bookmark_id = uuid.uuid4(), uuid.uuid4()
        with patch(f"{MODULE}.BookmarkService") as service_cls:
            service_cls.return_value.attached_message_ids = AsyncMock(
                return_value={message_id: bookmark_id}
            )
            response = client.get("/bookmarks/state")

        assert response.status_code == 200
        assert response.json() == {"message_ids": {str(message_id): str(bookmark_id)}}


class TestRemoving:
    def test_by_id_answers_204(self, client: TestClient) -> None:
        bookmark_id = uuid.uuid4()
        with patch(f"{MODULE}.BookmarkService") as service_cls:
            service_cls.return_value.remove = AsyncMock()
            response = client.delete(f"/bookmarks/{bookmark_id}")

        assert response.status_code == 204
        service_cls.return_value.remove.assert_awaited_once_with(USER_ID, bookmark_id)

    def test_by_message_answers_204_when_a_row_went_and_404_otherwise(
        self, client: TestClient
    ) -> None:
        message_id = uuid.uuid4()
        with patch(f"{MODULE}.BookmarkService") as service_cls:
            service_cls.return_value.remove_by_message = AsyncMock(return_value=True)
            assert client.delete(f"/bookmarks/by-message/{message_id}").status_code == 204
            service_cls.return_value.remove_by_message = AsyncMock(return_value=False)
            assert client.delete(f"/bookmarks/by-message/{message_id}").status_code == 404
