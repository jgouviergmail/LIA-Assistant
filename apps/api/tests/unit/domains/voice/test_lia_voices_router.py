"""The voice mode settings' routes for LIA's voices (ADR-345 amendment 2026-10-14)."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.constants import VOICE_ID_MAX_CHARS
from src.core.dependencies import get_db
from src.core.exceptions import BaseAPIException
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.voice import lia_voices_router as module
from src.domains.voice.engine_voices import EngineVoices
from src.domains.voice.factory import TTSConfig
from src.domains.voice.lia_voices import LIA_VOICE_UNKNOWN, Gender, LiaVoices
from src.domains.voice.voices_catalog import VoiceOption
from tests._routes import served_routes

pytestmark = pytest.mark.unit

PERSON = uuid4()
REMY = VoiceOption("r" * 32, "Remy", "male", "fr")
EMILIE = VoiceOption("f" * 32, "Emilie", "female", "fr")
CONFIG = TTSConfig(
    provider="fishaudio", model="s2.1-pro", voice_male=REMY.voice_id, voice_female=EMILIE.voice_id
)


def view(chosen: Mapping[Gender, str]) -> LiaVoices:
    return LiaVoices(
        engine=EngineVoices(CONFIG, [REMY, EMILIE], multilingual=True),
        voices=[EMILIE, REMY],
        chosen=dict(chosen),
        defaults={"male": REMY, "female": EMILIE},
    )


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, Any]]:
    seen: list[tuple[str, Any]] = []

    async def read(user_id: UUID, language: str) -> LiaVoices:
        seen.append(("read", (user_id, language)))
        return view({"female": EMILIE.voice_id})

    async def save(user_id: UUID, language: str, choice: Mapping[Gender, str]) -> LiaVoices:
        seen.append(("save", (user_id, language, dict(choice))))
        if "nope" in choice.values():
            raise BaseAPIException(status_code=422, detail={"code": LIA_VOICE_UNKNOWN})
        return view(choice)

    async def enabled(capability: Any) -> bool:
        return True

    monkeypatch.setattr(module, "lia_voices", read)
    monkeypatch.setattr(module, "save_lia_voices", save)
    monkeypatch.setattr(module, "is_capability_enabled", enabled)
    return seen


@pytest.fixture
def client(calls: list[tuple[str, Any]]) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[get_current_active_session_for_stream] = lambda: SimpleNamespace(
        id=PERSON, language="fr-FR"
    )
    with TestClient(app) as test_client:
        yield test_client


class TestTheRead:
    def test_publishes_the_engine_the_voices_the_choice_and_the_instance_s_voices(
        self, client: TestClient, calls: list[tuple[str, Any]]
    ) -> None:
        body = client.get("/voice/lia-voices").json()

        assert (body["available"], body["engine"], body["provider"]) == (
            True,
            "fishaudio/s2.1-pro",
            "fishaudio",
        )
        assert [voice["label"] for voice in body["voices"]] == ["Emilie", "Remy"]
        assert (body["male"], body["female"]) == (None, EMILIE.voice_id)
        assert body["default_male"]["label"] == "Remy"
        assert body["default_female"]["voice_id"] == EMILIE.voice_id
        # The stored language, through the one locale door.
        assert calls == [("read", (PERSON, "fr"))]


class TestTheWrite:
    def test_keeps_the_voices_chosen_a_null_one_left_to_the_instance(
        self, client: TestClient, calls: list[tuple[str, Any]]
    ) -> None:
        response = client.put("/voice/lia-voices", json={"male": REMY.voice_id, "female": None})

        assert response.status_code == 200
        assert response.json()["male"] == REMY.voice_id
        assert calls == [("save", (PERSON, "fr", {"male": REMY.voice_id}))]

    def test_a_voice_the_engine_does_not_offer_is_refused_by_its_code(
        self, client: TestClient
    ) -> None:
        response = client.put("/voice/lia-voices", json={"male": "nope"})

        assert response.status_code == 422
        assert response.json()["detail"] == {"code": LIA_VOICE_UNKNOWN}

    @pytest.mark.parametrize(
        "body",
        [{"male": ""}, {"female": "x" * (VOICE_ID_MAX_CHARS + 1)}, {"neutral": "a"}],
    )
    def test_what_names_no_voice_never_reaches_the_rule(
        self, client: TestClient, calls: list[tuple[str, Any]], body: dict[str, str]
    ) -> None:
        assert client.put("/voice/lia-voices", json=body).status_code == 422
        assert calls == []


@pytest.mark.parametrize("route", served_routes(module.router), ids=lambda route: route.path)
def test_no_route_holds_a_request_session_while_a_catalogue_is_read(route: Any) -> None:
    # ADR-304: a live catalogue may ask the vendor; each route authenticates on a
    # session of its own, closed before the route runs.
    def dependency_calls(dependant: Any) -> Iterator[Callable[..., Any]]:
        for dependency in dependant.dependencies:
            yield dependency.call
            yield from dependency_calls(dependency)

    assert get_db not in set(dependency_calls(route.dependant))
