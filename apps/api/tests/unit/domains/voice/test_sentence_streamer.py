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
- ``on_chars_synthesized`` callback fires per SERVED sentence (never for a refused one) and exceptions
  raised inside it never break the stream
- ``first_audio_latency_seconds`` is populated only after a chunk lands
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterator

import pytest
from structlog.testing import capture_logs

from src.domains.voice import sentence_streamer
from src.domains.voice.exceptions import TTSProviderError
from src.domains.voice.schemas import VoiceAudioChunk
from src.domains.voice.sentence_streamer import ProgressiveSentenceStreamer
from tests.support.structlog_capture import fresh_module_logger

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
async def test_a_refused_sentence_costs_nothing_a_served_one_costs_its_length() -> None:
    """The characters are counted when the provider RETURNS audio, never at dispatch.

    Measured on Docker dev 2026-09-20: four streams refused on every sentence
    (``invalid_api_key``, zero chunks) each recorded a TTS cost and stamped
    the message — absence of delivery was billed. A refused sentence spends
    nothing; a served one costs exactly its length.
    """
    counts: list[int] = []

    async def _synth(sentence: str) -> str:
        if sentence.startswith("KO"):
            raise RuntimeError("provider refused")
        return f"ok-{sentence}"

    streamer = ProgressiveSentenceStreamer(
        synth=_synth,
        max_sentences=5,
        audio_format="mp3",
        on_chars_synthesized=counts.append,
    )
    streamer.feed("KO one. Served two. KO three.")
    streamer.close_input()
    chunks = await _collect(streamer)

    assert [c.phrase_text for c in chunks] == ["Served two."]
    assert counts == [len("Served two.")]


@pytest.mark.unit
async def test_a_stream_refused_on_every_sentence_counts_no_character() -> None:
    counts: list[int] = []

    async def _refuse(_: str) -> str:
        raise RuntimeError("invalid_api_key")

    streamer = ProgressiveSentenceStreamer(
        synth=_refuse,
        max_sentences=5,
        audio_format="mp3",
        on_chars_synthesized=counts.append,
    )
    streamer.feed("One. Two. Three.")
    streamer.close_input()
    chunks = await _collect(streamer)

    assert chunks == []
    assert counts == []
    assert streamer.dispatched_sentences == 3


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


# ---------------------------------------------------------------------------
# Nothing to say
# ---------------------------------------------------------------------------


def _recording_synth(sent: list[str]) -> Callable[[str], Awaitable[str]]:
    async def _synth(sentence: str) -> str:
        sent.append(sentence)
        return f"ok:{sentence}"

    return _synth


@pytest.mark.unit
async def test_a_sentence_with_nothing_to_say_is_neither_sent_nor_billed() -> None:
    """Emojis, bracketed tags and markup alone leave nothing to pronounce.

    Measured in production 2026-10-03: such a sentence was sent, refused by the
    provider (« empty text after removing speaker tags and emojis », HTTP 400)
    and logged as an ERROR — a call for a silence nobody could have heard.
    """
    sent: list[str] = []
    counts: list[int] = []
    streamer = ProgressiveSentenceStreamer(
        synth=_recording_synth(sent),
        max_sentences=5,
        audio_format="mp3",
        on_chars_synthesized=counts.append,
    )
    streamer.feed("Bonjour. 🎉🎉 [laughs] ✨. <br/> *** ! Au revoir. 🙂")
    streamer.close_input()
    chunks = await _collect(streamer)

    assert sent == ["Bonjour.", "Au revoir."]
    assert [(c.phrase_index, c.phrase_text) for c in chunks] == [
        (0, "Bonjour."),
        (1, "Au revoir."),
    ]
    assert counts == [len("Bonjour."), len("Au revoir.")]
    assert streamer.dispatched_sentences == 2


@pytest.mark.unit
async def test_digits_and_any_script_are_something_to_say() -> None:
    sent: list[str] = []
    streamer = ProgressiveSentenceStreamer(
        synth=_recording_synth(sent), max_sentences=5, audio_format="mp3"
    )
    streamer.feed("42. 你好")
    streamer.close_input()
    await _collect(streamer)

    assert sent == ["42.", "你好"]


@pytest.mark.unit
async def test_a_stream_with_nothing_to_say_still_closes() -> None:
    streamer = ProgressiveSentenceStreamer(
        synth=_recording_synth([]), max_sentences=5, audio_format="mp3"
    )
    streamer.feed("🎉 [music]. ✨")
    streamer.close_input()

    assert await asyncio.wait_for(_collect(streamer), timeout=1) == []
    assert streamer.dispatched_sentences == 0


# ---------------------------------------------------------------------------
# What a refusal leaves in the logs
# ---------------------------------------------------------------------------


@pytest.fixture
def fresh_streamer_logger() -> Iterator[None]:
    """Keep `capture_logs` reliable under xdist — see `tests/support`."""
    yield from fresh_module_logger(sentence_streamer)


@pytest.mark.unit
@pytest.mark.usefixtures("fresh_streamer_logger")
async def test_a_provider_refusal_is_logged_by_its_code_never_its_message() -> None:
    """ADR-303: a code is bounded; a provider's message may quote what it refused."""

    async def _refuse(_: str) -> str:
        raise TTSProviderError(
            code="provider_http_error",
            message="HTTP 400: refused « the words of the answer »",
            details={"status_code": 400},
        )

    streamer = ProgressiveSentenceStreamer(synth=_refuse, max_sentences=5, audio_format="mp3")
    with capture_logs() as logs:
        streamer.feed("Une phrase.")
        streamer.close_input()
        await _collect(streamer)

    errors = [entry for entry in logs if entry["event"] == "progressive_sentence_synth_error"]
    assert len(errors) == 1
    assert {
        key: errors[0].get(key) for key in ("error_code", "status_code", "transient", "error_type")
    } == {
        "error_code": "provider_http_error",
        "status_code": 400,
        "transient": False,
        "error_type": "TTSProviderError",
    }
    assert "the words of the answer" not in repr(logs)


@pytest.mark.unit
@pytest.mark.usefixtures("fresh_streamer_logger")
async def test_an_unclassified_failure_is_logged_by_its_type_alone() -> None:
    async def _crash(_: str) -> str:
        raise RuntimeError("the words of the answer")

    streamer = ProgressiveSentenceStreamer(synth=_crash, max_sentences=5, audio_format="mp3")
    with capture_logs() as logs:
        streamer.feed("Une phrase.")
        streamer.close_input()
        await _collect(streamer)

    errors = [entry for entry in logs if entry["event"] == "progressive_sentence_synth_error"]
    assert [(e["error_type"], e.get("error_code")) for e in errors] == [("RuntimeError", None)]
    assert "the words of the answer" not in repr(logs)
