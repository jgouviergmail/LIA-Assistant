"""LIA's voices for one person (ADR-345 amendment 2026-10-14).

What is asserted is the rule, read forgivingly and written strictly: a choice
kept per provider — every model of it, and the entries an older release kept per
model still read —, a voice the engine no longer offers reading as the instance's,
an engine that cannot list its voices keeping the choice, a write of a voice the
engine does not offer refused before anything is stored — and, before LIA
speaks, no vendor asked: the catalogue is the one already known, and a person
who never chose reads none at all.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from src.core.constants import VOICE_ID_MAX_CHARS
from src.core.exceptions import BaseAPIException
from src.domains.voice import lia_voices as module
from src.domains.voice.engine_voices import EngineVoices
from src.domains.voice.factory import TTSConfig
from src.domains.voice.lia_voices import (
    LIA_VOICE_UNKNOWN,
    choice_on,
    gender_of,
    kept,
    lia_voices,
    save_lia_voices,
    spoken_voice,
    without_voice,
)
from src.domains.voice.voices_catalog import VoiceOption

pytestmark = pytest.mark.unit

ENGINE = "fishaudio"
#: Where a release before 2026-10-16 kept the same choice: per provider AND model.
OLDER = "fishaudio/s2.1-pro"
EMMA = VoiceOption("e" * 32, "Emma", "female", "en")
EMILIE = VoiceOption("f" * 32, "Emilie", "female", "fr")
REMY = VoiceOption("r" * 32, "Remy", "male", "fr")
DENISE = VoiceOption("fr-FR-DeniseNeural", "Denise", "female", "fr")
ARIA = VoiceOption("en-US-AriaNeural", "Aria", "female", "en")


def config(provider: str = "fishaudio", model: str = "s2.1-pro") -> TTSConfig:
    return TTSConfig(
        provider=provider, model=model, voice_male=REMY.voice_id, voice_female="unlisted"
    )


def engine(
    voices: list[VoiceOption], *, multilingual: bool = True, cfg: TTSConfig | None = None
) -> EngineVoices:
    return EngineVoices(cfg or config(), voices, multilingual=multilingual)


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """The person's stored column, the engine that speaks, and every write."""
    state: dict[str, Any] = {
        "stored": None,
        "engine": engine([EMMA, EMILIE, REMY]),
        # What the speaking path may read: known without the vendor, or None.
        "known": engine([EMMA, EMILIE, REMY]),
        "writes": [],
        "known_reads": 0,
        "vendor_asks": 0,
    }

    async def stored(user_id: UUID) -> object:
        return state["stored"]

    async def chat_engine() -> EngineVoices:
        return state["engine"]

    async def known(cfg: TTSConfig) -> EngineVoices | None:
        state["known_reads"] += 1
        known_engine: EngineVoices | None = state["known"]
        if known_engine is None:
            return None
        return EngineVoices(cfg, known_engine.voices, known_engine.multilingual)

    async def offered(cfg: TTSConfig) -> EngineVoices:
        state["vendor_asks"] += 1
        return state["engine"]

    async def write(
        user_id: UUID,
        key: str,
        choice: dict[str, str],
        *,
        catalogue_revision: UUID | None = None,
        credential_fingerprint: str | None = None,
    ) -> None:
        state["writes"].append((key, dict(choice)))

    monkeypatch.setattr(module, "_stored", stored)
    monkeypatch.setattr(module, "chat_engine", chat_engine)
    monkeypatch.setattr(module, "known_engine", known)
    monkeypatch.setattr(module, "offered_engine", offered)
    monkeypatch.setattr(module, "_write", write)
    return state


