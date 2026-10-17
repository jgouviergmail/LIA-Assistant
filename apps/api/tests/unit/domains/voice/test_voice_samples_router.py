"""Settings samples speak a bounded sentence, without changing either preference."""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.auth import dependencies as auth_dependencies
from src.domains.feature_switches import guard
from src.domains.radio import router as radio_router
from src.domains.voice import lia_voices_router

pytestmark = pytest.mark.unit
PERSON = uuid4()


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any]]]:
    seen: list[tuple[str, dict[str, Any]]] = []

    async def sample_chat(**kwargs: Any) -> dict[str, str]:
        seen.append(("chat", kwargs))
        return {"voice_id": "chat-female", "audio_base64": "UklGRg==", "mime_type": "audio/wav"}

    async def sample_radio(**kwargs: Any) -> dict[str, str]:
        seen.append(("radio", kwargs))
        return {"voice_id": "radio-auto", "audio_base64": "SUQz", "mime_type": "audio/mpeg"}

    async def enabled(*_: Any) -> bool:
        return True

    async def limiter() -> Any:
        async def acquire(**_: Any) -> bool:
            return True

        return SimpleNamespace(acquire=acquire)

    monkeypatch.setattr(lia_voices_router, "sample_lia_voice", sample_chat, raising=False)
    monkeypatch.setattr(radio_router, "sample_radio_voice", sample_radio, raising=False)
    monkeypatch.setattr(guard, "is_capability_enabled", enabled)
    monkeypatch.setattr(auth_dependencies, "get_rate_limiter", limiter)
    return seen


@pytest.fixture
def client(calls: list[tuple[str, dict[str, Any]]]) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(lia_voices_router.router)
    app.include_router(radio_router.router)
    app.dependency_overrides[get_current_active_session_for_stream] = lambda: SimpleNamespace(
        id=PERSON, language="fr-FR"
    )
    with TestClient(app) as browser:
        yield browser


def test_chat_selection_samples_the_requested_gender_and_null_default(
    client: TestClient, calls: list[tuple[str, dict[str, Any]]]
) -> None:
    response = client.post("/voice/lia-voices/sample", json={"gender": "female", "voice_id": None})
    assert response.status_code == 200
    assert response.json() == {
        "voice_id": "chat-female",
        "audio_base64": "UklGRg==",
        "mime_type": "audio/wav",
    }
    assert calls == [
        ("chat", {"user_id": PERSON, "language": "fr", "gender": "female", "voice_id": None})
    ]


def test_radio_auto_uses_the_whole_current_cast_including_commentators(
    client: TestClient, calls: list[tuple[str, dict[str, Any]]]
) -> None:
    response = client.post(
        "/radio/voices/sample",
        json={"role": "speaker_b", "voices": {"host": "host-new", "speaker_a": "guest"}},
    )
    assert response.status_code == 200
    assert response.json()["voice_id"] == "radio-auto"
    assert str(calls[0][1]["role"]) == "speaker_b"
    assert calls[0][1]["voices"] == {"host": "host-new", "speaker_a": "guest"}
    assert calls[0][1]["language"] == "fr"


@pytest.mark.parametrize(
    "url,body",
    [
        ("/voice/lia-voices/sample", {"gender": "female", "voice_id": "ok", "text": "arbitrary"}),
        ("/voice/lia-voices/sample", {"gender": "other", "voice_id": "ok"}),
        ("/voice/lia-voices/sample", {"gender": "male", "voice_id": "   "}),
        ("/radio/voices/sample", {"role": "unknown", "voices": {}}),
        ("/radio/voices/sample", {"role": "host", "voices": {"host": ""}}),
        ("/radio/voices/sample", {"role": "host", "voices": {}, "api_key": "client-key"}),
    ],
)
def test_samples_never_accept_arbitrary_text_keys_or_unbounded_selections(
    client: TestClient, calls: list[tuple[str, dict[str, Any]]], url: str, body: dict[str, Any]
) -> None:
    assert client.post(url, json=body).status_code == 422
    assert calls == []


def test_both_surfaces_share_the_same_user_rate_limit(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, calls: list[tuple[str, dict[str, Any]]]
) -> None:
    attempts: list[dict[str, Any]] = []

    async def limiter() -> Any:
        async def acquire(**kwargs: Any) -> bool:
            attempts.append(kwargs)
            return len(attempts) <= 12

        return SimpleNamespace(acquire=acquire)

    monkeypatch.setattr(auth_dependencies, "get_rate_limiter", limiter)
    for _ in range(6):
        assert client.post("/voice/lia-voices/sample", json={"gender": "male"}).status_code == 200
        assert (
            client.post("/radio/voices/sample", json={"role": "host", "voices": {}}).status_code
            == 200
        )
    response = client.post("/radio/voices/sample", json={"role": "host", "voices": {}})
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    assert len(calls) == 12
    assert {attempt["key"] for attempt in attempts} == {f"auth:voice_sample:user:{PERSON}"}
    assert all(
        attempt["max_calls"] == 12 and attempt["window_seconds"] == 60 for attempt in attempts
    )


def test_samples_require_an_authenticated_account(client: TestClient) -> None:
    from src.core.exceptions import AuthenticationError

    async def anonymous() -> None:
        raise AuthenticationError()

    client.app.dependency_overrides[get_current_active_session_for_stream] = anonymous
    assert client.post("/voice/lia-voices/sample", json={"gender": "male"}).status_code == 401
    assert client.post("/radio/voices/sample", json={"role": "host"}).status_code == 401


@pytest.mark.parametrize(
    "url,body",
    [
        ("/voice/lia-voices/sample", {"gender": "male", "voice_id": "ok"}),
        ("/radio/voices/sample", {"role": "host", "voices": {}}),
    ],
)
def test_disabled_surface_never_synthesizes(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    calls: list[tuple[str, dict[str, Any]]],
    url: str,
    body: dict[str, Any],
) -> None:
    async def disabled(*_: Any) -> bool:
        return False

    monkeypatch.setattr(guard, "is_capability_enabled", disabled)
    assert client.post(url, json=body).status_code == 403
    assert calls == []
