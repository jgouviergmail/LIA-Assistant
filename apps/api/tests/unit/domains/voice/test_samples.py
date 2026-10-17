"""Voice samples use the selected engine, one bounded sentence and the shared ledger."""

from __future__ import annotations

import asyncio
import base64
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.exceptions import BaseAPIException
from src.core.i18n_voice_samples import VOICE_SAMPLE_PHRASES, voice_sample_phrase
from src.domains.voice import samples
from src.domains.voice.engine_voices import EngineVoices
from src.domains.voice.exceptions import TTSProviderError
from src.domains.voice.factory import TTSConfig
from src.domains.voice.protocol import RawAudioSpec
from src.domains.voice.voices_catalog import VoiceOption

pytestmark = pytest.mark.unit
PERSON = uuid4()
MALE = VoiceOption("male", "Man", "male", "fr")
FEMALE = VoiceOption("female", "Woman", "female", "fr")
OTHER = VoiceOption("other", "Other", "male", "en")
CONFIG = TTSConfig(provider="edge", model="edge-tts", voice_male="male", voice_female="female")


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    events: list[tuple[str, object]] = []
    client = SimpleNamespace(provider_name="edge", audio_format="mp3", close=AsyncMock())
    engine = EngineVoices(CONFIG, [MALE, FEMALE, OTHER], multilingual=False)

    async def configuration(*_: Any) -> TTSConfig:
        return CONFIG

    async def catalogue(config: TTSConfig) -> EngineVoices:
        events.append(("catalogue", config))
        return engine

    def serve(config: TTSConfig, **kwargs: Any) -> Any:
        events.append(("client", kwargs))
        return SimpleNamespace(client=client)

    class Ledger:
        def __init__(self, **kwargs: Any) -> None:
            events.append(("ledger", kwargs))

        async def __aenter__(self) -> Ledger:
            return self

        async def __aexit__(self, *_: Any) -> None:
            return None

        async def commit(self) -> None:
            events.append(("commit", None))

        @classmethod
        def cleanup_run_records(cls, _: str) -> None:
            events.append(("cleanup", None))

    async def speak(*args: Any, **kwargs: Any) -> Any:
        events.append(("speak", (args, kwargs)))
        return SimpleNamespace(audio=b"ID3-audio")

    quota = AsyncMock()
    monkeypatch.setattr(samples, "get_tts_config", configuration)
    monkeypatch.setattr(samples, "served_config", lambda config: config)
    monkeypatch.setattr(samples, "serve_tts", serve)
    monkeypatch.setattr(samples, "offered_engine", catalogue)
    monkeypatch.setattr(samples, "TrackingContext", Ledger)
    monkeypatch.setattr(samples, "speak", speak)
    monkeypatch.setattr(samples, "enforce_usage_limit", quota)
    return SimpleNamespace(events=events, client=client, engine=engine, quota=quota)


async def test_chat_default_uses_requested_gender_fixed_french_phrase_and_no_free_ledger(
    world: SimpleNamespace,
) -> None:
    result = await samples.sample_lia_voice(
        user_id=PERSON, language="fr", gender="female", voice_id=None
    )
    assert result.voice_id == "female"
    args, kwargs = next(value for event, value in world.events if event == "speak")
    assert args[1:] == ("Bonjour, ceci est un échantillon de ma voix !", "female")
    assert kwargs["model"] == "edge-tts"
    assert kwargs["ledger"] is None
    world.quota.assert_not_awaited()
    world.client.close.assert_awaited_once()


async def test_explicit_voice_is_used_without_saving_preferences(world: SimpleNamespace) -> None:
    result = await samples.sample_lia_voice(
        user_id=PERSON, language="fr", gender="female", voice_id="male"
    )
    assert result.voice_id == "male"
    assert base64.b64decode(result.audio_base64) == b"ID3-audio"
    assert result.mime_type == "audio/mpeg"


@pytest.mark.parametrize("voice", ["missing", "other"])
async def test_unknown_or_wrong_language_voice_never_reaches_synthesis(
    world: SimpleNamespace,
    voice: str,
) -> None:
    with pytest.raises(BaseAPIException) as caught:
        await samples.sample_lia_voice(user_id=PERSON, language="fr", gender="male", voice_id=voice)
    assert caught.value.status_code == 422
    assert all(event != "speak" for event, _ in world.events)
    world.client.close.assert_awaited_once()


async def test_unavailable_catalogue_cannot_authorize_an_explicit_voice(
    world: SimpleNamespace,
) -> None:
    world.engine.voices.clear()
    with pytest.raises(BaseAPIException) as caught:
        await samples.sample_lia_voice(
            user_id=PERSON, language="fr", gender="male", voice_id="male"
        )
    assert caught.value.status_code == 503
    world.client.close.assert_awaited_once()


