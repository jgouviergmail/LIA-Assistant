"""The HTTP contract of a fired reminder's buttons (ADR-268 amendment 2026-11-16).

The service is proved on PostgreSQL (``test_reminder_firings_pg``); this pins
what only the route decides: the occurrence is acted on for the SESSION's
account, « tomorrow morning » is read in the account's own zone, a Telegram
press cannot be forged through the web door, a foreign or purged occurrence
answers 404 and commits nothing, and the two writing verbs are rate limited.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.dependencies import get_db
from src.core.exceptions import ResourceNotFoundError
from src.core.session_dependencies import get_current_active_session
from src.domains.reminders import router as reminders_router
from src.domains.reminders.firing_service import FiringState, SnoozeResult
from src.domains.reminders.firings import (
    FiringSurface,
    SnoozeChoice,
    SnoozeDelays,
    SnoozeOutcome,
    StopOutcome,
)
from tests._routes import served_routes

pytestmark = pytest.mark.unit

FIRING = uuid.uuid4()
FIRED_AT = datetime(2026, 11, 16, 14, 0, tzinfo=UTC)


class _Session:
    """The request's database session: only its commit matters here."""

    def __init__(self) -> None:
        self.commit = AsyncMock()


@pytest.fixture
def account() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), timezone="America/New_York", language="fr")


@pytest.fixture
def session() -> _Session:
    return _Session()


@pytest.fixture
def client(account: SimpleNamespace, session: _Session) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(reminders_router.router)
    app.dependency_overrides[get_current_active_session] = lambda: account
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[reminders_router.rate_limit_firing_actions] = lambda: None
    with TestClient(app) as test_client:
        yield test_client


#: Where the route builds its service, replaced per test.
SERVICE = "src.domains.reminders.router.ReminderFiringService"


class TestTheState:
    def test_it_reads_the_sessions_occurrence_and_says_what_it_offers(
        self, client: TestClient, account: SimpleNamespace
    ) -> None:
        state = FiringState(
            firing_id=FIRING,
            fired_at=FIRED_AT,
            snoozable_until=FIRED_AT + timedelta(hours=24),
            snoozed_until=None,
            stoppable=True,
            delays=SnoozeDelays(short_minutes=10, long_minutes=60, morning_hour=9),
        )
        with patch(SERVICE) as service_cls:
            service_cls.return_value.state = AsyncMock(return_value=state)

            response = client.get(f"/reminders/firings/{FIRING}")

        assert response.status_code == 200
        assert response.json() == {
            "id": str(FIRING),
            "fired_at": "2026-11-16T14:00:00Z",
            "snoozable_until": "2026-11-17T14:00:00Z",
            "snoozed_until": None,
            "stoppable": True,
            "short_minutes": 10,
            "long_minutes": 60,
        }
        args, _ = service_cls.return_value.state.await_args
        assert args == (FIRING, account.id)

    def test_an_unknown_or_foreign_occurrence_is_a_404(self, client: TestClient) -> None:
        with patch(SERVICE) as service_cls:
            service_cls.return_value.state = AsyncMock(
                side_effect=ResourceNotFoundError("reminder_firing", str(FIRING))
            )

            response = client.get(f"/reminders/firings/{FIRING}")

        assert response.status_code == 404


