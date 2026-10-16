"""Fish Audio dialogue: one request for several voices, each turn placed on its timeline.

The timelines below are the vendor's own answers, MEASURED on ``s2.1-pro-free``
(2026-10-14) for a French exchange with digits, an apostrophe, a hyphen, a
percent and a cue, and for a Chinese one: the letters and digits of the turns,
in order, are exactly those of the timed segments. No test here reaches the
network.
"""

from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest

from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.domains.voice.exceptions import TTSProviderError
from src.domains.voice.fishaudio import tts_client as module
from src.domains.voice.fishaudio.dialogue import (
    TimedWord,
    TimestampedStream,
    compose_dialogue,
    turn_starts,
)
from src.domains.voice.fishaudio.tts_client import FishAudioTTSClient
from src.domains.voice.protocol import DialogueTTSClient, DialogueTurn
from tests.support.structlog_capture import fresh_module_logger

pytestmark = pytest.mark.unit

FRENCH = [
    "Le parlement a adopté le budget par 312 voix, soit 45 % des votants.",
    "L'école reste fermée, peut-être jusqu'au 3 novembre.",
    "Et c'est tout pour aujourd'hui.",
]
#: The answer to FRENCH as one request — the second turn opened by « [serious] »,
#: which the timing does not spell. Two text chunks: the first holds two turns.
FRENCH_TIMELINE = [
    *(
        TimedWord(text, start)
        for text, start in [
            ("Le", 0.16), ("parlement", 0.32), ("a", 0.8), ("adopté", 0.96), ("le", 1.28),
            ("budget", 1.36), ("par", 1.76), ("312", 1.92), ("voix", 2.56), ("soit", 3.2),
            ("45", 3.44), ("des", 4.32), ("votants", 4.4), ("L'école", 4.96), ("reste", 5.28),
            ("fermée", 5.6), ("peut", 6.4), ("être", 6.56), ("jusqu'au", 6.8), ("3", 7.04),
            ("novembre", 7.28),
        ]
    ),
    *(
        TimedWord(text, 7.94 + start)
        for text, start in [
            ("Et", 0.32), ("c'est", 0.4), ("tout", 0.64), ("pour", 0.8), ("aujourd'hui", 0.96)
        ]
    ),
]  # fmt: skip


class TestComposition:
    def test_each_voice_speaks_under_its_rank_of_entry_and_a_cue_opens_its_turn(self) -> None:
        text, voices = compose_dialogue(
            [
                DialogueTurn("anchor", "Bonsoir."),
                DialogueTurn("expert", "Merci.", cue="[serious]"),
                DialogueTurn("anchor", "Au revoir."),
            ]
        )

        assert voices == ["anchor", "expert"]
        assert text == "<|speaker:0|>Bonsoir.<|speaker:1|>[serious] Merci.<|speaker:0|>Au revoir."


class TestPlacement:
    def test_the_measured_french_exchange_places_every_turn(self) -> None:
        assert turn_starts(FRENCH, FRENCH_TIMELINE) == (0.16, 4.96, pytest.approx(8.26))

    def test_the_measured_chinese_exchange_places_every_turn(self) -> None:
        timeline = [TimedWord(c, 0.08 * n) for n, c in enumerate("今天的新闻摘要")] + [
            TimedWord(c, 1.48 + 0.1 * n) for n, c in enumerate("交通罢工将持续到明天早上")
        ]

        starts = turn_starts(["今天的新闻摘要。", "交通罢工将持续到明天早上。"], timeline)

        assert starts == (0.0, 1.48)

    def test_a_timing_that_spells_other_words_places_nothing(self) -> None:
        """A vendor that read « 312 » aloud as words: no turn is guessed."""
        spelled = [
            w if w.text != "312" else TimedWord("trois cent douze", w.start_s)
            for w in FRENCH_TIMELINE
        ]

        assert turn_starts(FRENCH, spelled) is None

    def test_a_turn_with_nothing_to_time_places_nothing(self) -> None:
        assert turn_starts([FRENCH[0], "…"], FRENCH_TIMELINE[:13]) is None


def _event(audio: bytes, seq: int, offset: float, words: list[tuple[str, float]] | None) -> str:
    alignment = (
        None
        if words is None
        else {"segments": [{"text": t, "start": s, "end": s + 0.1} for t, s in words]}
    )
    payload = {
        "audio_base64": base64.b64encode(audio).decode(),
        "content": "",
        "chunk_seq": seq,
        "chunk_audio_offset_sec": offset,
        "alignment": alignment,
    }
    return f"data: {json.dumps(payload)}"


