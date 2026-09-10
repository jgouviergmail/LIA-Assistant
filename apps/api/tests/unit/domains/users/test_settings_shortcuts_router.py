"""``/users/me/settings-shortcuts`` (ADR-277) — a tolerant read, a strict and capped write.

The chat shortcuts precedent, on the users router: the schema refuses a
malformed or duplicated token, the router refuses the count (it reads the
runtime setting), and the write is a NEW list on the row — the JSONB rule.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.config import settings
from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.users.router import router

pytestmark = pytest.mark.unit

ENDPOINT = "/users/me/settings-shortcuts"


@pytest.fixture
def user() -> SimpleNamespace:
    return SimpleNamespace(id="u1", settings_shortcuts=None)


@pytest.fixture
def db() -> MagicMock:
    session = MagicMock()
    session.commit = AsyncMock()
    return session


@pytest.fixture
def client(user: SimpleNamespace, db: MagicMock) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_active_session] = lambda: user

    async def _db() -> AsyncIterator[MagicMock]:
        yield db

    app.dependency_overrides[get_db] = _db
    return TestClient(app)


class TestTheRead:
    def test_a_null_column_reads_as_nothing_pinned(self, client: TestClient) -> None:
        resp = client.get(ENDPOINT)

        assert resp.status_code == 200
        assert resp.json() == {
            "shortcuts": [],
            "max_count": settings.settings_shortcuts_max_count,
        }

    def test_a_malformed_stored_entry_is_dropped_never_raised(
        self, client: TestClient, user: SimpleNamespace
    ) -> None:
        user.settings_shortcuts = ["theme", "BAD ID", 7, "font"]

        resp = client.get(ENDPOINT)

        assert resp.status_code == 200
        assert resp.json()["shortcuts"] == ["theme", "font"]


class TestTheWrite:
    def test_replaces_the_list_with_a_new_one(
        self, client: TestClient, user: SimpleNamespace, db: MagicMock
    ) -> None:
        resp = client.put(ENDPOINT, json={"shortcuts": ["theme", "font"]})

        assert resp.status_code == 200
        assert resp.json() == {
            "shortcuts": ["theme", "font"],
            "max_count": settings.settings_shortcuts_max_count,
        }
        assert user.settings_shortcuts == ["theme", "font"]
        db.add.assert_called_once_with(user)
        db.commit.assert_awaited_once()

    def test_an_empty_list_unpins_everything(
        self, client: TestClient, user: SimpleNamespace, db: MagicMock
    ) -> None:
        user.settings_shortcuts = ["theme"]

        resp = client.put(ENDPOINT, json={"shortcuts": []})

        assert resp.status_code == 200
        assert user.settings_shortcuts == []
        db.commit.assert_awaited_once()

    def test_refuses_more_than_the_runtime_cap_and_writes_nothing(
        self, client: TestClient, user: SimpleNamespace, db: MagicMock
    ) -> None:
        too_many = [f"section-{i}" for i in range(settings.settings_shortcuts_max_count + 1)]

        resp = client.put(ENDPOINT, json={"shortcuts": too_many})

        assert resp.status_code == 400
        assert user.settings_shortcuts is None
        db.commit.assert_not_awaited()

    @pytest.mark.parametrize("bad", [["Theme"], ["theme", "theme"], ["a b"], [""]])
    def test_refuses_a_malformed_or_duplicated_token(
        self, client: TestClient, user: SimpleNamespace, db: MagicMock, bad: list[str]
    ) -> None:
        resp = client.put(ENDPOINT, json={"shortcuts": bad})

        assert resp.status_code == 422
        assert user.settings_shortcuts is None
        db.commit.assert_not_awaited()
