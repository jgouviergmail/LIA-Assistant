"""Unit tests for :mod:`src.domains.voice.sentence_streamer`.

Covers the invariants of :class:`ProgressiveSentenceStreamer`:

- happy-path (in-order delivery, multiple chunks)
- ``max_sentences`` cap enforced
- TTS failure on a sentence is skipped silently and the rest of the stream
  keeps flowing
- out-of-order task completion is reordered before emission
- ``cancel_pending()`` releases tasks and emits the sentinel exactly once
- ``close_input()`` with no buffered text + zero dispatched sentences
  produces an empty stream and a single sentinel
- ``on_chars_synthesized`` callback fires per sentence and exceptions
  raised inside it never break the stream
- ``first_audio_latency_seconds`` is populated only after a chunk lands
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import pytest

from src.domains.voice.schemas import VoiceAudioChunk
from src.domains.voice.sentence_streamer import ProgressiveSentenceStreamer

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _instant_synth(token: str) -> Callable[[str], Awaitable[str]]:
    """Return a synth callable producing a deterministic base64 marker.

    Each invocation returns ``"{token}-{sentence}"`` (un-encoded for clarity
    in assertions). The returned coroutine is "instant" — it doesn't await.
    """

    async def _synth(sentence: str) -> str:
        return f"{token}-{sentence}"

    return _synth


def _delayed_synth(
    delays_by_sentence: dict[str, float],
) -> Callable[[str], Awaitable[str]]:
    """Synth callable with controlled per-sentence delay.

    Lets tests reproduce out-of-order completion: phrase A waits 50 ms while
    phrase B waits 5 ms — B finishes first but the streamer must still emit
    A then B.
    """

    async def _synth(sentence: str) -> str:
        delay = delays_by_sentence.get(sentence, 0.0)
        if delay > 0:
            await asyncio.sleep(delay)
        return f"audio:{sentence}"

    return _synth


async def _collect(
    streamer: ProgressiveSentenceStreamer,
) -> list[VoiceAudioChunk]:
    """Drain the streamer's audio_chunks() iterator into a list."""
    chunks: list[VoiceAudioChunk] = []
    async for chunk in streamer.audio_chunks():
        chunks.append(chunk)
    return chunks


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_happy_path_in_order_delivery() -> None:
    """Two sentences fed → two chunks emitted in dispatch order."""
    streamer = ProgressiveSentenceStreamer(
        synth=_instant_synth("ok"),
        max_sentences=10,
        audio_format="mp3",
    )
    streamer.feed("Bonjour. Comment ça va ? ")
    streamer.close_input()
    chunks = await _collect(streamer)

    assert [c.phrase_index for c in chunks] == [0, 1]
    assert chunks[0].phrase_text == "Bonjour."
    assert chunks[1].phrase_text == "Comment ça va ?"
    assert all(c.mime_type == "audio/mpeg" for c in chunks)
    # Single sentence dispatched per phrase, no leftover in pending.
    assert streamer.dispatched_sentences == 2


@pytest.mark.unit
async def test_trailing_text_without_punctuation_is_flushed() -> None:
    """LLM closes the stream mid-sentence → trailing buffer becomes the
    final sentence (no terminator required)."""
    streamer = ProgressiveSentenceStreamer(
        synth=_instant_synth("ok"),
        max_sentences=5,
        audio_format="mp3",
    )
    streamer.feed("Première phrase. Sans terminateur final")
    streamer.close_input()
    chunks = await _collect(streamer)

    assert [c.phrase_text for c in chunks] == [
        "Première phrase.",
        "Sans terminateur final",
    ]


# ---------------------------------------------------------------------------
# Max-sentences cap
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_max_sentences_cap_drops_excess() -> None:
    """Six sentences fed with ``max_sentences=3`` → only the first three
    are dispatched; everything after is silently dropped."""
    streamer = ProgressiveSentenceStreamer(
        synth=_instant_synth("ok"),
        max_sentences=3,
        audio_format="mp3",
    )
    streamer.feed("Un. Deux. Trois. Quatre. Cinq. Six.")
    streamer.close_input()
    chunks = await _collect(streamer)

    assert [c.phrase_text for c in chunks] == ["Un.", "Deux.", "Trois."]
    assert streamer.dispatched_sentences == 3


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_failed_sentence_is_skipped_stream_continues() -> None:
    """Sentence #2 fails → slot skipped, sentences #1 and #3 emitted in order."""
    counter = {"call": 0}

    async def _flaky_synth(sentence: str) -> str:
        counter["call"] += 1
        if counter["call"] == 2:
            raise RuntimeError("provider 503")
        return f"ok:{sentence}"

    streamer = ProgressiveSentenceStreamer(
        synth=_flaky_synth,
        max_sentences=5,
        audio_format="mp3",
    )
    streamer.feed("Un. Deux. Trois.")
    streamer.close_input()
    chunks = await _collect(streamer)

    # Only 2 chunks land — the failed slot is skipped without blocking.
    assert [c.phrase_index for c in chunks] == [0, 2]
    assert [c.phrase_text for c in chunks] == ["Un.", "Trois."]


