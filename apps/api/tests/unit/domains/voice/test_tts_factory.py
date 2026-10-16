"""The TTS factory serves what a family declares — and never substitutes for a strict caller."""

from __future__ import annotations

from typing import Any, get_args

import pytest

from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.voice.client import EdgeTTSClient
from src.domains.voice.elevenlabs_tts_client import ElevenLabsTTSClient
from src.domains.voice.exceptions import TTSProviderError
from src.domains.voice.factory import (
    TTSConfig,
    TTSProvider,
    get_tts_client_sync,
    get_tts_config,
    serve_tts,
    served_config,
)
from src.domains.voice.families import (
    TTS_FAMILIES,
    TtsBilling,
    TtsControl,
    controls_for,
    family_of,
)
from src.domains.voice.fishaudio.tts_client import FishAudioTTSClient
from src.domains.voice.gemini_tts_client import GeminiTTSClient
from src.domains.voice.openai_tts_client import OpenAITTSClient

pytestmark = pytest.mark.unit


def config(provider: str, model: str = "m") -> TTSConfig:
    return TTSConfig(provider=provider, model=model, voice_male="a", voice_female="b")


def keys(monkeypatch: pytest.MonkeyPatch, *present: str) -> None:
    monkeypatch.setattr(
        LLMConfigOverrideCache,
        "get_api_key",
        classmethod(lambda cls, provider: "k" if provider in present else None),
    )


class TestFamilies:
    def test_every_configurable_provider_has_a_family(self) -> None:
        assert set(get_args(TTSProvider)) == set(TTS_FAMILIES)

    def test_an_unknown_provider_is_not_served(self) -> None:
        assert family_of("azure") is None

    def test_every_family_declares_the_unit_it_is_billed_in(self) -> None:
        by_billing = {f.provider: f.billing for f in TTS_FAMILIES.values()}
        assert by_billing["gemini"] is TtsBilling.TOKENS
        assert by_billing["edge"] is TtsBilling.FREE
        assert by_billing["fishaudio"] is TtsBilling.UTF8_BYTES
        assert {p for p, b in by_billing.items() if b is TtsBilling.CHARACTERS} == {
            "openai",
            "elevenlabs",
        }

    @pytest.mark.parametrize(("provider", "paid"), [("edge", False), ("gemini", True), ("x", True)])
    def test_is_paid_follows_the_family(self, provider: str, paid: bool) -> None:
        assert config(provider).is_paid is paid


class TestControlsPerModel:
    """Measured 2026-09-26 on the Interactions API: a speech annotation sent to a
    model that does not take one is a 400, and it fails the WHOLE synthesis."""

    @pytest.mark.parametrize(
        "model",
        [
            "gemini-3.8-flash-tts",
            "gemini-3.8-flash-lite-tts",
            "gemini-3.8-flash-tts-001",  # a dated release of a measured model
        ],
    )
    def test_a_gemini_model_measured_to_take_a_direction_is_directed(self, model: str) -> None:
        assert TtsControl.STYLE_PROMPT in controls_for("gemini", model)

    @pytest.mark.parametrize(
        "model",
        [
            "gemini-2.5-flash-preview-tts",
            "gemini-2.5-pro-preview-tts",
            "gemini-3.1-flash-tts-preview",
            "gemini-9-tts",  # never measured: a refused direction silences every line
        ],
    )
    def test_any_other_gemini_model_is_never_sent_a_direction(self, model: str) -> None:
        assert controls_for("gemini", model) == frozenset()

    @pytest.mark.parametrize("model", ["edge-tts", "tts-1", "eleven_v3_conversational", ""])
    def test_a_family_whose_models_all_take_a_control_ignores_the_model(self, model: str) -> None:
        for provider in ("edge", "openai", "elevenlabs"):
            family = family_of(provider)
            assert family is not None
            assert controls_for(provider, model) == family.controls

    def test_an_unknown_provider_takes_no_control(self) -> None:
        assert controls_for("azure", "anything") == frozenset()


