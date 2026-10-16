"""The admin voice picker's catalogue: Fish Audio's own, pinned and licensed voices (ADR-345)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.voice import admin_router
from src.domains.voice.fishaudio.voices import FishVoicesError
from src.domains.voice.voices_catalog import VoiceOption
from tests._routes import served_routes

pytestmark = pytest.mark.unit

PINNED = "b" * 32


def make_client(*, superuser: bool = True) -> TestClient:
    app = FastAPI()
    app.include_router(admin_router.router)
    app.dependency_overrides[get_current_active_session_for_stream] = lambda: SimpleNamespace(
        id=uuid4(), is_superuser=superuser
    )
    return TestClient(app)


@pytest.fixture
def pin_reads(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every read of the instance's pins (it holds one, ``PINNED``)."""
    reads: list[str] = []

    async def read_pins() -> tuple[str, ...]:
        reads.append("read")
        return (PINNED,)

    monkeypatch.setattr(admin_router, "read_pins", read_pins)
    monkeypatch.setattr(
        LLMConfigOverrideCache,
        "get_api_key",
        classmethod(lambda cls, provider: "fish-key" if provider == "fishaudio" else None),
    )
    return reads


@pytest.fixture
def client(pin_reads: list[str]) -> Iterator[TestClient]:
    with make_client() as test_client:
        yield test_client


def catalogue(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, tuple[str, ...]]]:
    calls: list[tuple[str, tuple[str, ...]]] = []

    async def get_fish_voices(api_key: str, pinned: Any) -> list[VoiceOption]:
        calls.append((api_key, tuple(pinned)))
        return [
            VoiceOption("a" * 32, "Own", "female", "fr", {"source": "own"}),
            VoiceOption(PINNED, "Pinned", "male", "en", {"source": "pinned"}),
        ]

    monkeypatch.setattr(admin_router, "get_fish_voices", get_fish_voices)
    return calls


class TestOnlyAnAdministrator:
    def test_anyone_else_is_refused_before_a_vendor_is_asked(
        self, pin_reads: list[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = catalogue(monkeypatch)
        with make_client(superuser=False) as test_client:
            listing = test_client.get("/admin/voice/voices", params={"provider": "fishaudio"})
            lookup = test_client.get(f"/admin/voice/fishaudio/voices/{PINNED}")
        assert (listing.status_code, lookup.status_code) == (403, 403)
        assert (calls, pin_reads) == ([], [])

    @pytest.mark.parametrize(
        "route", served_routes(admin_router.router), ids=lambda route: route.path
    )
    def test_no_route_holds_a_request_session_while_a_vendor_answers(self, route: Any) -> None:
        # ADR-304: the request session would stay ``idle in transaction`` across
        # the vendor's listing. Each route authenticates on a session of its own.
        def calls(dependant: Any) -> Iterator[Callable[..., Any]]:
            for dependency in dependant.dependencies:
                yield dependency.call
                yield from calls(dependency)

        assert get_db not in set(calls(route.dependant))


class TestTheFishCatalogue:
    def test_voices_come_with_their_source_and_the_instance_s_pins(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = catalogue(monkeypatch)
        response = client.get("/admin/voice/voices", params={"provider": "fishaudio"})
        assert response.status_code == 200
        body = response.json()
        assert (body["provider"], body["source"]) == ("fishaudio", "live")
        assert [(v["voice_id"][0], v["source"]) for v in body["voices"]] == [
            ("a", "own"),
            ("b", "pinned"),
        ]
        assert calls == [("fish-key", (PINNED,))]

    def test_the_pins_are_the_instance_s_never_the_caller_s(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # One list for every voice slot: a form cannot ask for pins of its own.
        calls = catalogue(monkeypatch)
        client.get("/admin/voice/voices", params={"provider": "fishaudio", "pinned": ["c" * 32]})
        assert calls == [("fish-key", (PINNED,))]

    def test_without_a_key_the_listing_says_so_without_reading_the_pins(
        self, client: TestClient, pin_reads: list[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            LLMConfigOverrideCache, "get_api_key", classmethod(lambda cls, provider: None)
        )
        response = client.get("/admin/voice/voices", params={"provider": "fishaudio"})
        assert response.status_code == 400
        assert pin_reads == []

    def test_a_vendor_failure_is_an_upstream_error(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def failing(api_key: str, pinned: Any) -> list[VoiceOption]:
            raise FishVoicesError("refused", details={"status_code": 401, "vendor_code": None})

        monkeypatch.setattr(admin_router, "get_fish_voices", failing)
        response = client.get("/admin/voice/voices", params={"provider": "fishaudio"})
        assert response.status_code >= 500


class TestOneVoice:
    def test_a_voice_to_pin_is_read_as_a_pin(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fetch(api_key: str, voice_id: str) -> VoiceOption:
            return VoiceOption(voice_id, "Narrator", "male", "en", {"source": "pinned"})

        monkeypatch.setattr(admin_router, "fetch_fish_voice", fetch)
        response = client.get(f"/admin/voice/fishaudio/voices/{PINNED}")
        assert response.status_code == 200
        assert response.json() == {
            "voice_id": PINNED,
            "label": "Narrator",
            "gender": "male",
            "language": "en",
            "source": "pinned",
        }

    def test_a_voice_that_cannot_speak_is_refused_by_name(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fetch(api_key: str, voice_id: str) -> None:
            return None

        monkeypatch.setattr(admin_router, "fetch_fish_voice", fetch)
        response = client.get(f"/admin/voice/fishaudio/voices/{PINNED}")
        assert response.status_code == 422
        assert response.json()["detail"]["type"] == "fishaudio_voice_unavailable"

    def test_a_malformed_id_never_reaches_the_vendor(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        called: list[str] = []

        async def fetch(api_key: str, voice_id: str) -> None:
            called.append(voice_id)

        monkeypatch.setattr(admin_router, "fetch_fish_voice", fetch)
        response = client.get("/admin/voice/fishaudio/voices/UPPERCASE")
        assert response.status_code == 422
        assert response.json()["detail"]["type"] == "fishaudio_voice_id_malformed"
        assert called == []
