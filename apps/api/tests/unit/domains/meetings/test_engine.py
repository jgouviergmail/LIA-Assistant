"""Engine resolution (ADR-258): slot provider first, then any provider with a key, then local."""

from __future__ import annotations

import pytest

from src.core.constants import (
    DEFAULT_ELEVENLABS_STT_MODEL,
    OPENAI_STT_DIARIZE_MODEL_DEFAULT,
)
from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.meetings import engine as eng
from src.domains.meetings.models import MeetingSttEnginePreference, MeetingSttProvider

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _cache(monkeypatch: pytest.MonkeyPatch):
    LLMConfigOverrideCache.reset()
    LLMConfigOverrideCache._overrides = {}
    LLMConfigOverrideCache._loaded = True
    # Pricing cache untouched: unknown price → None, the honest answer.
    monkeypatch.setattr(eng, "get_cached_cost_audio_usd_eur", lambda model, seconds: (0.0, 0.0))
    yield
    LLMConfigOverrideCache.reset()


def _keys(**keys: str) -> None:
    LLMConfigOverrideCache._provider_keys = dict(keys)


def test_auto_prefers_the_slot_provider_when_it_has_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _keys(elevenlabs="sk_x", openai="sk-y")
    resolved = eng.resolve_engine(MeetingSttEnginePreference.AUTO)
    assert resolved is not None
    assert resolved.provider is MeetingSttProvider.ELEVENLABS
    assert resolved.model == DEFAULT_ELEVENLABS_STT_MODEL
    assert resolved.diarized is True
    assert resolved.api_key == "sk_x"
    assert resolved.cost_per_hour_eur is None  # no pricing row → unknown, never 0


def test_auto_falls_back_to_openai_when_elevenlabs_has_no_key() -> None:
    _keys(openai="sk-y")
    resolved = eng.resolve_engine(MeetingSttEnginePreference.AUTO)
    assert resolved is not None
    assert resolved.provider is MeetingSttProvider.OPENAI
    assert resolved.model == OPENAI_STT_DIARIZE_MODEL_DEFAULT


def test_auto_falls_back_to_local_when_no_provider_has_a_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _keys()
    monkeypatch.setattr(eng.settings, "voice_stt_enabled", True)
    monkeypatch.setattr(eng.settings, "meetings_local_rtf_estimate", 2.5)
    resolved = eng.resolve_engine(MeetingSttEnginePreference.AUTO)
    assert resolved is not None
    assert resolved.provider is MeetingSttProvider.LOCAL
    assert resolved.diarized is False
    assert resolved.local_rtf_estimate == 2.5
    assert resolved.api_key is None


def test_the_kill_switch_skips_elevenlabs(monkeypatch: pytest.MonkeyPatch) -> None:
    _keys(elevenlabs="sk_x", openai="sk-y")
    monkeypatch.setattr(eng.settings, "elevenlabs_stt_enabled", False)
    resolved = eng.resolve_engine(MeetingSttEnginePreference.AUTO)
    assert resolved is not None and resolved.provider is MeetingSttProvider.OPENAI


def test_remote_never_falls_back_to_local(monkeypatch: pytest.MonkeyPatch) -> None:
    _keys()
    monkeypatch.setattr(eng.settings, "voice_stt_enabled", True)
    assert eng.resolve_engine(MeetingSttEnginePreference.REMOTE) is None


def test_local_never_calls_a_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    _keys(elevenlabs="sk_x")
    monkeypatch.setattr(eng.settings, "voice_stt_enabled", True)
    resolved = eng.resolve_engine(MeetingSttEnginePreference.LOCAL)
    assert resolved is not None and resolved.provider is MeetingSttProvider.LOCAL
    monkeypatch.setattr(eng.settings, "voice_stt_enabled", False)
    assert eng.resolve_engine(MeetingSttEnginePreference.LOCAL) is None


def test_the_slot_model_is_honoured_for_its_provider() -> None:
    _keys(openai="sk-y")
    LLMConfigOverrideCache._overrides = {
        "voice_transcription": {"provider": "openai", "model": "gpt-4o-transcribe"}
    }
    resolved = eng.resolve_engine(MeetingSttEnginePreference.AUTO)
    assert resolved is not None
    assert (resolved.provider, resolved.model) == (MeetingSttProvider.OPENAI, "gpt-4o-transcribe")


def test_an_excluded_provider_is_skipped_and_the_chain_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _keys(elevenlabs="key_id", openai="sk-y")
    monkeypatch.setattr(eng.settings, "voice_stt_enabled", True)
    monkeypatch.setattr(eng.settings, "meetings_local_rtf_estimate", 1.5)
    after_elevenlabs = eng.resolve_engine(
        MeetingSttEnginePreference.AUTO, exclude=frozenset({MeetingSttProvider.ELEVENLABS})
    )
    assert after_elevenlabs is not None and after_elevenlabs.provider is MeetingSttProvider.OPENAI
    after_both = eng.resolve_engine(
        MeetingSttEnginePreference.AUTO,
        exclude=frozenset({MeetingSttProvider.ELEVENLABS, MeetingSttProvider.OPENAI}),
    )
    assert after_both is not None and after_both.provider is MeetingSttProvider.LOCAL
    # `remote` never falls to the local engine, even with every provider excluded.
    assert (
        eng.resolve_engine(
            MeetingSttEnginePreference.REMOTE,
            exclude=frozenset({MeetingSttProvider.ELEVENLABS, MeetingSttProvider.OPENAI}),
        )
        is None
    )
    # `local` excluded → nothing left.
    assert (
        eng.resolve_engine(
            MeetingSttEnginePreference.LOCAL, exclude=frozenset({MeetingSttProvider.LOCAL})
        )
        is None
    )