async def test_paid_sample_checks_quota_and_commits_before_audio_envelope(
    monkeypatch: pytest.MonkeyPatch,
    world: SimpleNamespace,
) -> None:
    paid = TTSConfig(provider="openai", model="tts-1", voice_male="male", voice_female="female")
    world.client.provider_name = "openai"
    world.engine = EngineVoices(paid, [MALE, FEMALE], multilingual=True)

    async def catalogue(_: TTSConfig) -> EngineVoices:
        return world.engine

    def envelope(*_: Any) -> str:
        assert any(event == "commit" for event, _ in world.events)
        return "encoded"

    monkeypatch.setattr(samples, "offered_engine", catalogue)
    monkeypatch.setattr(samples, "playable_base64", envelope)
    await samples.synthesize_sample(
        user_id=PERSON,
        language="fr",
        config=paid,
        choose=lambda _: "male",
        run_prefix="voice_sample",
    )
    world.quota.assert_awaited_once_with(PERSON, layer="voice_sample")
    assert (
        next(value for event, value in world.events if event == "ledger")["conversation_id"] is None
    )
    args, kwargs = next(value for event, value in world.events if event == "speak")
    assert kwargs["ledger"] is not None
    world.client.close.assert_awaited_once()


async def test_quota_refusal_closes_client_without_contacting_provider(
    world: SimpleNamespace,
) -> None:
    world.quota.side_effect = BaseAPIException(status_code=429, detail="quota")
    paid = TTSConfig(provider="openai", model="tts-1", voice_male="male", voice_female="female")
    with pytest.raises(BaseAPIException):
        await samples.synthesize_sample(
            user_id=PERSON,
            language="fr",
            config=paid,
            choose=lambda _: "male",
            run_prefix="voice_sample",
        )
    assert all(event != "speak" for event, _ in world.events)
    world.client.close.assert_awaited_once()


async def test_raw_pcm_is_playable_wav_with_its_own_rate(
    monkeypatch: pytest.MonkeyPatch,
    world: SimpleNamespace,
) -> None:
    world.client.audio_format = "pcm"
    world.client.raw_audio_spec = RawAudioSpec(16000)

    async def speak(*_: Any, **__: Any) -> Any:
        return SimpleNamespace(audio=b"\x00\x00\x01\x00")

    monkeypatch.setattr(samples, "speak", speak)
    result = await samples.sample_lia_voice(
        user_id=PERSON, language="fr", gender="male", voice_id=None
    )
    assert result.mime_type == "audio/wav"
    assert base64.b64decode(result.audio_base64).startswith(b"RIFF")


async def test_provider_failure_is_coded_and_never_retried(
    monkeypatch: pytest.MonkeyPatch,
    world: SimpleNamespace,
) -> None:
    provider = AsyncMock(side_effect=TTSProviderError("provider_timeout"))
    monkeypatch.setattr(samples, "speak", provider)
    with pytest.raises(BaseAPIException) as caught:
        await samples.sample_lia_voice(
            user_id=PERSON, language="fr", gender="male", voice_id="male"
        )
    assert caught.value.status_code == 503
    provider.assert_awaited_once()
    world.client.close.assert_awaited_once()


async def test_cancellation_closes_client_and_never_retries(
    monkeypatch: pytest.MonkeyPatch, world: SimpleNamespace
) -> None:
    provider = AsyncMock(side_effect=asyncio.CancelledError())
    monkeypatch.setattr(samples, "speak", provider)
    with pytest.raises(asyncio.CancelledError):
        await samples.sample_lia_voice(
            user_id=PERSON, language="fr", gender="male", voice_id="male"
        )
    provider.assert_awaited_once()
    world.client.close.assert_awaited_once()
    assert all(event != "commit" for event, _ in world.events)


async def test_key_reload_during_catalogue_keeps_client_and_catalogue_on_same_credential(
    monkeypatch: pytest.MonkeyPatch, world: SimpleNamespace
) -> None:
    from src.domains.voice import engine_voices

    current = "old-key"
    captured: list[str] = []
    paid = TTSConfig(provider="openai", model="tts-1", voice_male="male", voice_female="female")

    def serve(config: TTSConfig, **_: Any) -> Any:
        captured.append(current)
        return SimpleNamespace(client=world.client)

    async def catalogue(config: TTSConfig, *, api_key: str | None) -> list[VoiceOption]:
        nonlocal current
        assert api_key == "old-key"
        current = "new-key"
        return [MALE, FEMALE]

    monkeypatch.setattr(samples, "serve_tts", serve)
    monkeypatch.setattr(samples, "offered_engine", engine_voices.offered_engine)
    monkeypatch.setattr(engine_voices, "engine_voices", catalogue)
    monkeypatch.setattr(engine_voices.LLMConfigOverrideCache, "get_api_key", lambda _: current)
    await samples.synthesize_sample(
        user_id=PERSON,
        language="fr",
        config=paid,
        choose=lambda _: "male",
        run_prefix="voice_sample",
    )
    assert captured == ["old-key"] and current == "new-key"


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_every_account_language_has_one_fixed_sample_sentence(language: str) -> None:
    assert voice_sample_phrase(language) == VOICE_SAMPLE_PHRASES[language]
    assert 10 < len(voice_sample_phrase(language)) < 100
