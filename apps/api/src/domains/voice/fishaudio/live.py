"""Fish Audio over its WebSocket (``/v1/tts/live``): one session per synthesis (ADR-345).

A session is ``start`` (the HTTP request's own fields, its text empty), the
text, ``stop``; the vendor answers ``audio`` events then ONE ``finish`` whose
reason is ``stop`` or ``error``, and closes (MessagePack frames, vendor
documentation). Measured on ``s2.1-pro-free`` (2026-10-13 and 14):

- the socket STREAMS: the first audio frame came 0.6-1.0 s after the text
  whatever its length (135 to 1631 bytes), then one at least every 1.7 s until
  the finish — but a speech client returns a sentence WHOLE, so what LIA waits
  for is the finish, which came no sooner than an HTTP answer (a short sentence:
  later; 815 bytes: the same 19.6 s);
- an audio event carries no reliable mark of the text it voices: on the timed
  variant, the second sentence's audio arrived labelled with the first
  sentence's chunk — which is why a session never carries two texts.

So the socket is a TRANSPORT, chosen per voice slot and HTTP by default: what
it changes is how the bytes travel, never what a caller receives. An operator
whose account carries the vendor's latency guarantee (the paid model's, which
the free one lacks) measures it on their own.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

import msgpack

from src.domains.voice.exceptions import TTSProviderError

#: Where a socket session is opened, on the API's own host.
LIVE_PATH: Final[str] = "/v1/tts/live"


def live_url(base_url: str) -> str:
    """The socket address on ``base_url``'s host — ``wss`` for ``https``, ``ws`` else."""
    scheme, _, rest = base_url.rstrip("/").partition("://")
    return f"{'wss' if scheme == 'https' else 'ws'}://{rest}{LIVE_PATH}"


def opening_frames(request: Mapping[str, object]) -> list[bytes]:
    """The three frames a session sends: its configuration, its text, its end.

    Args:
        request: The HTTP request's body (its ``text`` included).

    Returns:
        ``start`` (text empty, as the vendor asks), ``text``, ``stop``.
    """
    text = request.get("text", "")
    frames = (
        {"event": "start", "request": {**request, "text": ""}},
        {"event": "text", "text": text},
        {"event": "stop"},
    )
    return [msgpack.packb(frame) for frame in frames]


def _invalid(reason: str) -> TTSProviderError:
    return TTSProviderError(
        code="provider_invalid_response",
        message="Fish Audio socket answered off its documented shape",
        details={"stage": "socket", "reason": reason},
    )


class LiveAudio:
    """The audio of one session, read frame by frame until its ``finish``."""

    def __init__(self) -> None:
        self._audio = bytearray()
        self.finished = False

    @property
    def complete(self) -> bool:
        """A successful finish with actual audio, without copying the samples."""
        return self.finished and bool(self._audio)

    def read(self, frame: bytes) -> bool:
        """Read one binary frame; ``True`` once the session finished well.

        Raises:
            TTSProviderError: On a frame off the documented shape, or a
                ``finish`` whose reason is not ``stop``.
        """
        try:
            # Every refusal of ``unpackb`` is a ValueError (FormatError,
            # ExtraData, StackError, an incomplete frame).
            event = msgpack.unpackb(frame, raw=False)
        except ValueError, TypeError:
            raise _invalid("frame") from None
        if not isinstance(event, dict):
            raise _invalid("frame")
        kind = event.get("event")
        if kind == "audio":
            chunk = event.get("audio")
            if not isinstance(chunk, bytes):
                raise _invalid("audio")
            self._audio.extend(chunk)
        elif kind == "finish":
            if event.get("reason") != "stop":
                raise _invalid("finish")
            self.finished = True
        # Any other event is ignored, as the vendor asks of its clients.
        return self.finished

    @property
    def audio(self) -> bytes:
        """Every audio chunk, in arrival order."""
        return bytes(self._audio)


__all__ = ["LIVE_PATH", "LiveAudio", "live_url", "opening_frames"]
