"""A speech slot names a model its provider serves, of its kind, at a price its recorder reads.

Measured 2026-10-13: Fish Audio serves AND bills an unknown ``model`` header as
``s2.1-pro``. Nothing held a slot's provider and model together, so
``provider=fishaudio, model=eleven_v4`` would have spoken through Fish while LIA
priced the line at ElevenLabs' tariff. The admin form offers a provider's own
models; this is the write path's half of the promise.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import HTTPException

from src.domains.llm_config import speech_validation
from src.domains.llm_config.constants import LLM_DEFAULTS
from src.domains.llm_config.speech_validation import refuse_unserved_speech_model
from src.infrastructure.cache.pricing_cache import CachedModelPrice
from src.infrastructure.llm.model_profiles import ModelProfile

pytestmark = pytest.mark.unit

#: model → (provider, kind, pricing unit or None for unpriced)
_CATALOGUE: dict[str, tuple[str, str, str | None]] = {
    "s2.1-pro-free": ("fishaudio", "tts", "per_1m_tokens"),
    "eleven_v4": ("elevenlabs", "tts", "per_1m_tokens"),
    "edge-tts": ("edge", "tts", None),
    "scribe_v2": ("elevenlabs", "audio", "per_audio_hour"),
    "gpt-4.1": ("openai", "chat", "per_1m_tokens"),
    "unpriced-tts": ("fishaudio", "tts", None),
    "minute-tts": ("fishaudio", "tts", "per_audio_minute"),
}


@pytest.fixture(autouse=True)
def catalogue(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    cache = speech_validation.ModelCapabilitiesCache

    def get(model: str) -> ModelProfile | None:
        entry = _CATALOGUE.get(model)
        return None if entry is None else ModelProfile(model_id=model, kind=entry[1])

    def provider_of(model: str) -> str | None:
        entry = _CATALOGUE.get(model)
        return None if entry is None else entry[0]

    def price_of(model: str) -> CachedModelPrice | None:
        entry = _CATALOGUE.get(model)
        if entry is None or entry[2] is None:
            return None
        return CachedModelPrice(
            input_unit_price=1.0,
            output_unit_price=0.0,
            cached_input_unit_price=1.0,
            pricing_unit=entry[2],
        )

    monkeypatch.setattr(cache, "is_loaded", classmethod(lambda cls: True))
    monkeypatch.setattr(cache, "get", classmethod(lambda cls, model: get(model)))
    monkeypatch.setattr(cache, "get_provider", classmethod(lambda cls, model: provider_of(model)))
    monkeypatch.setattr(speech_validation, "is_cache_initialized", lambda: True)
    monkeypatch.setattr(speech_validation, "get_cached_model_price", price_of)
    yield


def refusal(llm_type: str, provider: str | None, model: str | None) -> dict[str, Any]:
    with pytest.raises(HTTPException) as caught:
        refuse_unserved_speech_model(llm_type, provider, model)
    assert caught.value.status_code == 422
    detail = caught.value.detail
    assert isinstance(detail, dict)
    return detail


class TestAcceptedConfigurations:
    @pytest.mark.parametrize(
        ("llm_type", "provider", "model"),
        [
            ("voice_tts", "fishaudio", "s2.1-pro-free"),
            ("radio_voice", "elevenlabs", "eleven_v4"),
            ("voice_tts", "edge", "edge-tts"),  # the free engine needs no tariff
            ("voice_transcription", "elevenlabs", "scribe_v2"),
        ],
    )
    def test_a_coherent_choice_passes(self, llm_type: str, provider: str, model: str) -> None:
        refuse_unserved_speech_model(llm_type, provider, model)

    @pytest.mark.parametrize("provider", [None, LLM_DEFAULTS["voice_tts"].provider])
    def test_a_model_left_to_the_default_keeps_its_default_provider(
        self, provider: str | None
    ) -> None:
        refuse_unserved_speech_model("voice_tts", provider, None)

    def test_a_chat_slot_is_not_this_rules(self) -> None:
        refuse_unserved_speech_model("response", "fishaudio", "s2.1-pro-free")

    def test_without_evidence_nothing_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            speech_validation.ModelCapabilitiesCache, "is_loaded", classmethod(lambda cls: False)
        )
        refuse_unserved_speech_model("voice_tts", "fishaudio", "nothing-known")

    def test_an_omitted_provider_is_the_slots_default(self) -> None:
        """The slot's default provider is Edge: an Edge model with no provider passes."""
        refuse_unserved_speech_model("voice_tts", None, "edge-tts")


class TestRefusals:
    @pytest.mark.parametrize("loaded", [False, True])
    def test_switching_provider_cannot_inherit_the_other_providers_default_model(
        self,
        monkeypatch: pytest.MonkeyPatch,
        loaded: bool,
    ) -> None:
        default = LLM_DEFAULTS["voice_tts"]
        provider = "fishaudio" if default.provider != "fishaudio" else "edge"
        monkeypatch.setattr(
            speech_validation.ModelCapabilitiesCache, "is_loaded", classmethod(lambda cls: loaded)
        )
        detail = refusal("voice_tts", provider, None)
        assert detail["type"] == "model_provider_mismatch"
        assert detail["ctx"] == {"model": default.model, "provider": default.provider}

    def test_an_unknown_model(self) -> None:
        detail = refusal("voice_tts", "fishaudio", "s9-ultra")
        assert detail["type"] == "unknown_model"
        assert detail["ctx"] == {"model": "s9-ultra"}

    def test_a_model_of_another_provider(self) -> None:
        detail = refusal("voice_tts", "fishaudio", "eleven_v4")
        assert detail["type"] == "model_provider_mismatch"
        assert detail["ctx"] == {"model": "eleven_v4", "provider": "elevenlabs"}

    def test_a_model_of_another_kind(self) -> None:
        detail = refusal("voice_tts", "openai", "gpt-4.1")
        assert detail["type"] == "model_kind_mismatch"
        assert detail["ctx"] == {"model": "gpt-4.1", "kind": "chat", "required_kind": "tts"}

    def test_a_transcription_model_for_synthesis(self) -> None:
        assert refusal("radio_voice", "elevenlabs", "scribe_v2")["type"] == "model_kind_mismatch"

    def test_a_tariff_its_recorder_cannot_read(self) -> None:
        """A synthesis is priced per million billed units; a per-minute row prices it at zero."""
        detail = refusal("voice_tts", "fishaudio", "minute-tts")
        assert detail["type"] == "model_pricing_unit_mismatch"
        assert detail["ctx"] == {"model": "minute-tts", "pricing_unit": "per_audio_minute"}

    def test_a_transcription_tariff_per_million_units_is_unreadable_too(self) -> None:
        _CATALOGUE["token-stt"] = ("elevenlabs", "audio", "per_1m_tokens")
        try:
            detail = refusal("voice_transcription", "elevenlabs", "token-stt")
        finally:
            del _CATALOGUE["token-stt"]
        assert detail["type"] == "model_pricing_unit_mismatch"

    def test_a_model_with_no_tariff_is_not_this_rules_to_refuse(self) -> None:
        """Free engine or unpriced one: only the voice families can tell (absence of evidence)."""
        refuse_unserved_speech_model("voice_tts", "fishaudio", "unpriced-tts")

    def test_a_cold_pricing_cache_refuses_nothing_on_price(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(speech_validation, "is_cache_initialized", lambda: False)
        refuse_unserved_speech_model("voice_tts", "fishaudio", "minute-tts")