class TestTheStoredChoice:
    def test_each_provider_keeps_its_own_voices(self) -> None:
        stored = {ENGINE: {"male": REMY.voice_id}, "edge": {"female": DENISE.voice_id}}

        assert choice_on(stored, ENGINE) == {"male": REMY.voice_id}
        assert choice_on(stored, "edge") == {"female": DENISE.voice_id}
        assert choice_on(stored, "openai") == {}

    def test_an_entry_an_older_release_kept_per_model_is_still_read(self) -> None:
        stored = {
            "fishaudio/s1": {"male": REMY.voice_id},
            OLDER: {"male": REMY.voice_id, "female": EMILIE.voice_id},
            "edge/edge-tts": {"female": DENISE.voice_id},
        }

        # The fullest one of the provider's models: a model change never loses it.
        assert choice_on(stored, ENGINE) == {"male": REMY.voice_id, "female": EMILIE.voice_id}
        assert choice_on(stored, "edge") == {"female": DENISE.voice_id}
        assert choice_on(stored, "edge-like") == {}

    def test_the_provider_s_own_entry_wins_over_an_older_one(self) -> None:
        stored = {OLDER: {"male": REMY.voice_id, "female": EMILIE.voice_id}, ENGINE: {"male": "x"}}

        assert choice_on(stored, ENGINE) == {"male": "x"}

    @pytest.mark.parametrize("stored", [None, "voices", ["a"], {ENGINE: "male"}, {ENGINE: None}])
    def test_anything_but_a_mapping_names_no_voice(self, stored: object) -> None:
        assert choice_on(stored, ENGINE) == {}

    def test_a_value_that_names_no_voice_is_left_out(self) -> None:
        stored = {
            ENGINE: {
                "male": "x" * (VOICE_ID_MAX_CHARS + 1),
                "female": "   ",
                "neutral": EMMA.voice_id,
            }
        }

        assert choice_on(stored, ENGINE) == {}

    def test_only_lia_s_two_genders_are_genders(self) -> None:
        assert (gender_of("male"), gender_of("female"), gender_of("neutral")) == (
            "male",
            "female",
            None,
        )


class TestWhatTheEngineStillOffers:
    def test_a_voice_no_longer_offered_reads_as_the_instance_s(self) -> None:
        choice = {"male": REMY.voice_id, "female": "gone"}

        assert kept(choice, engine([REMY]), [REMY]) == {"male": REMY.voice_id}

    def test_an_engine_that_cannot_list_its_voices_keeps_the_choice(self) -> None:
        choice = {"male": "unknown-now"}

        assert kept(choice, engine([]), []) == choice


class TestTheSettingsPage:
    async def test_shows_the_voices_offered_the_choice_and_the_instance_s_voices(
        self, world: dict[str, Any]
    ) -> None:
        world["stored"] = {ENGINE: {"female": EMILIE.voice_id, "male": "gone"}}

        view = await lia_voices(uuid4(), "fr")

        assert [voice.label for voice in view.voices] == ["Emilie", "Remy", "Emma"]
        assert view.chosen == {"female": EMILIE.voice_id}
        assert view.defaults["male"] == REMY
        # A default the catalogue does not hold is still named, by its id.
        assert (view.defaults["female"].voice_id, view.defaults["female"].label) == (
            "unlisted",
            "unlisted",
        )

    async def test_a_one_language_engine_offers_the_person_s_language(
        self, world: dict[str, Any]
    ) -> None:
        world["engine"] = engine([DENISE, ARIA], multilingual=False, cfg=config("edge", "edge-tts"))
        world["stored"] = {"edge": {"female": ARIA.voice_id}}

        view = await lia_voices(uuid4(), "fr")

        assert [voice.voice_id for voice in view.voices] == [DENISE.voice_id]
        # An English voice is no longer offered to a French reader: it reads as default.
        assert view.chosen == {}


class TestTheWrite:
    async def test_an_offered_voice_is_kept_for_the_engine_that_speaks(
        self, world: dict[str, Any]
    ) -> None:
        view = await save_lia_voices(uuid4(), "fr", {"male": REMY.voice_id})

        assert world["writes"] == [(ENGINE, {"male": REMY.voice_id})]
        assert view.chosen == {"male": REMY.voice_id}

    async def test_a_voice_the_engine_does_not_offer_is_refused_and_nothing_stored(
        self, world: dict[str, Any]
    ) -> None:
        with pytest.raises(BaseAPIException) as refused:
            await save_lia_voices(uuid4(), "fr", {"male": REMY.voice_id, "female": "nope"})

        assert refused.value.status_code == 422
        assert refused.value.detail == {"code": LIA_VOICE_UNKNOWN}
        assert world["writes"] == []

    async def test_an_unavailable_catalogue_cannot_authorize_a_new_voice(
        self, world: dict[str, Any]
    ) -> None:
        world["engine"] = engine([])

        with pytest.raises(BaseAPIException) as refused:
            await save_lia_voices(uuid4(), "fr", {"male": "any-voice"})

        assert refused.value.status_code == 503
        assert refused.value.detail == {"code": "lia_voice_catalogue_unavailable"}
        assert world["writes"] == []

    async def test_an_unavailable_catalogue_still_allows_returning_to_defaults(
        self, world: dict[str, Any]
    ) -> None:
        world["engine"] = engine([])
        await save_lia_voices(uuid4(), "fr", {})
        assert world["writes"] == [(ENGINE, {})]

    async def test_no_choice_gives_both_voices_back_to_the_instance(
        self, world: dict[str, Any]
    ) -> None:
        await save_lia_voices(uuid4(), "fr", {})

        assert world["writes"] == [(ENGINE, {})]