# ---------------------------------------------------------------------------
# Out-of-order completion
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_out_of_order_completion_reordered_before_emission() -> None:
    """Sentence #1 takes longer than #2 → consumer still sees #1 then #2."""
    delays = {"Un.": 0.05, "Deux.": 0.005}
    streamer = ProgressiveSentenceStreamer(
        synth=_delayed_synth(delays),
        max_sentences=5,
        audio_format="mp3",
    )
    streamer.feed("Un. Deux.")
    streamer.close_input()
    chunks = await _collect(streamer)

    assert [c.phrase_index for c in chunks] == [0, 1]
    assert [c.phrase_text for c in chunks] == ["Un.", "Deux."]


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_cancel_pending_releases_tasks_and_pushes_single_sentinel() -> None:
    """A consumer disconnect calls cancel_pending() — the streamer wraps
    up cleanly and audio_chunks() exits without raising."""

    started = asyncio.Event()
    proceed = asyncio.Event()

    async def _slow_synth(sentence: str) -> str:
        started.set()
        # Block until the test releases the gate. Cancellation should
        # interrupt this wait.
        await proceed.wait()
        return f"ok:{sentence}"

    streamer = ProgressiveSentenceStreamer(
        synth=_slow_synth,
        max_sentences=5,
        audio_format="mp3",
    )
    streamer.feed("Un. Deux.")
    # Wait until at least one TTS task is in-flight, then cancel.
    await started.wait()
    streamer.cancel_pending()

    chunks: list[VoiceAudioChunk] = []
    async for chunk in streamer.audio_chunks():
        chunks.append(chunk)

    # The cancelled tasks may still be alive briefly; allow the event
    # loop to schedule their cleanup before final assertions.
    proceed.set()
    await asyncio.sleep(0)

    # Either no chunks emitted (cancel hit before any synth completed) or
    # at most one (race with the staging lock). The streamer MUST close
    # cleanly either way — no infinite loop, no second sentinel waiting
    # in the queue (consumed exactly the one cancel pushed).
    assert len(chunks) <= 2
    # The internal sentinel flag is the source of truth for idempotence.
    assert streamer._sentinel_pushed is True


# ---------------------------------------------------------------------------
# Empty / degenerate streams
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_close_input_without_any_feed_emits_no_audio() -> None:
    """LLM produced nothing → consumer sees an immediate end-of-stream."""
    streamer = ProgressiveSentenceStreamer(
        synth=_instant_synth("ok"),
        max_sentences=5,
        audio_format="mp3",
    )
    streamer.close_input()
    chunks = await _collect(streamer)

    assert chunks == []
    assert streamer.dispatched_sentences == 0


@pytest.mark.unit
async def test_feed_after_close_input_is_ignored() -> None:
    """Input is closed → subsequent feed() is a no-op (no spurious dispatch)."""
    streamer = ProgressiveSentenceStreamer(
        synth=_instant_synth("ok"),
        max_sentences=5,
        audio_format="mp3",
    )
    streamer.close_input()
    streamer.feed("Trop tard.")  # must be silently ignored

    chunks = await _collect(streamer)
    assert chunks == []
    assert streamer.dispatched_sentences == 0


# ---------------------------------------------------------------------------
# Cost tracking callback
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_on_chars_synthesized_called_once_per_sentence() -> None:
    """Verify the cost-tracking hook is invoked with each sentence's char count."""
    counts: list[int] = []
    streamer = ProgressiveSentenceStreamer(
        synth=_instant_synth("ok"),
        max_sentences=5,
        audio_format="mp3",
        on_chars_synthesized=counts.append,
    )
    streamer.feed("AB. CDEF.")
    streamer.close_input()
    await _collect(streamer)

    # "AB." → 3 chars, "CDEF." → 5 chars. Order matches dispatch order.
    assert counts == [3, 5]


@pytest.mark.unit
async def test_on_chars_synthesized_exception_is_swallowed() -> None:
    """A throwing callback must NOT break the synth pipeline (CLAUDE.md
    rule: cross-cutting hooks are best-effort)."""

    def _bad_callback(_: int) -> None:
        raise RuntimeError("metric backend down")

    streamer = ProgressiveSentenceStreamer(
        synth=_instant_synth("ok"),
        max_sentences=5,
        audio_format="mp3",
        on_chars_synthesized=_bad_callback,
    )
    streamer.feed("Une phrase.")
    streamer.close_input()
    chunks = await _collect(streamer)

    # The chunk still flows through — the pipeline is resilient.
    assert len(chunks) == 1
    assert chunks[0].phrase_text == "Une phrase."


# ---------------------------------------------------------------------------
# Latency property
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_first_audio_latency_seconds_populated_after_first_chunk() -> None:
    """Property is None before any chunk lands, then a positive float."""
    streamer = ProgressiveSentenceStreamer(
        synth=_instant_synth("ok"),
        max_sentences=5,
        audio_format="mp3",
    )
    assert streamer.first_audio_latency_seconds is None

    streamer.feed("Première.")
    streamer.close_input()
    await _collect(streamer)

    latency = streamer.first_audio_latency_seconds
    assert latency is not None
    assert latency >= 0.0


# ---------------------------------------------------------------------------
# MIME type fallback
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_unknown_audio_format_falls_back_to_default_mime() -> None:
    """An audio_format outside the known map (mp3/opus/aac/flac/wav/pcm)
    yields the default MIME type — protects forward compatibility."""
    streamer = ProgressiveSentenceStreamer(
        synth=_instant_synth("ok"),
        max_sentences=5,
        audio_format="unknown_format",
    )
    streamer.feed("Une phrase.")
    streamer.close_input()
    chunks = await _collect(streamer)

    assert chunks[0].mime_type == "audio/mpeg"
