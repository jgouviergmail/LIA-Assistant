"""Fish Audio's WebSocket session: what it sends, how its answer is read (ADR-345).

The shape is the vendor's documentation, measured on ``s2.1-pro-free``
(2026-10-13 and 14): MessagePack frames, ``start`` with the HTTP request's own
fields and an empty text, then the text, then ``stop``; the vendor answers
``audio`` events and one ``finish``. No test here reaches the network.
"""

from __future__ import annotations

import msgpack
import pytest

from src.domains.voice.exceptions import TTSProviderError
from src.domains.voice.fishaudio.live import LiveAudio, live_url, opening_frames

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("base_url", "url"),
    [
        ("https://api.fish.audio", "wss://api.fish.audio/v1/tts/live"),
        ("https://api.fish.audio/", "wss://api.fish.audio/v1/tts/live"),
        ("http://127.0.0.1:8123", "ws://127.0.0.1:8123/v1/tts/live"),
    ],
)
def test_the_socket_lives_on_the_apis_own_host(base_url: str, url: str) -> None:
    assert live_url(base_url) == url


def test_a_session_configures_then_sends_its_one_text_then_ends() -> None:
    request = {"text": "Bonjour.", "reference_id": "voice", "format": "mp3", "latency": "normal"}

    start, text, stop = (msgpack.unpackb(frame, raw=False) for frame in opening_frames(request))

    assert start == {"event": "start", "request": {**request, "text": ""}}
    assert text == {"event": "text", "text": "Bonjour."}
    assert stop == {"event": "stop"}


def _frame(event: dict[str, object]) -> bytes:
    return msgpack.packb(event)


class TestTheAnswer:
    def test_every_audio_event_is_kept_until_the_session_finishes(self) -> None:
        received = LiveAudio()

        done = [
            received.read(_frame(event))
            for event in (
                {"event": "audio", "audio": b"ID3", "time": 1.0},
                {"event": "log", "message": "ignored"},
                {"event": "audio", "audio": b"more"},
                {"event": "finish", "reason": "stop", "time": 2.0},
            )
        ]

        assert done == [False, False, False, True]
        assert received.audio == b"ID3more"
        assert received.finished

    @pytest.mark.parametrize(
        "frame",
        [
            b"\xc1",  # not MessagePack
            msgpack.packb(["audio"]),  # not an event
            msgpack.packb({"event": "audio", "audio": "not bytes"}),
            msgpack.packb({"event": "finish", "reason": "error"}),
        ],
        ids=["garbage", "not-an-event", "audio-not-bytes", "finish-error"],
    )
    def test_an_answer_off_its_shape_or_in_error_is_a_transient_refusal(self, frame: bytes) -> None:
        with pytest.raises(TTSProviderError) as raised:
            LiveAudio().read(frame)

        assert raised.value.code == "provider_invalid_response"
        assert raised.value.transient