class TestServing:
    def test_edge_is_served_without_a_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        keys(monkeypatch)
        assert isinstance(get_tts_client_sync(config("edge"), strict=True), EdgeTTSClient)

    def test_a_character_billed_engine_with_its_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        keys(monkeypatch, "openai", "elevenlabs")
        assert isinstance(get_tts_client_sync(config("openai"), strict=True), OpenAITTSClient)
        assert isinstance(
            get_tts_client_sync(config("elevenlabs"), strict=True), ElevenLabsTTSClient
        )

    async def test_a_byte_billed_engine_with_its_key_and_its_tuning(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        keys(monkeypatch, "fishaudio")
        cfg = TTSConfig(
            provider="fishaudio",
            model="s2.1-pro-free",
            voice_male="a",
            voice_female="b",
            output_format="pcm_24000",
            latency="balanced",
            speed=1.1,
        )
        client = get_tts_client_sync(cfg, strict=True)
        try:
            assert isinstance(client, FishAudioTTSClient)
            assert client.model == "s2.1-pro-free"
            assert client.audio_format == "pcm"
        finally:
            await client.close()

    @pytest.mark.parametrize("strict", [True, False])
    async def test_a_token_billed_engine_is_served_to_every_caller(
        self, monkeypatch: pytest.MonkeyPatch, strict: bool
    ) -> None:
        """Every caller records through ``speak``, which bills the tokens the
        vendor reports: the chat used to be handed Edge for a Gemini slot."""
        keys(monkeypatch, "gemini")
        client = get_tts_client_sync(config("gemini"), strict=strict)
        try:
            assert isinstance(client, GeminiTTSClient)
        finally:
            await client.close()

    @pytest.mark.parametrize(
        ("provider", "reason"),
        [
            ("openai", "api_key_missing"),
            ("gemini", "api_key_missing"),
            ("fishaudio", "api_key_missing"),
            ("azure", "no_client"),
        ],
    )
    def test_a_strict_caller_is_refused_never_substituted(
        self, monkeypatch: pytest.MonkeyPatch, provider: str, reason: str
    ) -> None:
        keys(monkeypatch)
        with pytest.raises(TTSProviderError) as caught:
            get_tts_client_sync(config(provider), strict=True)
        assert caught.value.code == "tts_unavailable"
        assert isinstance(caught.value.details, dict)
        assert caught.value.details["reason"] == reason

    @pytest.mark.parametrize("provider", ["openai", "gemini", "fishaudio", "azure"])
    def test_a_lenient_caller_keeps_speaking_through_edge(
        self, monkeypatch: pytest.MonkeyPatch, provider: str
    ) -> None:
        keys(monkeypatch)
        assert isinstance(get_tts_client_sync(config(provider)), EdgeTTSClient)

    def test_a_substituted_client_comes_with_its_own_configuration(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The configured engine's voice ids mean nothing to Edge: a caller that
        read them from the configuration it asked for heard silence."""
        keys(monkeypatch)
        served = serve_tts(config("elevenlabs", model="eleven_v4"))
        assert isinstance(served.client, EdgeTTSClient)
        assert (served.config.provider, served.config.model) == ("edge", "edge-tts")
        assert served.config.voice_female.endswith("Neural")
        assert served.config.voice_male.endswith("Neural")

    @pytest.mark.parametrize("present", [(), ("openai",)])
    async def test_the_engine_that_speaks_is_known_without_building_a_client(
        self, monkeypatch: pytest.MonkeyPatch, present: tuple[str, ...]
    ) -> None:
        # What a page offers LIA's voices from (ADR-345 amendment): the engine the
        # lenient serve builds, decided the same way.
        keys(monkeypatch, *present)
        asked = config("openai", model="tts-1")
        served = serve_tts(asked)
        try:
            assert served_config(asked) == served.config
        finally:
            await served.client.close()

    async def test_a_served_client_comes_with_the_configuration_asked_for(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        keys(monkeypatch, "openai")
        asked = config("openai", model="tts-1")
        served = serve_tts(asked)
        try:
            assert served.config is asked
            assert isinstance(served.client, OpenAITTSClient)
        finally:
            await served.client.close()


class TestConfig:
    async def test_a_slot_reads_its_own_override_and_keeps_its_blob(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        override: dict[str, Any] = {
            "provider": "gemini",
            "model": "gemini-tts",
            "provider_config": '{"voice_male": "Puck", "cast": {"host": "Kore"}}',
        }
        monkeypatch.setattr(
            LLMConfigOverrideCache,
            "get_override",
            classmethod(lambda cls, slot: override if slot == "voice_tts" else None),
        )
        cfg = await get_tts_config("voice_tts")
        assert (cfg.provider, cfg.model, cfg.voice_male) == ("gemini", "gemini-tts", "Puck")
        assert cfg.voice_female == "Kore"  # the family's default female voice
        assert cfg.extras["cast"] == {"host": "Kore"}

    async def test_a_fish_slot_reads_its_tuning_and_has_default_voices(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        override: dict[str, Any] = {
            "provider": "fishaudio",
            "model": "s2.1-pro",
            "provider_config": '{"latency": "balanced", "speed": 1.1, "output_format": "pcm_24000"}',
        }
        monkeypatch.setattr(
            LLMConfigOverrideCache,
            "get_override",
            classmethod(lambda cls, slot: override if slot == "voice_tts" else None),
        )
        cfg = await get_tts_config("voice_tts")
        assert (cfg.latency, cfg.speed, cfg.output_format) == ("balanced", 1.1, "pcm_24000")
        for voice in (cfg.voice_male, cfg.voice_female):
            assert len(voice) == 32 and int(voice, 16) >= 0  # a library model id
        assert cfg.voice_male != cfg.voice_female
