"""Unit tests for the STT backend factory.

Validates the routing between Sherpa (local) and ElevenLabs (remote), the
provider-config base URL fallback, and the explicit error raised when the
remote provider is selected without an API key configured.
"""

from __future__ import annotations

import pytest

from src.core.constants import DEFAULT_ELEVENLABS_BASE_URL
from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.voice.stt.elevenlabs_stt import ElevenLabsSttService
from src.domains.voice.stt.exceptions import STTProviderError
from src.domains.voice.stt.factory import (
    _resolve_remote_base_url,
    get_stt_service_for_mode,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    """Ensure each test starts from a clean ``LLMConfigOverrideCache``."""
    LLMConfigOverrideCache.reset()
    yield
    LLMConfigOverrideCache.reset()


def _seed_cache(api_key: str | None, override: dict | None = None) -> None:
    """Manually populate the cache without hitting the DB."""
    LLMConfigOverrideCache._provider_keys = {"elevenlabs": api_key} if api_key is not None else {}
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