class TestTheStream:
    def test_the_latest_snapshot_of_a_chunk_wins_and_every_audio_chunk_is_kept(self) -> None:
        stream = TimestampedStream()
        for line in [
            "event: message",
            _event(b"a", 0, 0.0, None),
            _event(b"b", 0, 0.0, [("Bonsoir", 0.1)]),
            _event(b"c", 0, 0.0, [("Bonsoir", 0.1), ("Merci", 1.2)]),
            "",
            _event(b"d", 1, 2.0, [("Fin", 0.3)]),
        ]:
            stream.feed(line)

        assert stream.audio == b"abcd"
        assert stream.timeline() == [
            TimedWord("Bonsoir", 0.1),
            TimedWord("Merci", 1.2),
            TimedWord("Fin", 2.3),
        ]

    @pytest.mark.parametrize(
        "line",
        [
            "data: not json",
            "data: []",
            'data: {"audio_base64": "!!", "alignment": null}',
            'data: {"audio_base64": "", "chunk_seq": 0, "chunk_audio_offset_sec": -1,'
            ' "alignment": {"segments": []}}',
            'data: {"audio_base64": "", "chunk_seq": "0", "chunk_audio_offset_sec": 0,'
            ' "alignment": {"segments": []}}',
        ],
    )
    def test_an_event_off_the_documented_shape_is_a_refusal(self, line: str) -> None:
        with pytest.raises(TTSProviderError) as raised:
            TimestampedStream().feed(line)

        assert raised.value.code == "provider_invalid_response"


@pytest.fixture(autouse=True)
def _fresh_module_logger() -> Iterator[None]:
    yield from fresh_module_logger(module)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    monkeypatch.setattr(
        LLMConfigOverrideCache,
        "get_api_key",
        classmethod(lambda cls, provider: "fish-key" if provider == "fishaudio" else None),
    )

    @asynccontextmanager
    async def free_slot(
        provider: str, api_key: str, *, timeout_seconds: float
    ) -> AsyncIterator[None]:
        yield

    monkeypatch.setattr(module, "provider_slot", free_slot)

    def build(respond: Any, model: str = "s2.1-pro-free") -> FishAudioTTSClient:
        return FishAudioTTSClient(model=model, http_transport=httpx.MockTransport(respond))

    yield build


class TestTheClient:
    async def test_one_request_voices_every_turn_and_places_it(self, client: Any) -> None:
        sent: list[httpx.Request] = []
        events = "\n\n".join(
            [
                _event(b"ID3first", 0, 0.0, [("Bonsoir", 0.08)]),
                _event(b"second", 1, 1.5, [("Merci", 0.2), ("à", 0.6), ("vous", 0.7)]),
            ]
        )

        def respond(request: httpx.Request) -> httpx.Response:
            sent.append(request)
            return httpx.Response(200, text=events, headers={"content-type": "text/event-stream"})

        fish = client(respond)
        assert isinstance(fish, DialogueTTSClient)
        dialogue = await fish.synthesize_dialogue(
            [DialogueTurn("anchor", "Bonsoir."), DialogueTurn("expert", "Merci à vous.", "[warm]")],
            speed=1.1,
        )

        request = sent[0]
        body = json.loads(request.content)
        assert request.url.path == "/v1/tts/stream/with-timestamp"
        assert request.headers["model"] == "s2.1-pro-free"
        assert body["reference_id"] == ["anchor", "expert"]
        assert body["text"] == "<|speaker:0|>Bonsoir.<|speaker:1|>[warm] Merci à vous."
        assert body["prosody"] == {"speed": 1.1}
        assert dialogue.audio == b"ID3firstsecond"
        assert dialogue.sent_text == body["text"]
        assert dialogue.turn_starts_s == (0.08, 1.7)
        await fish.close()

    async def test_a_refusal_keeps_its_facts(self, client: Any) -> None:
        fish = client(
            lambda request: httpx.Response(429, json={"message": "the words", "status": 429})
        )

        with pytest.raises(TTSProviderError) as raised:
            await fish.synthesize_dialogue([DialogueTurn("a", "Un."), DialogueTurn("b", "Deux.")])

        assert raised.value.code == "provider_rate_limited"
        assert "the words" not in str(raised.value)
        await fish.close()

    async def test_a_stream_without_audio_is_a_refusal(self, client: Any) -> None:
        fish = client(lambda request: httpx.Response(200, text=_event(b"", 0, 0.0, [("Un", 0.1)])))

        with pytest.raises(TTSProviderError) as raised:
            await fish.synthesize_dialogue([DialogueTurn("a", "Un."), DialogueTurn("b", "Deux.")])

        assert raised.value.code == "provider_invalid_response"
        await fish.close()
