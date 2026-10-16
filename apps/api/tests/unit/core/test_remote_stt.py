"""Which remote engine transcribes, decided once (ADR-345).

Before: the voice mode's « remote » was ElevenLabs whatever the administrator
chose — available when an ElevenLabs key existed, billed under ElevenLabs —
while the meetings read the slot. Every reader now asks one resolution: the
``voice_transcription`` slot's provider, its kill switch, its key.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from src.core.config import settings
from src.core.remote_stt import remote_stt_enabled, remote_stt_ready, remote_stt_slot
from src.domains.llm_config.cache import LLMConfigOverrideCache

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clean_cache() -> Iterator[None]:
    LLMConfigOverrideCache.reset()
    yield
    LLMConfigOverrideCache.reset()


def _slot(provider: str, model: str, keys: dict[str, str]) -> None:
    LLMConfigOverrideCache._overrides = {
        "voice_transcription": {"provider": provider, "model": model}
    }
    LLMConfigOverrideCache._provider_keys = dict(keys)
    LLMConfigOverrideCache._loaded = True


def test_the_slot_names_who_receives_the_audio() -> None:
    _slot("fishaudio", "transcribe-1-pro", {"fishaudio": "sk"})

    slot = remote_stt_slot()

    assert (slot.provider, slot.model) == ("fishaudio", "transcribe-1-pro")


def test_remote_is_ready_on_the_slots_key_not_on_another_providers() -> None:
    """An ElevenLabs key no longer makes a Fish Audio slot « available »."""
    _slot("fishaudio", "transcribe-1-pro", {"elevenlabs": "sk-eleven"})
    assert not remote_stt_ready()

    LLMConfigOverrideCache._provider_keys["fishaudio"] = "sk-fish"
    assert remote_stt_ready()


@pytest.mark.parametrize(
    ("provider", "switch"),
    [("fishaudio", "fishaudio_stt_enabled"), ("elevenlabs", "elevenlabs_stt_enabled")],
)
def test_a_providers_kill_switch_turns_its_remote_off(
    monkeypatch: pytest.MonkeyPatch, provider: str, switch: str
) -> None:
    _slot(provider, "model", {provider: "sk"})
    monkeypatch.setattr(settings, switch, False)

    assert not remote_stt_enabled(provider)
    assert not remote_stt_ready()


def test_openai_has_no_switch_and_an_unserved_provider_is_never_enabled() -> None:
    assert remote_stt_enabled("openai")
    assert not remote_stt_enabled("anthropic")
