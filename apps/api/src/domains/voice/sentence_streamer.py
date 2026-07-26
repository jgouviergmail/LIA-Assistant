"""Progressive sentence streaming for low-latency TTS.

The default voice flow waits for the LLM to fully complete (chat response or
voice-comment LLM) before splitting into sentences and synthesising. For long
responses this introduces several seconds of dead air before the first audio
chunk reaches the user.

This module exposes :class:`ProgressiveSentenceStreamer`, which buffers an
incoming text stream **token by token** and dispatches the synthesis of each
complete sentence as soon as a punctuation delimiter (``. ! ?``) is detected.
Per-sentence TTS calls run **concurrently** as ``asyncio.Task`` instances and
the resulting :class:`VoiceAudioChunk` objects are pushed to an internal
queue, ordered by completion (the consumer respects ``phrase_index`` for UI
ordering).

Typical usage (mode chat — chat LLM streaming + direct TTS)::

    streamer = ProgressiveSentenceStreamer(
        synth=lambda text: tts_client.synthesize_base64(text, voice_name=voice),
        max_sentences=10,
        audio_format=tts_client.audio_format,
    )

    async def feed_chat_tokens():
        async for token in chat_llm.astream(prompt):
            streamer.feed(token.content)
        streamer.close_input()

    feeder = asyncio.create_task(feed_chat_tokens())
    async for chunk in streamer.audio_chunks():
        yield chunk
    await feeder

Latency saved (rule of thumb): for an N-sentence response the first audio
chunk lands ~``N×`` faster than the legacy "wait the full text first" path.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import suppress
from typing import Any

import structlog

from src.core.constants import VOICE_TTS_MS_PER_CHAR_HEURISTIC
from src.domains.voice.schemas import (
    AUDIO_MIME_TYPES,
    DEFAULT_AUDIO_MIME_TYPE,
    VoiceAudioChunk,
)

logger = structlog.get_logger(__name__)


def _build_sentence_end_regex(delimiters: str) -> re.Pattern[str]:
    """Build the sentence-end regex from a configurable delimiter string.

    The pattern eats one or more delimiters in a row (e.g. ``"...???"``) so
    that ellipses or stylistic emphasis don't split a sentence into multiple
    fragments. ``re.escape`` keeps the character class safe even when the
    admin opts into delimiters that have regex meta-meaning (e.g. ``$`` or
    ``+``). Empty input falls back to the default ``.!?`` to keep the
    streamer functional rather than silently never splitting anything.

    The run must be FOLLOWED BY WHITESPACE to count as a boundary. Two reasons,
    and they are the same reason: a delimiter glued to the next character is
    part of a token ("3.5", "12.99", "1.2.3", "exemple.fr"), and a delimiter at
    the very end of the buffer may simply be one whose next character has not
    streamed in yet. Without the lookahead the streamer dispatched "il fait 3."
    to the TTS engine and spoke "cinq degrés" as a separate sentence. The tail
    that never gets a following space is flushed by :meth:`close_input`.
    """
    chars = delimiters or ".!?"
    return re.compile(f"[{re.escape(chars)}]+(?=\\s)")


SynthCallable = Callable[[str], Awaitable[str]]
"""Async callable that synthesises one sentence to base64-encoded audio.

