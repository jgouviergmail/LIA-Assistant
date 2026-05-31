"""Unit tests for the reasoning-streaming helper.

Covers the four load-bearing guarantees, with no network/LLM:
- provider-agnostic delta extraction (content_blocks + reasoning_content);
- coalescer flush rules (min_chars / interval / sentence) + per-node cap;
- emit safety (never propagates an exception);
- ``stream_reasoning_events`` parity: returns the terminal output unchanged,
  and emits the streamed reasoning.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from src.core.constants import REASONING_MAX_CHARS_PER_NODE
from src.infrastructure.llm.reasoning_stream import (
    ReasoningCoalescer,
    extract_reasoning_delta,
    stream_reasoning_events,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _Chunk:
    """Minimal stand-in for an AIMessageChunk (content_blocks + additional_kwargs)."""

    def __init__(
        self,
        content_blocks: list[dict[str, Any]] | None = None,
        additional_kwargs: dict[str, Any] | None = None,
    ) -> None:
        if content_blocks is not None:
            self.content_blocks = content_blocks
        self.additional_kwargs = additional_kwargs or {}


def _stream_event(chunk: Any) -> dict[str, Any]:
    return {"event": "on_chat_model_stream", "data": {"chunk": chunk}, "parent_ids": ["root"]}


def _end_event(event: str, output: Any, *, root: bool) -> dict[str, Any]:
    """Build a terminal event; ``root`` controls parent_ids ([] = root runnable)."""
    return {"event": event, "data": {"output": output}, "parent_ids": [] if root else ["root"]}


class _FakeRunnable:
    """astream_events stub yielding a scripted sequence of events."""

    def __init__(self, events: list[dict[str, Any]]) -> None:
        self._events = events
        self.seen_config: Any = None

    async def astream_events(self, payload: Any, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        self.seen_config = kwargs.get("config")
        for ev in self._events:
            yield ev


class _Clock:
    """Deterministic monotonic clock for coalescer interval tests."""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


# ---------------------------------------------------------------------------
# extract_reasoning_delta
# ---------------------------------------------------------------------------


class TestExtractReasoningDelta:
    def test_content_blocks_reasoning(self) -> None:
        ev = _stream_event(_Chunk(content_blocks=[{"type": "reasoning", "reasoning": "step 1"}]))
        assert extract_reasoning_delta(ev) == "step 1"

    def test_content_blocks_thinking(self) -> None:
        ev = _stream_event(_Chunk(content_blocks=[{"type": "thinking", "thinking": "hmm"}]))
        assert extract_reasoning_delta(ev) == "hmm"

    def test_content_blocks_summary(self) -> None:
        """OpenAI reasoning-summary blocks expose the text under ``summary``."""
        ev = _stream_event(_Chunk(content_blocks=[{"type": "reasoning", "summary": "calc"}]))
        assert extract_reasoning_delta(ev) == "calc"

    def test_additional_kwargs_reasoning_content(self) -> None:
        """DeepSeek-style fallback."""
        ev = _stream_event(_Chunk(additional_kwargs={"reasoning_content": "deepseek thought"}))
        assert extract_reasoning_delta(ev) == "deepseek thought"

    def test_content_blocks_take_precedence_over_kwargs(self) -> None:
        ev = _stream_event(
            _Chunk(
                content_blocks=[{"type": "reasoning", "reasoning": "block"}],
                additional_kwargs={"reasoning_content": "kwarg"},
            )
        )
        assert extract_reasoning_delta(ev) == "block"

    def test_text_block_is_not_reasoning(self) -> None:
        """A plain text block (the answer) is not treated as reasoning."""
        ev = _stream_event(_Chunk(content_blocks=[{"type": "text", "text": "answer"}]))
        assert extract_reasoning_delta(ev) is None

    def test_non_stream_event_returns_none(self) -> None:
        assert extract_reasoning_delta({"event": "on_chain_end", "data": {}}) is None

    def test_missing_chunk_returns_none(self) -> None:
        assert extract_reasoning_delta({"event": "on_chat_model_stream", "data": {}}) is None

    def test_empty_chunk_returns_none(self) -> None:
        ev = _stream_event(_Chunk())
        assert extract_reasoning_delta(ev) is None


# ---------------------------------------------------------------------------
# ReasoningCoalescer
# ---------------------------------------------------------------------------


class TestReasoningCoalescer:
    def test_flush_on_min_chars(self) -> None:
        out: list[str] = []
        clock = _Clock()
        c = ReasoningCoalescer(out.append, min_chars=10, interval_ms=10_000, monotonic=clock)
        c.feed("12345")  # 5 chars, below threshold, no sentence end
        assert out == []
        c.feed("67890")  # reaches 10 chars -> flush
        assert out == ["1234567890"]

    def test_flush_on_interval(self) -> None:
        out: list[str] = []
        clock = _Clock()
        c = ReasoningCoalescer(out.append, min_chars=1000, interval_ms=100, monotonic=clock)
        c.feed("ab")
        assert out == []  # below min_chars, interval not elapsed
        clock.advance(0.2)  # 200ms > 100ms
        c.feed("cd")
        assert out == ["abcd"]

    def test_flush_on_sentence_boundary(self) -> None:
        out: list[str] = []
        clock = _Clock()
        c = ReasoningCoalescer(out.append, min_chars=1000, interval_ms=10_000, monotonic=clock)
        c.feed("short.")  # ends with '.' -> immediate flush
        assert out == ["short."]

    def test_close_flushes_trailing(self) -> None:
        out: list[str] = []
        clock = _Clock()
        c = ReasoningCoalescer(out.append, min_chars=1000, interval_ms=10_000, monotonic=clock)
        c.feed("trailing")
        assert out == []
        c.close()
        assert out == ["trailing"]

    def test_close_is_idempotent(self) -> None:
        out: list[str] = []
        c = ReasoningCoalescer(out.append, min_chars=1000, interval_ms=10_000, monotonic=_Clock())
        c.feed("x")
        c.close()
        c.close()
        assert out == ["x"]

    def test_per_node_cap_truncates_and_stops(self) -> None:
        out: list[str] = []
        clock = _Clock()
        c = ReasoningCoalescer(
            out.append, min_chars=1, interval_ms=10_000, max_chars=5, monotonic=clock
        )
        c.feed("abc")  # flush "abc" (3/5)
        c.feed("defgh")  # only "de" fits (cap 5) -> truncated, then capped
        c.feed("ignored")  # dropped (capped)
        c.close()
        assert "".join(out) == "abcde"
        assert len("".join(out)) == 5

    def test_emit_exception_is_swallowed(self) -> None:
        def boom(_text: str) -> None:
            raise RuntimeError("frontend gone")

        c = ReasoningCoalescer(boom, min_chars=1, interval_ms=10_000, monotonic=_Clock())
        # Must not raise — surfacing reasoning never breaks the node.
        c.feed("x")
        c.close()

    def test_empty_delta_ignored(self) -> None:
        out: list[str] = []
        c = ReasoningCoalescer(out.append, min_chars=1, interval_ms=10_000, monotonic=_Clock())
        c.feed("")
        c.close()
        assert out == []

    def test_default_cap_constant_used(self) -> None:
        """Sanity: the helper wires the centralized cap constant."""
        out: list[str] = []
        c = ReasoningCoalescer(out.append, min_chars=1, interval_ms=10_000, monotonic=_Clock())
        big = "z" * (REASONING_MAX_CHARS_PER_NODE + 100)
        c.feed(big)
        c.close()
        assert len("".join(out)) == REASONING_MAX_CHARS_PER_NODE


# ---------------------------------------------------------------------------
# stream_reasoning_events  (parity + emission)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestStreamReasoningEvents:
    async def test_returns_root_chain_end_output_and_emits_reasoning(self) -> None:
        """Root on_chain_end output is returned verbatim; reasoning is emitted."""
        sentinel = {"intent": "action", "domain": "email"}
        events = [
            _stream_event(
                _Chunk(content_blocks=[{"type": "reasoning", "reasoning": "thinking. "}])
            ),
            _stream_event(_Chunk(additional_kwargs={"reasoning_content": "more. "})),
            _end_event("on_chain_end", sentinel, root=True),
        ]
        runnable = _FakeRunnable(events)
        emitted: list[str] = []

        result = await stream_reasoning_events(
            runnable,  # type: ignore[arg-type]
            "payload",
            emit=emitted.append,
            config={"callbacks": []},
        )

        assert result is sentinel  # parity: root output returned unchanged
        assert "".join(emitted) == "thinking. more. "
        assert runnable.seen_config == {"callbacks": []}  # config propagated

    async def test_root_chat_model_end_for_raw_llm(self) -> None:
        """Raw-LLM path: the root on_chat_model_end output is captured."""
        msg = object()
        events = [
            _stream_event(_Chunk(content_blocks=[{"type": "reasoning", "reasoning": "r"}])),
            _end_event("on_chat_model_end", msg, root=True),
        ]
        result = await stream_reasoning_events(
            _FakeRunnable(events), "p", emit=lambda _t: None  # type: ignore[arg-type]
        )
        assert result is msg

    async def test_nested_chain_end_does_not_override_root(self) -> None:
        """A nested (non-root) on_chain_end must NOT override the root output."""
        inner = {"inner": "parser-internal"}
        root = {"intent": "action", "domain": "email"}
        events = [
            _stream_event(_Chunk(additional_kwargs={"reasoning_content": "t"})),
            _end_event("on_chat_model_end", object(), root=False),  # inner LLM end
            _end_event("on_chain_end", inner, root=False),  # inner parser end
            _end_event("on_chain_end", root, root=True),  # ROOT structured output
        ]
        result = await stream_reasoning_events(
            _FakeRunnable(events), "p", emit=lambda _t: None  # type: ignore[arg-type]
        )
        assert result is root

    async def test_root_selected_even_if_emitted_before_nested_end(self) -> None:
        """Root selection is order-independent (root may not be the last event)."""
        root = {"k": "v"}
        events = [
            _end_event("on_chain_end", root, root=True),
            _end_event("on_chain_end", {"late": "nested"}, root=False),
        ]
        result = await stream_reasoning_events(
            _FakeRunnable(events), "p", emit=lambda _t: None  # type: ignore[arg-type]
        )
        assert result is root

    async def test_fallback_when_parent_ids_absent(self) -> None:
        """If parent_ids is missing (non-v2), fall back: chain end > chat end."""
        chat_out = object()
        chain_out = {"k": "v"}
        events = [
            {"event": "on_chat_model_end", "data": {"output": chat_out}},
            {"event": "on_chain_end", "data": {"output": chain_out}},
        ]
        result = await stream_reasoning_events(
            _FakeRunnable(events), "p", emit=lambda _t: None  # type: ignore[arg-type]
        )
        assert result is chain_out

    async def test_no_terminal_event_returns_none(self) -> None:
        events = [_stream_event(_Chunk(additional_kwargs={"reasoning_content": "x"}))]
        result = await stream_reasoning_events(
            _FakeRunnable(events), "p", emit=lambda _t: None  # type: ignore[arg-type]
        )
        assert result is None

    async def test_no_reasoning_still_returns_output(self) -> None:
        """A provider that emits no reasoning still yields the final output."""
        out = {"ok": True}
        events = [
            _stream_event(_Chunk(content_blocks=[{"type": "text", "text": "answer"}])),
            _end_event("on_chain_end", out, root=True),
        ]
        emitted: list[str] = []
        result = await stream_reasoning_events(
            _FakeRunnable(events), "p", emit=emitted.append  # type: ignore[arg-type]
        )
        assert result is out
        assert emitted == []
