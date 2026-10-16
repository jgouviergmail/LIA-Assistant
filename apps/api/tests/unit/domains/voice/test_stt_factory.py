"""Unit tests for the STT backend factory.

Validates the routing between Sherpa (local) and the remote engine of the
``voice_transcription`` slot — its PROVIDER decides, never a hard-coded one
(ADR-345: a slot set to OpenAI used to send OpenAI's model name to ElevenLabs) —,
the provider-config base URL fallback, and the explicit error raised when the
remote provider is selected without an API key configured.
"""

from __future__ import annotations

import pytest

from src.core.constants import DEFAULT_ELEVENLABS_BASE_URL
from src.core.remote_stt import REMOTE_STT_PROVIDERS, remote_stt_slot
from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.voice.stt.elevenlabs_stt import ElevenLabsSttService
from src.domains.voice.stt.exceptions import STTProviderError
from src.domains.voice.stt.factory import (
    _resolve_remote_base_url,
    build_remote_stt,
    get_stt_service_for_mode,
)
from src.domains.voice.stt.fishaudio_stt import FishAudioSttService
from src.domains.voice.stt.openai_stt import OpenAISttService


@pytest.fixture(autouse=True)
def _reset_cache():
    """Ensure each test starts from a clean ``LLMConfigOverrideCache``."""
    LLMConfigOverrideCache.reset()
    yield
    LLMConfigOverrideCache.reset()


def _seed_cache(
    api_key: str | None, override: dict | None = None, *, provider: str = "elevenlabs"
) -> None:
    """Manually populate the cache without hitting the DB."""
    LLMConfigOverrideCache._provider_keys = {provider: api_key} if api_key is not None else {}
    LLMConfigOverrideCache._overrides = {"voice_transcription": override} if override else {}
    LLMConfigOverrideCache._loaded = True


# ----------------------------------------------------------------------
# Local branch
# ----------------------------------------------------------------------


def test_local_mode_returns_sherpa_singleton(monkeypatch):
    """``mode='local'`` returns the Sherpa singleton without DB lookups."""
    sentinel = object()
    monkeypatch.setattr(
        "src.domains.voice.stt.factory.get_stt_service",
        lambda: sentinel,
    )

    result = get_stt_service_for_mode("local")
    assert result is sentinel


# ----------------------------------------------------------------------
# Remote branch
# ----------------------------------------------------------------------


def test_remote_mode_missing_key_raises(monkeypatch):
    """No ElevenLabs API key in the cache → ``elevenlabs_api_key_missing``."""
    _seed_cache(api_key=None)

    with pytest.raises(STTProviderError) as exc:
        get_stt_service_for_mode("remote")
    assert exc.value.code == "elevenlabs_api_key_missing"


def test_remote_mode_returns_elevenlabs_service():
    _seed_cache(api_key="sk-test")
    service = get_stt_service_for_mode("remote")
    assert isinstance(service, ElevenLabsSttService)
    assert service._api_key == "sk-test"
    # Default model from LLM_DEFAULTS.
    assert service._model == "scribe_v2"
    # No provider_config override → DEFAULT_ELEVENLABS_BASE_URL.
    assert service._base_url == DEFAULT_ELEVENLABS_BASE_URL


def test_remote_mode_custom_base_url_via_provider_config():
    _seed_cache(
        api_key="sk-test",
        override={"provider_config": '{"base_url": "https://api.eu.residency.elevenlabs.io"}'},
    )
    service = get_stt_service_for_mode("remote")
    assert service._base_url == "https://api.eu.residency.elevenlabs.io"


def test_remote_mode_model_override():
    _seed_cache(api_key="sk-test", override={"model": "scribe_v1"})
    service = get_stt_service_for_mode("remote")
    assert service._model == "scribe_v1"


# ----------------------------------------------------------------------
# _resolve_remote_base_url helper
# ----------------------------------------------------------------------


def test_resolve_base_url_none_returns_default():
    assert _resolve_remote_base_url(None) == DEFAULT_ELEVENLABS_BASE_URL


def test_resolve_base_url_empty_returns_default():
    assert _resolve_remote_base_url("") == DEFAULT_ELEVENLABS_BASE_URL


def test_resolve_base_url_invalid_json_returns_default():
    assert _resolve_remote_base_url("not-json") == DEFAULT_ELEVENLABS_BASE_URL


def test_resolve_base_url_no_key_returns_default():
    assert _resolve_remote_base_url('{"timeout": 30}') == DEFAULT_ELEVENLABS_BASE_URL


def test_resolve_base_url_extracts_value():
    result = _resolve_remote_base_url('{"base_url": "https://custom.example/v1"}')
    assert result == "https://custom.example/v1"


def test_resolve_base_url_strips_whitespace():
    result = _resolve_remote_base_url('{"base_url": "  https://x.example/v1  "}')
    assert result == "https://x.example/v1"


# ----------------------------------------------------------------------
# The slot's provider decides (ADR-345)
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("provider", "model", "engine"),
    [
        ("fishaudio", "transcribe-1-pro", FishAudioSttService),
        ("openai", "gpt-4o-mini-transcribe", OpenAISttService),
    ],
)
def test_remote_mode_builds_the_slots_own_engine(provider: str, model: str, engine: type) -> None:
    _seed_cache("sk-test", {"provider": provider, "model": model}, provider=provider)

    service = get_stt_service_for_mode("remote")

    assert isinstance(service, engine)
    assert service._model == model


def test_the_missing_key_named_is_the_slots_providers() -> None:
    _seed_cache("sk-eleven", {"provider": "fishaudio", "model": "transcribe-1"})

    with pytest.raises(STTProviderError) as exc:
        get_stt_service_for_mode("remote")

    assert exc.value.code == "fishaudio_api_key_missing"


def test_a_slot_naming_no_remote_engine_is_a_classified_defect() -> None:
    _seed_cache("sk-test", {"provider": "anthropic", "model": "claude"}, provider="anthropic")

    with pytest.raises(STTProviderError) as exc:
        get_stt_service_for_mode("remote")

    assert exc.value.code == "provider_unknown"


def test_the_slot_a_caller_read_is_the_one_transcribing() -> None:
    """The voice WebSocket files the cost under the slot it read: the factory
    must transcribe with that same slot, never re-read one that moved."""
    _seed_cache("sk-test", {"provider": "fishaudio", "model": "transcribe-1"}, provider="fishaudio")
    read = remote_stt_slot()
    _seed_cache(
        "sk-test", {"provider": "openai", "model": "gpt-4o-mini-transcribe"}, provider="openai"
    )
    LLMConfigOverrideCache._provider_keys["fishaudio"] = "sk-fish"

    service = get_stt_service_for_mode("remote", slot=read)

    assert isinstance(service, FishAudioSttService)


@pytest.mark.parametrize("provider", REMOTE_STT_PROVIDERS)
def test_every_declared_remote_engine_is_one_the_factory_builds(provider: str) -> None:
    """The declaration readers trust (core) and the engines the factory builds stay one list."""
    service = build_remote_stt(provider, api_key="sk", model="m", timeout_seconds=5.0)

    assert hasattr(service, "transcribe_pcm_int16_async")
    assert hasattr(service, "transcribe_file_async")