Should raise on synthesis error so the streamer can record metrics. The
caller is responsible for binding ``voice_name`` (and any other per-call
overrides) via a closure.
"""


class ProgressiveSentenceStreamer:
    """Buffers a text stream and dispatches TTS per complete sentence.

    Lifecycle:
        1. ``feed(text)`` — push tokens (any granularity, including a single
           character or a multi-sentence chunk). Sentences ending in
           ``[.!?]`` are extracted immediately and dispatched as TTS tasks.
        2. ``close_input()`` — call once the producer is exhausted; flushes
           the trailing buffer as a final sentence (if non-empty and the
           ``max_sentences`` cap is not hit).
        3. ``audio_chunks()`` — async iterator yielding
           :class:`VoiceAudioChunk` instances **in completion order**. Closes
           when the input is closed AND all dispatched tasks are done.

    Concurrency model:
        - ``feed`` is sync (cheap) and safe to call from any context.
        - Each TTS dispatch creates an :class:`asyncio.Task`.
        - ``audio_chunks()`` consumes from an :class:`asyncio.Queue`.
        - Cancellation of the consumer cancels in-flight TTS tasks via
          ``cancel_pending()`` for cooperative cleanup.
    """

    def __init__(
        self,
        synth: SynthCallable,
        max_sentences: int,
        audio_format: str = "mp3",
        *,
        sentence_delimiters: str | None = None,
        on_chars_synthesized: Callable[[int], None] | None = None,
    ) -> None:
        """Initialise the streamer.

        Args:
            synth: Async callable taking a sentence and returning the
                base64-encoded audio bytes for that sentence.
            max_sentences: Hard cap on dispatched sentences — extra sentences
                from the input stream are dropped (the rest of the response
                is silent). Mirrors the legacy
                ``settings.voice_chat_mode_max_sentences`` cap.
            audio_format: Short MIME-like extension token (``mp3``/``opus``/
                ``pcm``/…) — used to populate the ``mime_type`` field of
                produced VoiceAudioChunk objects.
            sentence_delimiters: Characters that mark sentence boundaries.
                Defaults to ``.!?`` when ``None`` is passed; production
                callers should forward ``settings.voice_sentence_delimiters``
                so the regex follows the admin-configurable knob.
            on_chars_synthesized: Optional callback invoked synchronously
                with the integer character count of every sentence
                dispatched. Wires in the TTS cost tracker without
                threading the tracker through this module.
        """
        self._synth = synth
        self._max_sentences = max(1, int(max_sentences))
        self._audio_format = audio_format
        self._sentence_end_re = _build_sentence_end_regex(sentence_delimiters or ".!?")
        self._on_chars_synthesized = on_chars_synthesized

        self._buffer: str = ""
        self._dispatched: int = 0
        self._input_closed: bool = False

        self._queue: asyncio.Queue[VoiceAudioChunk | None] = asyncio.Queue()
        self._tasks: list[asyncio.Task[None]] = []
        self._first_audio_time: float | None = None
        self._stream_start_time: float = time.time()

        # === In-order delivery buffer ===
        # Without this, an asyncio.Task synthesising sentence #2 may finish
        # before sentence #1 (shorter input or provider variance) and the
        # consumer would hear them out of order. We buffer by phrase_index
        # and drain only when the next-expected index is ready, skipping
        # failed slots so a single provider error doesn't stall the whole
        # stream forever.
        self._pending: dict[int, VoiceAudioChunk] = {}
        self._failed: set[int] = set()
        self._next_emit_idx: int = 0
        self._drain_lock: asyncio.Lock = asyncio.Lock()

        # The end-of-stream sentinel ``None`` MUST be pushed exactly once.
        # Several producers can race to push it (cancel_pending, the last
        # task's done callback, the explicit close_input check) — without
        # this flag the consumer's ``audio_chunks()`` loop exits on the
        # first None but a second one stays in the queue, which is fine in
        # isolation but masks any future change that would consume the
        # queue more than once.
        self._sentinel_pushed: bool = False

    # ------------------------------------------------------------------
    # Producer surface
    # ------------------------------------------------------------------

    def feed(self, text: str) -> None:
        """Append text to the buffer; dispatch any complete sentences."""
        if not text or self._input_closed:
            return
        self._buffer += text
        self._drain_complete_sentences()

    def close_input(self) -> None:
        """Mark the input stream as exhausted. Flush trailing buffer.

        After this call no further ``feed()`` is allowed; the consumer task
        will see the queue close once all in-flight TTS tasks resolve.
        """
        if self._input_closed:
            return

        # Dispatch the trailing sentence BEFORE flipping the closed flag so
        # any task callback that fires during dispatch doesn't observe
        # "closed + all done" prematurely and emit the None sentinel.
        trailing = self._buffer.strip()
        self._buffer = ""
        had_trailing = bool(trailing)
        if trailing and self._dispatched < self._max_sentences:
            self._dispatch(trailing)

        self._input_closed = True

        # Diagnose silent-no-audio cases (LLM produced no terminator and
        # close_input observed an empty trailing buffer): consumer would
        # see only the sentinel without any chunk and the user hears
        # nothing — surface that explicitly so dashboards / alerts can
        # catch a misconfigured prompt or a truncated LLM response.
        if self._dispatched == 0 and not had_trailing:
            logger.warning(
                "progressive_streamer_closed_without_audio",
                buffer_len=0,
                input_closed_at=time.time() - self._stream_start_time,
            )

        # Re-run the close check now: if every dispatched task already
        # finished before close_input() was called, none of their callbacks
        # could push the sentinel (they short-circuited on
        # ``_input_closed == False``). We must close explicitly here.
        self._try_close_queue()

    def cancel_pending(self) -> None:
        """Cancel every in-flight TTS task. Safe to call multiple times.

        Used when the consumer aborts mid-stream (e.g. SSE client disconnect
        or HITL interrupt). The audio_chunks() loop should observe the
        sentinel and exit cleanly. Flipping ``_input_closed`` first prevents
        a concurrent ``close_input`` from dispatching one last sentence
        after we asked everyone to wind down.
        """
        self._input_closed = True
        for task in self._tasks:
            if not task.done():
                task.cancel()
        self._push_sentinel()

    # ------------------------------------------------------------------
    # Consumer surface
    # ------------------------------------------------------------------

    async def audio_chunks(self) -> AsyncIterator[VoiceAudioChunk]:
        """Yield :class:`VoiceAudioChunk` objects as they complete.

        Iteration ends after ``close_input()`` has been called AND all
        dispatched TTS tasks have either produced an audio chunk or failed.
        """
        while True:
            chunk = await self._queue.get()
            if chunk is None:
                return
            yield chunk

    @property
    def first_audio_latency_seconds(self) -> float | None:
        """Wall-clock seconds from streamer creation to first audio chunk
        ready in the queue. ``None`` when no chunk has landed yet."""
        if self._first_audio_time is None:
            return None
        return self._first_audio_time - self._stream_start_time

    @property
    def dispatched_sentences(self) -> int:
        return self._dispatched

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _drain_complete_sentences(self) -> None:
        """Extract and dispatch every complete sentence in the buffer."""
        while True:
            if self._dispatched >= self._max_sentences:
                # Cap reached — drop the rest of the stream silently. The
                # legacy ``stream_direct_tts`` does the same via slice.
                self._buffer = ""
                return
            match = self._sentence_end_re.search(self._buffer)
            if not match:
                return
            end = match.end()
            sentence = self._buffer[:end].strip()
            self._buffer = self._buffer[end:]
            if sentence:
                self._dispatch(sentence)

    def _dispatch(self, sentence: str) -> None:
        """Spawn a TTS task for the given sentence."""
        idx = self._dispatched
        self._dispatched += 1
        if self._on_chars_synthesized is not None:
            try:
                self._on_chars_synthesized(len(sentence))
            except Exception:
                # Tracking callback failures must never break the stream.
                logger.warning("tts_chars_callback_failed", phrase_index=idx)
        task = asyncio.create_task(self._synth_and_queue(sentence, idx))
        self._tasks.append(task)
        task.add_done_callback(self._maybe_close_queue)

    async def _synth_and_queue(self, sentence: str, idx: int) -> None:
        """Synthesise the sentence and stage the resulting chunk for in-order
        emission. Errors are logged and the slot is marked as failed so the
        rest of the stream keeps flowing.
        """
        chunk: VoiceAudioChunk | None = None
        try:
            audio_b64 = await self._synth(sentence)
            duration_ms = len(sentence) * VOICE_TTS_MS_PER_CHAR_HEURISTIC
            mime = AUDIO_MIME_TYPES.get(self._audio_format, DEFAULT_AUDIO_MIME_TYPE)
            chunk = VoiceAudioChunk(
                audio_base64=audio_b64,
                phrase_index=idx,
                phrase_text=sentence,
                is_last=False,  # is_last is signalled by the queue sentinel
                duration_ms=duration_ms,
                mime_type=mime,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — keep stream resilient
            logger.error(
                "progressive_sentence_synth_error",
                phrase_index=idx,
                sentence_length=len(sentence),
                error=str(exc),
                error_type=type(exc).__name__,
            )
            chunk = None  # mark as failed so the slot is skipped in-order

        await self._stage_and_drain(idx, chunk)

    async def _stage_and_drain(self, idx: int, chunk: VoiceAudioChunk | None) -> None:
        """Park the chunk by phrase_index, then push every contiguous chunk
        starting at ``_next_emit_idx`` to the consumer queue.

        Holding ``_drain_lock`` guarantees the queue receives chunks strictly
        in dispatch order even when several TTS tasks finish concurrently.
        """
        async with self._drain_lock:
            if chunk is not None:
                self._pending[idx] = chunk
            else:
                self._failed.add(idx)

            while self._next_emit_idx in self._pending or self._next_emit_idx in self._failed:
                if self._next_emit_idx in self._pending:
                    ready = self._pending.pop(self._next_emit_idx)
                    if self._first_audio_time is None:
                        self._first_audio_time = time.time()
                    await self._queue.put(ready)
                else:
                    # Failed slot — skip silently so the consumer keeps moving.
                    self._failed.discard(self._next_emit_idx)
                self._next_emit_idx += 1

    def _maybe_close_queue(self, task: asyncio.Task[Any]) -> None:
        """``add_done_callback`` hook — re-runs the close check after each
        task finishes."""
        self._try_close_queue()

    def _try_close_queue(self) -> None:
        """Push the sentinel once the input is closed AND every task is done
        AND every dispatched index has been emitted (or skipped).

        The triple condition matters: a failing task may complete instantly
        while a slow one is still synthesising — without the index check we
        would close the queue prematurely and drop in-flight chunks.
        """
        if not self._input_closed:
            return
        if self._tasks and not all(t.done() for t in self._tasks):
            return
        if self._next_emit_idx < self._dispatched:
            # Some slots are still pending in-order delivery — wait until
            # the corresponding _stage_and_drain calls finish their drain
            # loop. Each one re-runs this check via add_done_callback.
            return
        self._push_sentinel()

    def _push_sentinel(self) -> None:
        """Push the ``None`` end-of-stream marker exactly once."""
        if self._sentinel_pushed:
            return
        self._sentinel_pushed = True
        # Queue is unbounded so this should never happen — but the flag
        # is already set, so a future caller will short-circuit instead
        # of retrying forever.
        with suppress(asyncio.QueueFull):
            self._queue.put_nowait(None)
