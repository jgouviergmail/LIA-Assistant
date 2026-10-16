"""The voices of a speech engine, as a person may be offered them (ADR-324, ADR-345)."""

from __future__ import annotations

import pytest

from src.core.constants import SUPPORTED_LANGUAGES
from src.core.i18n_types import canonical_language
from src.domains.voice import engine_voices as module
from src.domains.voice.engine_voices import (
    KNOWN_LIVE_CATALOGUES,
    LIVE_CATALOGUES,
    EngineVoices,
    choice_key,
    engine_voices,
    holds_choice_of,
    known_engine,
    offered_engine,
    stored_choice,
    usable_voices,
)
from src.domains.voice.factory import TTSConfig
from src.domains.voice.fishaudio.voices import FishVoicesError
from src.domains.voice.voices_catalog import ElevenLabsVoicesError, VoiceOption, get_edge_voices

pytestmark = pytest.mark.unit

VOICE = VoiceOption(voice_id="v1", label="One", gender="female", language="en")


def config(provider: str, **extras: object) -> TTSConfig:
    return TTSConfig(provider=provider, model="m", voice_male="a", voice_female="b", extras=extras)


class TestTheCatalogue:
    async def test_a_shipped_list_is_the_engine_s_voices(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(module.STATIC_CATALOGUES, "edge", lambda: [VOICE])

        assert await engine_voices(config("edge")) == [VOICE]

    async def test_a_provider_no_catalogue_serves_offers_none(self) -> None:
        assert await engine_voices(config("nobody")) == []

    async def test_a_live_list_that_fails_offers_no_voice_rather_than_raising(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def unavailable(api_key: str, base_url: str) -> list[VoiceOption]:
            raise ElevenLabsVoicesError("vendor says no")

        monkeypatch.setattr(module, "get_cached_elevenlabs_voices", unavailable)

        assert await engine_voices(config("elevenlabs")) == []

    async def test_a_fish_engine_reads_its_account_s_voices_with_the_instance_s_pins(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pinned = "b" * 32
        asked: list[tuple[str, tuple[str, ...]]] = []

        async def fish_voices(api_key: str, pins: tuple[str, ...]) -> list[VoiceOption]:
            asked.append((api_key, pins))
            return [VOICE]

        async def pins() -> tuple[str, ...]:
            return (pinned,)

        monkeypatch.setattr(
            module.LLMConfigOverrideCache, "get_api_key", classmethod(lambda cls, p: "fish-key")
        )
        monkeypatch.setattr(module, "read_pins", pins)
        monkeypatch.setattr(module, "get_fish_voices", fish_voices)

        # A slot that still carries the key it held before the shared list reads nothing from it.
        voices = await engine_voices(config("fishaudio", pinned_voices=["e" * 32]))

        assert voices == [VOICE]
        assert asked == [("fish-key", (pinned,))]

    async def test_a_fish_list_that_fails_offers_no_voice(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def unavailable(api_key: str, pins: tuple[str, ...]) -> list[VoiceOption]:
            raise FishVoicesError("vendor says no")

        async def no_pins() -> tuple[str, ...]:
            return ()

        monkeypatch.setattr(module, "read_pins", no_pins)
        monkeypatch.setattr(module, "get_fish_voices", unavailable)

        assert await engine_voices(config("fishaudio")) == []


class TestTheEngine:
    async def test_an_edge_voice_speaks_its_own_language(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(module.STATIC_CATALOGUES, "edge", lambda: [VOICE])

        engine = await offered_engine(config("edge"))

        assert engine == EngineVoices(config("edge"), [VOICE], multilingual=False)

    async def test_a_multilingual_family_says_so(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(module.STATIC_CATALOGUES, "openai", lambda: [VOICE])

        assert (await offered_engine(config("openai"))).multilingual is True

    def test_a_choice_is_kept_per_provider_and_the_engine_shown_with_its_model(self) -> None:
        engine = EngineVoices(config("fishaudio"), [], multilingual=True)

        # Every model of a provider offers its catalogue: a model change keeps the choice.
        assert engine.key == choice_key("fishaudio") == "fishaudio"
        assert engine.name == "fishaudio/m"


def _read(raw: object) -> dict[str, str]:
    """One entry read forgivingly, as a caller's reader does."""
    if not isinstance(raw, dict):
        return {}
    return {name: voice for name, voice in raw.items() if isinstance(voice, str)}


class TestTheStoredChoice:
    """2026-10-16: kept per provider; the entries an older release kept per model still read."""

    def test_the_provider_s_own_entry_is_read_first(self) -> None:
        stored = {"fishaudio": {"host": "a"}, "fishaudio/s1": {"host": "b", "anchor": "c"}}

        assert stored_choice(stored, "fishaudio", _read) == {"host": "a"}

    def test_failing_it_the_fullest_older_entry_of_the_provider_is_read(self) -> None:
        stored = {
            "openai/tts-1": {"host": "alloy", "anchor": "coral"},
            "openai/tts-1-hd": {"host": "alloy", "anchor": "nova", "expert": "fable"},
            "openaix/m": {"host": "x", "anchor": "y", "expert": "z", "columnist": "w"},
            "edge": {"host": "henri"},
        }

        assert stored_choice(stored, "openai", _read) == {
            "host": "alloy",
            "anchor": "nova",
            "expert": "fable",
        }

    def test_on_a_tie_the_model_whose_name_sorts_last_wins(self) -> None:
        stored = {
            "elevenlabs/eleven_v4_turbo": {"host": "n", "expert": "g"},
            "elevenlabs/eleven_v3_conversational": {"host": "n", "expert": "q"},
        }

        assert stored_choice(stored, "elevenlabs", _read) == {"host": "n", "expert": "g"}

    def test_an_unreadable_own_entry_gives_way_to_an_older_one(self) -> None:
        stored = {"fishaudio": "voice", "fishaudio/s2.1-pro": {"host": "a"}}

        assert stored_choice(stored, "fishaudio", _read) == {"host": "a"}

    @pytest.mark.parametrize("stored", [None, "voices", ["fishaudio"], {7: {"host": "a"}}, {}])
    def test_anything_else_holds_no_choice(self, stored: object) -> None:
        assert stored_choice(stored, "fishaudio", _read) == {}

    @pytest.mark.parametrize(
        ("stored_key", "holds"),
        [
            ("fishaudio", True),
            ("fishaudio/s2.1-pro", True),
            ("fishaudio2", False),
            ("fish/s2", False),
            ("edge", False),
        ],
    )
    def test_a_writer_replaces_the_provider_s_entries_and_only_them(
        self, stored_key: str, holds: bool
    ) -> None:
        assert holds_choice_of(stored_key, "fishaudio") is holds


class TestTheLanguageRule:
    """Every voice of a multilingual engine speaks every language; a native one, without an accent."""

    FISH = [
        VoiceOption("e" * 32, "Emma", "female", "en"),
        VoiceOption("n" * 32, "Clone", "male", None),
        VoiceOption("f" * 32, "Emilie", "female", "fr"),
        VoiceOption("j" * 32, "Jun", "male", "ja"),
        VoiceOption("r" * 32, "Remy", "male", "fr"),
    ]
    EDGE = [
        VoiceOption("fr-FR-DeniseNeural", "Denise", "female", "fr"),
        VoiceOption("en-US-AriaNeural", "Aria", "female", "en"),
        VoiceOption("zh-CN-XiaoxiaoNeural", "Xiaoxiao", "female", "zh"),
    ]

    def test_native_voices_come_first_then_neutral_ones_then_the_rest(self) -> None:
        ordered = usable_voices(self.FISH, "fr", multilingual=True)
        assert [voice.label for voice in ordered] == ["Emilie", "Remy", "Clone", "Emma", "Jun"]

    def test_every_voice_of_a_multilingual_engine_stays_offered(self) -> None:
        assert len(usable_voices(self.FISH, "de", multilingual=True)) == len(self.FISH)

    def test_a_one_language_engine_offers_the_person_s_language_alone(self) -> None:
        assert [voice.label for voice in usable_voices(self.EDGE, "fr", False)] == ["Denise"]

    def test_both_spellings_of_chinese_compare(self) -> None:
        assert [voice.label for voice in usable_voices(self.EDGE, "zh-CN", False)] == ["Xiaoxiao"]

    def test_a_language_without_voices_still_gets_every_voice(self) -> None:
        assert usable_voices(self.EDGE, "it", multilingual=False) == self.EDGE


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_every_language_of_the_product_finds_edge_voices_of_its_own(language: str) -> None:
    # Edge's voices each speak one language: in every language the product speaks,
    # a person is offered voices of that language, and only those.
    offered = usable_voices(get_edge_voices(), language, multilingual=False)

    assert offered
    assert {canonical_language(voice.language) for voice in offered} == {language}


class TestWhatIsKnownWithoutTheVendor:
    """What a voice turn reads (ADR-345 amendment): never a vendor's listing."""

    def test_every_live_catalogue_has_its_cache_only_reader(self) -> None:
        assert set(KNOWN_LIVE_CATALOGUES) == set(LIVE_CATALOGUES)

    async def test_a_shipped_list_is_always_known(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(module.STATIC_CATALOGUES, "edge", lambda: [VOICE])

        assert await known_engine(config("edge")) == EngineVoices(
            config("edge"), [VOICE], multilingual=False
        )

    async def test_a_live_list_is_known_as_its_cache_holds_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        held: list[VoiceOption] | None = None
        asked: list[str] = []

        async def peek(cfg: TTSConfig) -> list[VoiceOption] | None:
            return held

        async def listing(cfg: TTSConfig, api_key: str) -> list[VoiceOption]:
            asked.append("vendor")
            return [VOICE]

        monkeypatch.setitem(module.KNOWN_LIVE_CATALOGUES, "fishaudio", peek)
        monkeypatch.setitem(module.LIVE_CATALOGUES, "fishaudio", listing)

        assert await known_engine(config("fishaudio")) is None  # not cached yet
        held = [VOICE]
        engine = await known_engine(config("fishaudio"))
        assert engine is not None and engine.voices == [VOICE] and engine.multilingual
        assert asked == []

    async def test_a_provider_no_catalogue_serves_is_known_empty(self) -> None:
        engine = await known_engine(config("nobody"))
        assert engine is not None and engine.voices == []
