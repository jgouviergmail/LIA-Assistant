"""Live streaming of agent reasoning (thinking) to the progress UI.

Surfaces the chain-of-thought of any pre-``response`` node that runs a
thinking-enabled model, as incremental deltas pushed through LangGraph's
``custom`` stream channel — the same transport ``compaction_node`` uses.
The reasoning is rendered in a dedicated "💭" block, interleaved with the
existing execution steps, and is wiped when the final answer starts streaming
(handled frontend-side, identical to the step accumulator).

Design (validated by prod POCs against deepseek / OpenAI / Anthropic / Gemini):

- **Provider-agnostic capture** — :func:`extract_reasoning_delta` reads the
  normalized ``content_blocks`` (``type`` ``reasoning`` / ``thinking``) that
  LangChain Core 1.2+ produces for every provider, falling back to the
  ``additional_kwargs.reasoning_content`` field used by DeepSeek.
- **Same-call, zero-regression** — :func:`stream_reasoning_events` consumes the
  LLM via ``astream_events`` and returns the *final* output (the ``on_chain_end``
  / ``on_chat_model_end`` payload). That payload is byte-identical to ``ainvoke``
  (proven: structured JSON strictly equal), so routing/planning/tool-calls are
  unchanged and the parent's parsing keeps working as-is.
- **Anti-flood** — :class:`ReasoningCoalescer` batches deltas (providers emit
  hundreds of fragments per call) so the SSE stream stays smooth.
- **Never breaks the node** — the emit callback is wrapped so a writer failure
  (e.g. ``get_stream_writer`` unavailable outside a graph run, or a transport
  error) degrades to a no-op; the LLM call proceeds normally.

This module performs capture + coalescing only. The SSE emit binding lives in
:func:`make_reasoning_emit`; the frontend rendering + wipe-on-answer is handled
in ``apps/web/src/lib/sse-handlers/handlers.ts``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from src.core.constants import (
    REASONING_ANTHROPIC_BIND_BUDGET_TOKENS,
    REASONING_COALESCE_INTERVAL_MS,
    REASONING_COALESCE_MIN_CHARS,
    REASONING_MAX_CHARS_PER_NODE,
    REASONING_SSE_STEP_TYPE,
)
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from langchain_core.runnables import Runnable

logger = get_logger(__name__)

__all__ = [
    "extract_reasoning_delta",
    "ReasoningCoalescer",
    "make_reasoning_emit",
    "stream_reasoning_events",
]

# Sentence-ending characters that trigger an early coalescer flush so the UI
# shows complete thoughts rather than mid-word fragments when possible.
_SENTENCE_ENDINGS = (".", "!", "?", "\n")


def extract_reasoning_delta(event: dict[str, Any]) -> str | None:
    """Extract a reasoning text fragment from a single ``astream_events`` item.

    Provider-agnostic: reads the normalized ``content_blocks`` first (OpenAI
    reasoning summary, Anthropic thinking, Gemini thoughts), then falls back to
    the DeepSeek-style ``additional_kwargs.reasoning_content``.

    Args:
        event: One item yielded by ``Runnable.astream_events(..., version="v2")``.

    Returns:
        The reasoning fragment for this chunk, or ``None`` when the event is not
        a model-stream chunk or carries no reasoning.
    """
    if event.get("event") != "on_chat_model_stream":
        return None

    chunk = event.get("data", {}).get("chunk")
    if chunk is None:
        return None

    # 1) Normalized content blocks (LangChain Core 1.2+) — the canonical,
    #    cross-provider source. Accessing ``content_blocks`` can raise on exotic
    #    content shapes, so it is defensively guarded.
    try:
        blocks = getattr(chunk, "content_blocks", None)
    except Exception:  # pragma: no cover - defensive: never break capture
        blocks = None
    if blocks:
        for block in blocks:
            if isinstance(block, dict) and block.get("type") in ("reasoning", "thinking"):
                text = block.get("reasoning") or block.get("thinking") or block.get("summary")
                if text:
                    return str(text)

    # 2) Provider-specific fallback (DeepSeek exposes reasoning_content here).
    additional = getattr(chunk, "additional_kwargs", None) or {}
    if isinstance(additional, dict):
        for key in ("reasoning_content", "reasoning", "thinking"):
            value = additional.get(key)
            if value:
                return str(value)

    return None


class ReasoningCoalescer:
    """Batch reasoning deltas before emitting, to avoid flooding the SSE stream.

    Providers emit reasoning at wildly different granularity (DeepSeek ~336,
    qwen ~687 fragments per call). Forwarding each fragment individually would
    overwhelm the client. This coalescer accumulates fragments and flushes when
    any of these holds:

    - the buffered length reaches ``min_chars``;
    - ``interval_ms`` has elapsed since the last flush (wall-clock via the
      injected ``monotonic`` callable);
    - the buffer ends on a sentence boundary.

    A per-node character cap (``max_chars``) bounds the total emitted volume so
    a runaway thinking budget cannot flood the UI; once reached, further deltas
    are dropped silently.

    The emit callable is invoked with the coalesced text. Any exception it
    raises is swallowed — surfacing reasoning must never break the LLM call.
    """

    def __init__(
        self,
        emit: Callable[[str], None],
        *,
        min_chars: int = REASONING_COALESCE_MIN_CHARS,
        interval_ms: int = REASONING_COALESCE_INTERVAL_MS,
        max_chars: int = REASONING_MAX_CHARS_PER_NODE,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        """Initialize the coalescer.

        Args:
            emit: Callback receiving each coalesced text batch.
            min_chars: Flush threshold on buffered length.
            interval_ms: Flush threshold on elapsed wall-clock since last flush.
            max_chars: Hard cap on total characters emitted for this node.
            monotonic: Monotonic clock source (injectable for tests). Defaults to
                ``time.monotonic``.
        """
        import time

        self._emit = emit
        self._min_chars = min_chars
        self._interval_s = interval_ms / 1000.0
        self._max_chars = max_chars
        self._monotonic = monotonic or time.monotonic

        self._buffer: list[str] = []
        self._buffered_len = 0
        self._emitted_total = 0
        self._last_flush = self._monotonic()
        self._capped = False

    def feed(self, delta: str) -> None:
        """Add a reasoning fragment, flushing if a threshold is crossed.

        Args:
            delta: Raw reasoning fragment from :func:`extract_reasoning_delta`.
        """
        if self._capped or not delta:
            return

        self._buffer.append(delta)
        self._buffered_len += len(delta)

        ends_sentence = delta.endswith(_SENTENCE_ENDINGS)
        elapsed = self._monotonic() - self._last_flush

        if self._buffered_len >= self._min_chars or elapsed >= self._interval_s or ends_sentence:
            self.flush()

    def flush(self) -> None:
        """Emit the buffered reasoning, respecting the per-node character cap."""
        if not self._buffer:
            return

        text = "".join(self._buffer)
        self._buffer.clear()
        self._buffered_len = 0
        self._last_flush = self._monotonic()

        # Enforce the per-node cap. Once reached, stop emitting entirely.
        remaining = self._max_chars - self._emitted_total
        if remaining <= 0:
            self._capped = True
            return
        if len(text) > remaining:
            text = text[:remaining]
            self._capped = True

        self._emitted_total += len(text)
        self._safe_emit(text)

    def close(self) -> None:
        """Flush any trailing buffered reasoning. Idempotent."""
        self.flush()

    def _safe_emit(self, text: str) -> None:
        try:
            self._emit(text)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(
                "reasoning_emit_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )


def make_reasoning_emit(node_name: str) -> Callable[[str], None]:
    """Build an emit callback that pushes reasoning deltas on the custom channel.

    Resolves LangGraph's per-node stream writer (``get_stream_writer``) once.
    Outside a graph run (e.g. unit tests) or when the symbol is unavailable, the
    returned callback is a no-op — so a node calling this never fails.

    The payload mirrors the ``execution_step`` shape forwarded verbatim by
    ``StreamingService._process_custom_chunk``: a ``reasoning`` sub-type the
    frontend routes to the dedicated "💭" block.

    Args:
        node_name: Logical node name (e.g. ``"query_analyzer"``) for the UI.

    Returns:
        A callback taking the coalesced reasoning text.
    """
    try:
        from langgraph.config import get_stream_writer

        writer = get_stream_writer()
    except Exception:
        writer = None

    if writer is None:
        return lambda _text: None

    def emit(text: str) -> None:
        if not text:
            return
        try:
            writer(
                {
                    "type": "execution_step",
                    "step_type": REASONING_SSE_STEP_TYPE,
                    "metadata": {
                        "emoji": "💭",
                        "node": node_name,
                        "delta": text,
                    },
                }
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(
                "reasoning_writer_failed",
                node=node_name,
                error=str(exc),
                error_type=type(exc).__name__,
            )

    return emit


def _reasoning_bind_kwargs(runnable: Any) -> dict[str, Any]:
    """Provider-specific kwargs that EXPOSE the model's thoughts in the stream.

    Some providers compute their reasoning but do not emit it unless explicitly
    asked (Gemini ``include_thoughts``, Anthropic ``thinking``). This returns the
    minimal kwargs to surface that reasoning, to be applied via ``.bind()`` on a
    *derived* runnable used ONLY for the reasoning stream — never on the
    factory-built instance, so admin/per-agent config and all other call paths
    are untouched.

    Detection walks the runnable graph (a ``with_structured_output`` wrapper is a
    ``RunnableSequence`` whose first step is the chat model) and matches on class
    name, defensively: an unknown/unsupported provider yields ``{}`` (no bind,
    clean degradation — e.g. deepseek already emits reasoning, OpenAI/qwen have
    no safe bind here).

    Args:
        runnable: The runnable about to be streamed (chat model or structured).

    Returns:
        Kwargs for ``runnable.bind(**kwargs)``, or ``{}`` when nothing to add.
    """
    # A structured runnable (``with_structured_output``) is a RunnableSequence
    # (model | parser) that forces tool use via tool_choice. Some reasoning binds
    # are INCOMPATIBLE with forced tools and raise a hard 400 (Anthropic:
    # "Thinking may not be enabled when tool_choice forces tool use"). Detect it
    # explicitly so we skip those binds and degrade cleanly (no reasoning) rather
    # than break the call.
    is_structured = isinstance(getattr(runnable, "steps", None), list) and bool(runnable.steps)

    # Resolve the underlying chat model. Structured: steps[0] -> RunnableBinding
    # -> .bound = ChatModel. Raw bound LLM: .bound = ChatModel. Walk
    # ``steps[0]``/``bound``/``first`` until stable (depth-capped, cycle-safe).
    candidate: Any = runnable
    for _ in range(6):
        if isinstance(getattr(candidate, "steps", None), list) and candidate.steps:
            candidate = candidate.steps[0]
            continue
        inner = getattr(candidate, "bound", None) or getattr(candidate, "first", None)
        if inner is None or inner is candidate:
            break
        candidate = inner

    cls_name = type(candidate).__name__
    if "ChatGoogleGenerativeAI" in cls_name:
        # include_thoughts is compatible with tool_choice → safe everywhere.
        return {"include_thoughts": True}
    if "ChatAnthropic" in cls_name:
        if is_structured:
            # Anthropic thinking + forced tool_choice is rejected by the API.
            return {}
        return {
            "thinking": {
                "type": "enabled",
                "budget_tokens": REASONING_ANTHROPIC_BIND_BUDGET_TOKENS,
            }
        }
    # deepseek (already emits reasoning_content), OpenAI ResponsesLLM, qwen, etc.
    return {}


async def stream_reasoning_events(
    runnable: Runnable,
    payload: Any,
    *,
    emit: Callable[[str], None],
    config: Any | None = None,
    version: str = "v2",
) -> Any:
    """Run ``runnable`` via ``astream_events``, streaming reasoning, return final.

    Drop-in replacement for ``await runnable.ainvoke(payload, config)`` on any
    pre-``response`` node. Reasoning fragments are coalesced and forwarded via
    ``emit``; the returned value is the runnable's final output — proven
    byte-identical to ``ainvoke`` (structured JSON strictly equal in prod POCs),
    so the caller's downstream parsing/usage is unchanged.

    Token tracking is preserved: ``on_llm_end`` fires under ``astream_events``
    with full ``usage_metadata`` (proven), so the ``TokenTrackingCallback``
    propagated via ``config`` records tokens exactly as with ``ainvoke``.

    Args:
        runnable: An LLM or a ``with_structured_output`` runnable.
        payload: The input passed to ``astream_events`` (messages / prompt).
        emit: Callback for coalesced reasoning text (see :func:`make_reasoning_emit`).
        config: ``RunnableConfig`` to propagate (callbacks, metadata) — pass the
            node's config so token tracking and tracing stay intact.
        version: ``astream_events`` schema version (``"v2"``).

    Returns:
        The final output of the **root** runnable — the top-level ``*_end`` event
        whose ``parent_ids`` is empty (``on_chain_end`` for a structured runnable,
        ``on_chat_model_end`` for a raw LLM). Selecting on the root, rather than
        the last terminal event, is robust to nested runnables (parser, retry,
        fallback) that emit their own intermediate ``on_chain_end``. The returned
        value is byte-identical to ``ainvoke`` (proven). ``None`` if no root
        terminal event was observed (caller should treat as a failure and may
        fall back to ``ainvoke``).
    """
    coalescer = ReasoningCoalescer(emit)
    root_output: Any = None
    saw_root_output = False
    # Fallback capture for the (defensive) case where ``parent_ids`` is missing
    # — e.g. a non-v2 schema. Mirrors the pre-root-selection heuristic.
    fallback_output: Any = None
    saw_fallback_chain_end = False

    astream_kwargs: dict[str, Any] = {"version": version}
    if config is not None:
        astream_kwargs["config"] = config

    # Derive a reasoning-enabled runnable ONLY for this stream (see
    # _reasoning_bind_kwargs). .bind() returns a new runnable; the original
    # factory instance is untouched. Guarded: if bind fails for any reason, fall
    # back to the original runnable (reasoning may be absent, but never breaks).
    streaming_runnable: Any = runnable
    try:
        bind_kwargs = _reasoning_bind_kwargs(runnable)
        if bind_kwargs:
            streaming_runnable = runnable.bind(**bind_kwargs)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug(
            "reasoning_bind_failed",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        streaming_runnable = runnable

    async for event in streaming_runnable.astream_events(payload, **astream_kwargs):
        delta = extract_reasoning_delta(event)
        if delta:
            coalescer.feed(delta)

        event_type = event.get("event")
        if event_type not in ("on_chain_end", "on_chat_model_end"):
            continue

        output = event.get("data", {}).get("output")
        # Primary: the root runnable's terminal event (``parent_ids == []``).
        # ``parent_ids`` is a v2 guarantee ("Root Events will have an empty list").
        parent_ids = event.get("parent_ids")
        if parent_ids is not None and len(parent_ids) == 0:
            root_output = output
            saw_root_output = True

        # Fallback bookkeeping (only used if no root event is ever seen): prefer a
        # chain end (structured output) over a chat-model end (raw aggregated msg).
        if event_type == "on_chain_end":
            fallback_output = output
            saw_fallback_chain_end = True
        elif event_type == "on_chat_model_end" and not saw_fallback_chain_end:
            fallback_output = output

    coalescer.close()
    return root_output if saw_root_output else fallback_output