class TestBeforeLiaSpeaks:
    async def test_the_person_s_voice_speaks_on_every_model_of_its_provider(
        self, world: dict[str, Any]
    ) -> None:
        world["stored"] = {ENGINE: {"female": EMILIE.voice_id}}

        assert await spoken_voice(str(uuid4()), config(), "female", "fr") == EMILIE.voice_id
        # A model switched for another keeps it (2026-10-16): the catalogue is the provider's.
        free = config("fishaudio", "s2.1-pro-free")
        assert await spoken_voice(str(uuid4()), free, "female", "fr") == EMILIE.voice_id
        # Another provider speaks: the choice made on this one does not travel.
        assert await spoken_voice(str(uuid4()), config("openai", "tts-1"), "female", "fr") is None
        assert world["vendor_asks"] == 0

    async def test_a_choice_an_older_release_kept_per_model_still_speaks(
        self, world: dict[str, Any]
    ) -> None:
        world["stored"] = {OLDER: {"female": EMILIE.voice_id}}

        free = config("fishaudio", "s2.1-pro-free")
        assert await spoken_voice(str(uuid4()), free, "female", "fr") == EMILIE.voice_id

    async def test_a_person_who_never_chose_reads_no_catalogue(self, world: dict[str, Any]) -> None:
        assert await spoken_voice(str(uuid4()), config(), "male", "fr") is None
        assert (world["known_reads"], world["vendor_asks"]) == (0, 0)

    async def test_a_voice_no_longer_offered_gives_way_to_the_instance_s(
        self, world: dict[str, Any]
    ) -> None:
        world["stored"] = {ENGINE: {"male": "deleted-since"}}

        assert await spoken_voice(str(uuid4()), config(), "male", "fr") is None

    async def test_an_engine_that_cannot_list_its_voices_keeps_the_choice(
        self, world: dict[str, Any]
    ) -> None:
        world["stored"] = {ENGINE: {"male": "cannot-tell"}}
        world["known"] = engine([])

        assert await spoken_voice(str(uuid4()), config(), "male", "fr") == "cannot-tell"

    async def test_a_catalogue_not_cached_yet_keeps_the_choice_and_asks_no_vendor(
        self, world: dict[str, Any]
    ) -> None:
        # Measured on dev: a cold Fish Audio listing took 6.8-9.2 s — never on a voice turn.
        world["stored"] = {ENGINE: {"female": EMILIE.voice_id}}
        world["known"] = None

        assert await spoken_voice(str(uuid4()), config(), "female", "fr") == EMILIE.voice_id
        assert world["vendor_asks"] == 0

    @pytest.mark.parametrize(("user_id", "gender"), [(None, "male"), ("set", "neutral")])
    async def test_an_anonymous_synthesis_or_an_unknown_gender_has_no_choice(
        self, world: dict[str, Any], user_id: str | None, gender: str
    ) -> None:
        world["stored"] = {ENGINE: {"male": REMY.voice_id}}
        person = str(uuid4()) if user_id else None

        assert await spoken_voice(person, config(), gender, "fr") is None


class TestAVoiceThatIsGone:
    def test_it_leaves_every_engine_and_every_other_choice_stays(self) -> None:
        stored = {
            ENGINE: {"male": REMY.voice_id, "female": EMILIE.voice_id},
            "fishaudio/s1": {"male": REMY.voice_id},
            "edge/edge-tts": {"female": DENISE.voice_id},
        }

        assert without_voice(stored, REMY.voice_id) == {
            ENGINE: {"female": EMILIE.voice_id},
            "edge/edge-tts": {"female": DENISE.voice_id},
        }

    def test_nothing_left_is_no_choice_at_all(self) -> None:
        assert without_voice({ENGINE: {"male": REMY.voice_id}}, REMY.voice_id) is None

    @pytest.mark.parametrize("stored", [None, "voices", {ENGINE: "male"}, {7: {"male": "x"}}])
    def test_what_names_no_voice_is_no_choice(self, stored: object) -> None:
        assert without_voice(stored, REMY.voice_id) is None
