"""The radio's routes (ADR-324): bound to the caller, guarded, refusing with stable codes.

What a route promises and this pins:

- every route sits under the radio's capability switch;
- every call is bound to the AUTHENTICATED account, never a parameter;
- a start refused names itself in ``detail.code`` (the web translates it);
- a session, a segment or a site that is not the caller's reads as absent;
- a segment's audio is never cached (live only, no replay);
- looking for a site's feed reaches a stranger's server: both routes that do
  it carry the per-account rate limiter.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.radio import router as router_module
from src.domains.radio.budget import BudgetStatus
from src.domains.radio.errors import (
    BUDGET_REACHED,
    START_REFUSALS,
    TIMER_TOO_LONG,
    raise_source_not_found,
    refuse,
)
from src.domains.radio.formats import MusicMood
from src.domains.radio.newsroom.discovery import FeedDescription
from src.domains.radio.newsroom.sources import Discovery, DiscoveryOutcome
from src.domains.radio.preferences import RadioPreferences
from src.domains.radio.repository import RadioSource
from src.domains.radio.router import router
from src.domains.radio.schemas import (
    RadioArticleResponse,
    RadioPlayheadRequest,
    RadioSessionResponse,
    RadioSessionStatus,
    RadioSourcesResponse,
    RadioSourceUpdateRequest,
    RadioStartRequest,
)
from src.domains.radio.setup_builder import RadioStartRefused
from tests._routes import served_routes

pytestmark = pytest.mark.unit

USER_ID = uuid.UUID("00000000-0000-4000-8000-0000000000f1")
SESSION_ID = uuid.UUID("00000000-0000-4000-8000-0000000000f2")
FEED = "https://outlet.example/feed.xml"


def answer(status: RadioSessionStatus = "starting") -> RadioSessionResponse:
    return RadioSessionResponse(
        session_id=SESSION_ID,
        status=status,
        segments=[],
        cost_eur=0.0,
        stop_at=None,
        startup_estimate_s=12.0,
        end_reason=None,
        mood=MusicMood.CALM,
    )


class Service:
    """Stands for the session doors: answers as set, records the caller."""

    def __init__(self) -> None:
        self.refusal: str | None = None
        self.refusal_detail: dict[str, object] = {}
        self.session: RadioSessionResponse | None = answer()
        self.stopped = True
        self.audio: Path | None = None
        self.calls: list[tuple[str, uuid.UUID]] = []

    async def start(self, user_id: uuid.UUID, request: RadioStartRequest) -> RadioSessionResponse:
        self.calls.append(("start", user_id))
        if self.refusal is not None:
            raise RadioStartRefused(self.refusal, detail=self.refusal_detail)
        assert self.session is not None
        return self.session

    async def report(
        self, user_id: uuid.UUID, session_id: uuid.UUID, request: RadioPlayheadRequest
    ) -> RadioSessionResponse | None:
        self.calls.append(("report", user_id))
        return self.session

    async def stop(self, user_id: uuid.UUID, session_id: uuid.UUID) -> bool:
        self.calls.append(("stop", user_id))
        return self.stopped

    async def audio_path(self, user_id: uuid.UUID, session_id: uuid.UUID, seq: int) -> Path | None:
        self.calls.append(("audio", user_id))
        return self.audio


@pytest.fixture
def service(monkeypatch: pytest.MonkeyPatch) -> Service:
    doors = Service()

    async def radio_service() -> Service:
        return doors

    monkeypatch.setattr(router_module, "radio_service", radio_service)
    return doors


def app_for(*, guarded: bool) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_active_session_for_stream] = lambda: SimpleNamespace(
        id=USER_ID, language="fr"
    )
    app.dependency_overrides[router_module.rate_limit_source_lookup] = lambda: None
    if not guarded:
        # The switch is a dependency of its own; one test below keeps it.
        guard = router.dependencies[0].dependency
        assert guard is not None
        app.dependency_overrides[guard] = lambda: None
    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app_for(guarded=False))


class TestTheSwitch:
    def test_switched_off_every_route_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def off(capability: object) -> bool:
            return False

        monkeypatch.setattr("src.domains.feature_switches.guard.is_capability_enabled", off)
        client = TestClient(app_for(guarded=True))

        response = client.get("/radio/preferences")

        assert response.status_code == 403
        assert response.json()["detail"]["capability"] == "radio"


class TestTheSession:
    def test_a_start_answers_201_for_the_caller(self, client: TestClient, service: Service) -> None:
        response = client.post("/radio/sessions", json={})

        assert response.status_code == 201
        assert response.json()["session_id"] == str(SESSION_ID)
        assert service.calls == [("start", USER_ID)]

    @pytest.mark.parametrize(
        ("reason", "code"),
        sorted((r, c) for r, c in START_REFUSALS.items() if c != BUDGET_REACHED),
    )
    def test_a_start_the_instance_cannot_serve_names_itself(
        self, client: TestClient, service: Service, reason: str, code: str
    ) -> None:
        service.refusal = reason

        response = client.post("/radio/sessions", json={})

        assert response.status_code == 503
        assert response.json()["detail"] == {"code": code}

    def test_a_start_past_the_radio_s_budget_says_its_bound_and_when_it_lifts(
        self, client: TestClient, service: Service
    ) -> None:
        service.refusal = "budget_reached"
        service.refusal_detail = {"max_eur": 2.0, "lifts_at": "2026-09-27T21:00:00+00:00"}

        response = client.post("/radio/sessions", json={})

        assert response.status_code == 429
        assert response.json()["detail"] == {
            "code": BUDGET_REACHED,
            "max_eur": 2.0,
            "lifts_at": "2026-09-27T21:00:00+00:00",
        }

    def test_a_session_that_is_not_the_caller_s_reads_as_absent(
        self, client: TestClient, service: Service
    ) -> None:
        service.session = None
        service.stopped = False

        report = client.post(
            f"/radio/sessions/{SESSION_ID}/playhead",
            json={"seq": 1, "position_s": 3.0, "playing": True},
        )
        stop = client.post(f"/radio/sessions/{SESSION_ID}/stop")

        assert (report.status_code, stop.status_code) == (404, 404)

    def test_a_stop_answers_no_content(self, client: TestClient, service: Service) -> None:
        response = client.post(f"/radio/sessions/{SESSION_ID}/stop")

        assert response.status_code == 204
        assert service.calls == [("stop", USER_ID)]


class TestTheAudio:
    def test_a_ready_segment_is_served_and_never_cached(
        self, client: TestClient, service: Service, tmp_path: Path
    ) -> None:
        segment = tmp_path / "0001.mp3"
        segment.write_bytes(b"ID3-mp3")
        service.audio = segment

        response = client.get(f"/radio/sessions/{SESSION_ID}/segments/1/audio")

        assert response.status_code == 200
        assert response.content == b"ID3-mp3"
        assert response.headers["content-type"] == "audio/mpeg"
        assert response.headers["cache-control"] == "no-store"
        assert service.calls == [("audio", USER_ID)]

    def test_a_segment_not_ready_or_not_theirs_reads_as_absent(
        self, client: TestClient, service: Service
    ) -> None:
        response = client.get(f"/radio/sessions/{SESSION_ID}/segments/2/audio")

        assert response.status_code == 404


class TheArticle:
    """Stands for ``radio_article``: records who asked, answers or not."""

    def __init__(self, found: bool) -> None:
        self.found = found
        self.asked: list[tuple[uuid.UUID, uuid.UUID, str]] = []

    async def __call__(
        self, user_id: uuid.UUID, story_id: uuid.UUID, language: str
    ) -> RadioArticleResponse | None:
        self.asked.append((user_id, story_id, language))
        if not self.found:
            return None
        return RadioArticleResponse(
            id=story_id,
            outlet="Global Voices",
            url="https://globalvoices.org/story",
            published_at="2026-09-26T19:00:00Z",
            title="Un titre",
            text="Le texte.",
            complete=True,
            cut=False,
            translated=True,
            source_language="en",
            translation_failed=False,
            budget_reached=False,
            cost_eur=0.0021,
        )


class TestTheArticle:
    def test_the_article_is_opened_for_the_caller_in_their_language(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        article = TheArticle(found=True)
        monkeypatch.setattr(router_module, "radio_article", article)
        story_id = uuid.uuid4()

        response = client.get(f"/radio/articles/{story_id}")

        assert response.status_code == 200
        assert response.json()["title"] == "Un titre"
        assert response.json()["cost_eur"] == 0.0021
        assert article.asked == [(USER_ID, story_id, "fr")]

    def test_a_story_that_is_not_the_caller_s_reads_as_absent(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(router_module, "radio_article", TheArticle(found=False))

        assert client.get(f"/radio/articles/{uuid.uuid4()}").status_code == 404


class TestThePreferences:
    def test_they_are_read_for_the_caller_in_their_language(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def listener_preferences(user_id: uuid.UUID, language: str) -> RadioPreferences:
            assert (user_id, language) == (USER_ID, "fr")
            return RadioPreferences(timer_minutes=30)

        monkeypatch.setattr(router_module, "listener_preferences", listener_preferences)

        response = client.get("/radio/preferences")

        assert response.status_code == 200
        assert response.json()["timer_minutes"] == 30

    def test_a_write_is_checked_in_the_caller_s_language(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[tuple[uuid.UUID, str, RadioPreferences]] = []

        async def save_preferences(
            user_id: uuid.UUID, language: str, preferences: RadioPreferences
        ) -> RadioPreferences:
            seen.append((user_id, language, preferences))
            return preferences

        monkeypatch.setattr(router_module, "save_preferences", save_preferences)

        response = client.put("/radio/preferences", json={"public_mode": True})

        assert response.status_code == 200
        assert seen == [(USER_ID, "fr", RadioPreferences(public_mode=True))]

    def test_a_refused_write_carries_its_code_and_its_bound(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def save_preferences(
            user_id: uuid.UUID, language: str, preferences: RadioPreferences
        ) -> RadioPreferences:
            refuse(TIMER_TOO_LONG, max_minutes=240)

        monkeypatch.setattr(router_module, "save_preferences", save_preferences)

        response = client.put("/radio/preferences", json={"timer_minutes": 999})

        assert response.status_code == 422
        assert response.json()["detail"] == {"code": TIMER_TOO_LONG, "max_minutes": 240}

    def test_an_unknown_field_is_refused_at_the_door(self, client: TestClient) -> None:
        response = client.put("/radio/preferences", json={"volume": 11})

        assert response.status_code == 422


def source(title: str = "Outlet") -> RadioSource:
    return RadioSource(id=uuid.uuid4(), feed_url=FEED, title=title, language="en")


class TestTheSites:
    def test_the_listing_is_the_caller_s_every_source_with_what_it_holds(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        view = RadioSourcesResponse(base=[], own=[], stories=3, unheard=2, window_hours=48)

        async def listener_sources(user_id: uuid.UUID, *, now: datetime) -> RadioSourcesResponse:
            assert user_id == USER_ID and now.tzinfo is not None
            return view

        monkeypatch.setattr(router_module, "listener_sources", listener_sources)

        response = client.get("/radio/sources")

        assert response.status_code == 200
        assert response.json() == view.model_dump(mode="json")

    @pytest.mark.parametrize(("theirs", "status"), [(True, 204), (False, 404)])
    def test_a_site_is_renamed_or_paused_by_its_owner_alone(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
        theirs: bool,
        status: int,
    ) -> None:
        received: list[RadioSourceUpdateRequest] = []

        async def update_listener_source(
            user_id: uuid.UUID, source_id: uuid.UUID, request: RadioSourceUpdateRequest
        ) -> None:
            assert user_id == USER_ID
            received.append(request)
            if not theirs:
                raise_source_not_found(source_id)

        monkeypatch.setattr(router_module, "update_listener_source", update_listener_source)

        response = client.patch(f"/radio/sources/{uuid.uuid4()}", json={"paused": True})

        assert response.status_code == status
        assert received == [RadioSourceUpdateRequest(paused=True)]

    @pytest.mark.parametrize(
        "body",
        [{}, {"title": "My <blog>"}, {"title": "   "}, {"paused": True, "volume": 11}],
        ids=["nothing-to-change", "markup", "blank", "unknown-field"],
    )
    def test_a_change_the_radio_cannot_make_is_refused_at_the_door(
        self, client: TestClient, body: dict[str, object]
    ) -> None:
        response = client.patch(f"/radio/sources/{uuid.uuid4()}", json=body)

        assert response.status_code == 422

    def test_forgetting_what_was_heard_answers_no_content(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        forgotten: list[uuid.UUID] = []

        async def forget_heard(user_id: uuid.UUID) -> None:
            forgotten.append(user_id)

        monkeypatch.setattr(router_module, "forget_heard", forget_heard)

        response = client.delete("/radio/heard")

        assert response.status_code == 204
        assert forgotten == [USER_ID]

    def test_a_preview_answers_what_was_found_never_an_error(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def look_for_feed(address: str) -> Discovery:
            assert address == "outlet.example"
            return Discovery(
                DiscoveryOutcome.FOUND,
                feed_url=FEED,
                description=FeedDescription(title="Outlet", language="en", entries=7),
            )

        monkeypatch.setattr(router_module, "look_for_feed", look_for_feed)

        response = client.post("/radio/sources/preview", json={"address": "outlet.example"})

        assert response.status_code == 200
        assert response.json() == {
            "outcome": "found",
            "feed_url": FEED,
            "title": "Outlet",
            "language": "en",
            "entries": 7,
        }

    def test_adding_a_site_answers_201_with_what_was_stored(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        added = source("Outlet Daily")

        async def add_listener_source(user_id: uuid.UUID, address: str) -> RadioSource:
            assert (user_id, address) == (USER_ID, "outlet.example")
            return added

        monkeypatch.setattr(router_module, "add_listener_source", add_listener_source)

        response = client.post("/radio/sources", json={"address": "outlet.example"})

        assert response.status_code == 201
        assert response.json()["title"] == "Outlet Daily"

    @pytest.mark.parametrize(("removed", "status"), [(True, 204), (False, 404)])
    def test_removing_a_site_that_is_not_theirs_reads_as_absent(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
        removed: bool,
        status: int,
    ) -> None:
        async def remove_source(user_id: uuid.UUID, source_id: uuid.UUID) -> bool:
            assert user_id == USER_ID
            return removed

        monkeypatch.setattr(router_module, "remove_source", remove_source)

        response = client.delete(f"/radio/sources/{uuid.uuid4()}")

        assert response.status_code == status

    def test_every_route_that_reaches_a_stranger_s_server_is_rate_limited(self) -> None:
        limited: set[tuple[str, str]] = set()
        for route in served_routes(router):
            assert isinstance(route.original_route, APIRoute)
            dependencies: list[Any] = [dep.dependency for dep in route.dependencies]
            if router_module.rate_limit_source_lookup in dependencies:
                limited |= {(method, route.path) for method in route.methods}

        assert limited == {("POST", "/radio/sources/preview"), ("POST", "/radio/sources")}


def starts(outcome: str) -> float:
    return REGISTRY.get_sample_value("radio_session_starts_total", {"outcome": outcome}) or 0.0


class TestEveryStartIsCounted:
    def test_a_start_that_took_its_place(self, client: TestClient, service: Service) -> None:
        before = starts("started")

        client.post("/radio/sessions", json={})

        assert starts("started") == before + 1

    @pytest.mark.parametrize(("reason", "code"), sorted(START_REFUSALS.items()))
    def test_a_refused_start_counts_its_code(
        self, client: TestClient, service: Service, reason: str, code: str
    ) -> None:
        service.refusal = reason
        before, started = starts(code), starts("started")

        client.post("/radio/sessions", json={})

        assert (starts(code), starts("started")) == (before + 1, started)


class TestTheBudget:
    """ADR-324 decision 37: what the listener's radio spent over the rolling day, published."""

    def test_the_listener_reads_what_their_radio_spent_over_the_day(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def listener_budget(user_id: uuid.UUID, *, now: datetime) -> BudgetStatus:
            assert user_id == USER_ID and now.tzinfo is not None
            return BudgetStatus(limit_eur=2.0, spent_eur=0.42, lifts_at=None)

        monkeypatch.setattr(router_module, "listener_budget", listener_budget)

        response = client.get("/radio/budget")

        assert response.status_code == 200
        assert response.json() == {
            "limit_eur": 2.0,
            "spent_eur": 0.42,
            "window_hours": 24,
            "lifts_at": None,
        }
