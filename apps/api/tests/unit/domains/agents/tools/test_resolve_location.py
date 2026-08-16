"""Unit tests for the location-resolution chokepoint (runtime_helpers).

``resolve_location`` is the single cascade every location-aware tool goes
through (places, weather, routes, the skill runner) — and, by absence of a
browser context, scheduled actions. The 2026-08-16 generalization inserts the
opt-in persisted last-known location between the live browser position and
the home address:

- implicit (no location phrase): browser > last_known (fresh) > home > silent
- current/query ("near me", "where am I"): browser > last_known (fresh,
  ``as_of`` carried so the model can state the position's age) > localized
  fallback message
- home ("chez moi"): home > browser > fallback — a dated position is NOT a
  valid answer to a "home" reference and never enters this branch

``resolve_implicit_location`` is the shared implicit cascade extracted so the
places tools stop re-implementing "browser else home" by hand (three sites).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain.tools import ToolRuntime

from src.domains.agents.tools.location_resolution import (
    ResolvedLocation,
    get_user_last_known_location,
    resolve_implicit_location,
    resolve_location,
)
from src.domains.users.user_location_service import LastKnownLocation

pytestmark = pytest.mark.unit

AS_OF = datetime(2026, 8, 16, 9, 0, tzinfo=UTC)
BROWSER_GEO = {"lat": 48.6103, "lon": 2.47481}
LAST_KNOWN = ResolvedLocation(
    lat=43.6045, lon=1.4442, source="last_known", address=None, as_of=AS_OF
)
HOME = ResolvedLocation(lat=48.85, lon=2.35, source="home", address="1 rue de Paris")


def _runtime(
    geolocation: dict[str, float] | None = None,
    user_id: str | None = None,
) -> ToolRuntime[None, dict[Any, Any]]:
    configurable: dict[str, Any] = {}
    if geolocation is not None:
        configurable["__browser_context"] = {"geolocation": geolocation}
    if user_id is not None:
        configurable["user_id"] = user_id
    return ToolRuntime(
        state={},
        context=None,
        config={"configurable": configurable},
        stream_writer=lambda _: None,
        tool_call_id=None,
        store=None,
    )


def _patch_last_known(value: ResolvedLocation | None) -> Any:
    return patch(
        "src.domains.agents.tools.location_resolution.get_user_last_known_location",
        return_value=value,
    )


def _patch_home(value: ResolvedLocation | None) -> Any:
    return patch(
        "src.domains.agents.tools.location_resolution.get_user_home_location",
        return_value=value,
    )


# ---------------------------------------------------------------------------
# Implicit cascade (no location phrase in the message)
# ---------------------------------------------------------------------------


class TestImplicitCascade:
    async def test_browser_wins_without_touching_the_database(self) -> None:
        with _patch_last_known(LAST_KNOWN) as lk, _patch_home(HOME) as home:
            location, fallback = await resolve_location(
                _runtime(BROWSER_GEO), "quel temps fait-il", "fr"
            )
        assert location is not None and location.source == "browser"
        assert fallback is None
        lk.assert_not_awaited()
        home.assert_not_awaited()

    async def test_last_known_beats_home_when_browser_is_gone(self) -> None:
        """The traveling-PWA scenario: frozen app, no live position — the
        persisted position must win over the home address."""
        with _patch_last_known(LAST_KNOWN), _patch_home(HOME) as home:
            location, fallback = await resolve_location(_runtime(), "quel temps fait-il", "fr")
        assert location is not None and location.source == "last_known"
        assert location.as_of == AS_OF
        assert fallback is None
        home.assert_not_awaited()

    async def test_home_remains_the_final_fallback(self) -> None:
        with _patch_last_known(None), _patch_home(HOME):
            location, fallback = await resolve_location(_runtime(), "quel temps fait-il", "fr")
        assert location is not None and location.source == "home"
        assert fallback is None

    async def test_nothing_available_stays_silent(self) -> None:
        with _patch_last_known(None), _patch_home(None):
            location, fallback = await resolve_location(_runtime(), "quel temps fait-il", "fr")
        assert location is None
        assert fallback is None


# ---------------------------------------------------------------------------
# Current-position / query phrases ("near me", "where am I")
# ---------------------------------------------------------------------------


class TestCurrentAndQueryCascade:
    async def test_browser_wins(self) -> None:
        with _patch_last_known(LAST_KNOWN) as lk:
            location, fallback = await resolve_location(_runtime(BROWSER_GEO), "où suis-je ?", "fr")
        assert location is not None and location.source == "browser"
        assert fallback is None
        lk.assert_not_awaited()

    async def test_fresh_last_known_answers_with_its_age(self) -> None:
        """A dated position is usable ONLY because ``as_of`` travels with it:
        the caller can (and must) state how old it is."""
        with _patch_last_known(LAST_KNOWN):
            location, fallback = await resolve_location(_runtime(), "restaurants près de moi", "fr")
        assert location is not None and location.source == "last_known"
        assert location.as_of == AS_OF
        assert fallback is None

    async def test_no_source_yields_the_localized_fallback_message(self) -> None:
        with _patch_last_known(None), _patch_home(HOME) as home:
            location, fallback = await resolve_location(_runtime(), "où suis-je ?", "fr")
        assert location is None
        assert fallback is not None
        # Home is NEVER an answer to "where am I": the branch must not even
        # consult it (answering a current-position question with the home
        # address is the lie this whole feature removes).
        home.assert_not_awaited()


# ---------------------------------------------------------------------------
# Home phrases ("chez moi")
# ---------------------------------------------------------------------------


class TestHomeCascade:
    async def test_home_wins_over_browser(self) -> None:
        with _patch_home(HOME):
            location, fallback = await resolve_location(
                _runtime(BROWSER_GEO), "météo chez moi", "fr"
            )
        assert location is not None and location.source == "home"
        assert fallback is None

    async def test_browser_substitutes_for_a_missing_home(self) -> None:
        with _patch_home(None):
            location, fallback = await resolve_location(
                _runtime(BROWSER_GEO), "météo chez moi", "fr"
            )
        assert location is not None and location.source == "browser"
        assert fallback is None

    async def test_last_known_never_answers_a_home_reference(self) -> None:
        """A position captured somewhere on the road says nothing about
        "home" — the branch falls back to the message, never to last_known."""
        with _patch_home(None), _patch_last_known(LAST_KNOWN) as lk:
            location, fallback = await resolve_location(_runtime(), "météo chez moi", "fr")
        assert location is None
        assert fallback is not None
        lk.assert_not_awaited()


# ---------------------------------------------------------------------------
# Shared implicit resolver (used by the places tools, no phrase detection)
# ---------------------------------------------------------------------------


class TestResolveImplicitLocation:
    async def test_browser_first(self) -> None:
        with _patch_last_known(LAST_KNOWN) as lk, _patch_home(HOME) as home:
            location = await resolve_implicit_location(_runtime(BROWSER_GEO))
        assert location is not None and location.source == "browser"
        lk.assert_not_awaited()
        home.assert_not_awaited()

    async def test_then_last_known(self) -> None:
        with _patch_last_known(LAST_KNOWN), _patch_home(HOME) as home:
            location = await resolve_implicit_location(_runtime())
        assert location is not None and location.source == "last_known"
        home.assert_not_awaited()

    async def test_then_home(self) -> None:
        with _patch_last_known(None), _patch_home(HOME):
            location = await resolve_implicit_location(_runtime())
        assert location is not None and location.source == "home"

    async def test_then_none(self) -> None:
        with _patch_last_known(None), _patch_home(None):
            assert await resolve_implicit_location(_runtime()) is None


# ---------------------------------------------------------------------------
# get_user_last_known_location (opt-in + freshness enforced at the source)
# ---------------------------------------------------------------------------


def _db_with_user(user: Any) -> Any:
    db = MagicMock()
    db.get = AsyncMock(return_value=user)
    return db


def _patch_db(db: Any) -> Any:
    @asynccontextmanager
    async def fake_context():
        yield db

    return patch(
        "src.infrastructure.database.session.get_db_context",
        side_effect=lambda: fake_context(),
    )


def _patch_service(last_known: LastKnownLocation | None) -> Any:
    service = MagicMock()
    service.get_last_known_location = AsyncMock(return_value=last_known)
    return patch(
        "src.domains.users.user_location_service.UserLocationService",
        return_value=service,
    )


class TestGetUserLastKnownLocation:
    async def test_no_user_id_short_circuits(self) -> None:
        assert await get_user_last_known_location(_runtime()) is None

    async def test_opt_out_returns_none_without_reading_the_location(self) -> None:
        user = SimpleNamespace(use_last_known_location=False)
        with _patch_db(_db_with_user(user)), _patch_service(None) as service_cls:
            assert await get_user_last_known_location(_runtime(user_id=str(uuid4()))) is None
        service_cls.assert_not_called()

    async def test_fresh_location_carries_source_and_as_of(self) -> None:
        user = SimpleNamespace(use_last_known_location=True)
        stored = LastKnownLocation(
            lat=43.6045, lon=1.4442, accuracy=25.0, updated_at=AS_OF, stale=False
        )
        with _patch_db(_db_with_user(user)), _patch_service(stored):
            location = await get_user_last_known_location(_runtime(user_id=str(uuid4())))
        assert location == ResolvedLocation(
            lat=43.6045, lon=1.4442, source="last_known", address=None, as_of=AS_OF
        )

    async def test_stale_location_is_refused(self) -> None:
        user = SimpleNamespace(use_last_known_location=True)
        stored = LastKnownLocation(
            lat=43.6045, lon=1.4442, accuracy=25.0, updated_at=AS_OF, stale=True
        )
        with _patch_db(_db_with_user(user)), _patch_service(stored):
            assert await get_user_last_known_location(_runtime(user_id=str(uuid4()))) is None

    async def test_database_failure_degrades_to_none(self) -> None:
        db = MagicMock()
        db.get = AsyncMock(side_effect=RuntimeError("db down"))
        with _patch_db(db):
            assert await get_user_last_known_location(_runtime(user_id=str(uuid4()))) is None