class TestTheSnooze:
    def test_it_postpones_in_the_accounts_zone_and_commits(
        self, client: TestClient, account: SimpleNamespace, session: _Session
    ) -> None:
        back = FIRED_AT + timedelta(minutes=10)
        with patch(SERVICE) as service_cls:
            service_cls.return_value.snooze = AsyncMock(
                return_value=SnoozeResult(SnoozeOutcome.SNOOZED, snoozed_until=back)
            )

            response = client.post(
                f"/reminders/firings/{FIRING}/snooze", json={"choice": "morning", "surface": "push"}
            )

        assert response.status_code == 200
        assert response.json() == {
            "outcome": "snoozed",
            "snoozed_until": "2026-11-16T14:10:00Z",
            "next_occurrence_at": None,
        }
        args, kwargs = service_cls.return_value.snooze.await_args
        assert args == (FIRING, account.id, SnoozeChoice.MORNING)
        assert kwargs["zone"] == "America/New_York"
        assert kwargs["surface"] is FiringSurface.PUSH
        session.commit.assert_awaited_once()

    def test_an_account_without_a_zone_reads_the_default_one(
        self, client: TestClient, account: SimpleNamespace
    ) -> None:
        account.timezone = None
        with patch(SERVICE) as service_cls:
            service_cls.return_value.snooze = AsyncMock(
                return_value=SnoozeResult(SnoozeOutcome.EXPIRED)
            )

            response = client.post(f"/reminders/firings/{FIRING}/snooze", json={"choice": "short"})

        assert response.status_code == 200
        assert response.json()["outcome"] == "expired"
        _, kwargs = service_cls.return_value.snooze.await_args
        assert kwargs["zone"] == DEFAULT_USER_DISPLAY_TIMEZONE
        assert kwargs["surface"] is FiringSurface.CHAT

    def test_a_refused_press_names_the_occurrence_it_met(self, client: TestClient) -> None:
        upcoming = FIRED_AT + timedelta(hours=19)
        with patch(SERVICE) as service_cls:
            service_cls.return_value.snooze = AsyncMock(
                return_value=SnoozeResult(SnoozeOutcome.COLLIDES, next_occurrence_at=upcoming)
            )

            response = client.post(
                f"/reminders/firings/{FIRING}/snooze", json={"choice": "morning"}
            )

        assert response.json() == {
            "outcome": "collides",
            "snoozed_until": None,
            "next_occurrence_at": "2026-11-17T09:00:00Z",
        }

    @pytest.mark.parametrize(
        "body",
        [
            {"choice": "short", "surface": "telegram"},  # the bot's own door
            {"choice": "later"},
            {},
        ],
    )
    def test_a_press_no_button_draws_is_refused(self, client: TestClient, body: dict) -> None:
        with patch(SERVICE) as service_cls:
            service_cls.return_value.snooze = AsyncMock()

            response = client.post(f"/reminders/firings/{FIRING}/snooze", json=body)

        assert response.status_code == 422
        service_cls.return_value.snooze.assert_not_awaited()

    def test_a_purged_occurrence_is_a_404_that_commits_nothing(
        self, client: TestClient, session: _Session
    ) -> None:
        with patch(SERVICE) as service_cls:
            service_cls.return_value.snooze = AsyncMock(
                side_effect=ResourceNotFoundError("reminder_firing", str(FIRING))
            )

            response = client.post(f"/reminders/firings/{FIRING}/snooze", json={"choice": "long"})

        assert response.status_code == 404
        session.commit.assert_not_awaited()


class TestTheStop:
    def test_it_stops_the_series_of_the_sessions_occurrence(
        self, client: TestClient, account: SimpleNamespace, session: _Session
    ) -> None:
        with patch(SERVICE) as service_cls:
            service_cls.return_value.stop = AsyncMock(return_value=StopOutcome.STOPPED)

            response = client.post(f"/reminders/firings/{FIRING}/stop")

        assert response.status_code == 200
        assert response.json() == {"outcome": "stopped"}
        args, kwargs = service_cls.return_value.stop.await_args
        assert args == (FIRING, account.id)
        assert kwargs["surface"] is FiringSurface.CHAT
        session.commit.assert_awaited_once()


def test_the_two_writing_verbs_are_rate_limited_per_account() -> None:
    """A person presses a button; a script looping on one is refused."""
    limited = {
        route.path
        for route in served_routes(reminders_router.router)
        if any(
            dependency.call is reminders_router.rate_limit_firing_actions
            for dependency in route.dependant.dependencies
        )
    }

    assert limited == {
        "/reminders/firings/{firing_id}/snooze",
        "/reminders/firings/{firing_id}/stop",
    }
