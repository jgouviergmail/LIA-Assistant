"""The Claude request and stream policy, wired onto one ``ChatAnthropic`` (ADR-306, ADR-362).

The factory installs two instance-level hooks on every Claude client; both
survive ``.with_structured_output()`` and ``.bind_tools()``, which reuse the
instance:

* the REQUEST hook decides which earlier thinking the request carries back
  (``anthropic_thinking``, on LangChain's messages -- where each one still says
  which model wrote it), then hands the request body to
  :func:`shape_claude_payload`, the one payload policy (where the breakpoints
  sit decides the bill), with the lifetime the caller declared
  (``prompt_cache_horizon``);
* the STREAM hook copies the cache-write breakdown a streamed response reports
  at its START into the chunk the client builds there. ``langchain-anthropic``
  reads a stream's usage from its END, whose usage type carries the write total
  alone (``MessageDeltaUsage`` has no ``cache_creation`` in anthropic 0.122.0),
  so without it a stream could not say which of its writes were for the hour.
  The copy uses keys the client never writes, and the usage reader takes the
  larger of two sources, so a later client that reports the breakdown itself is
  never counted twice.

Both hooks lean on private methods of the client; the contract test drives the
real client (``test_anthropic_hooks.py``), so a version that renames them fails
there instead of under-billing in production. They are closures over THIS
instance: a pydantic copy of the client would carry hooks still bound to the
original, so the factory hooks every client it builds and nothing copies one.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from pydantic import BaseModel

from src.core.config import settings
from src.infrastructure.llm.prompt_cache_horizon import extended_horizon_requested
from src.infrastructure.llm.providers.anthropic_payload import shape_claude_payload
from src.infrastructure.llm.providers.anthropic_thinking import replay_prior_turn_thinking
from src.infrastructure.llm.usage_metadata import (
    STREAM_CACHE_WRITE_EXTENDED_KEY,
    STREAM_CACHE_WRITE_SHORT_KEY,
)
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_prompt_cache import (
    llm_cache_write_breakdown_missing_total,
)

logger = get_logger(__name__)

#: The lifetime keys of the SDK's ``CacheCreation`` (the stream start's usage).
_SHORT_LIFETIME = "ephemeral_5m_input_tokens"
_EXTENDED_LIFETIME = "ephemeral_1h_input_tokens"


def install_claude_hooks(llm: Any) -> None:
    """Install the request and stream hooks on a Claude client.

    An object lacking either private method (a test double) keeps what it has.

    Args:
        llm: The ``ChatAnthropic`` instance the factory built.
    """
    if hasattr(llm, "_get_request_payload"):
        _install_request_hook(llm)
    if hasattr(llm, "_make_message_chunk_from_anthropic_event"):
        _install_stream_hook(llm)


def _install_request_hook(llm: Any) -> None:
    original: Callable[..., dict[str, Any]] = llm._get_request_payload
    convert: Callable[[Any], Any] | None = getattr(llm, "_convert_input", None)
    receiver = str(getattr(llm, "model", "") or "")

    def _get_request_payload(input_: Any, stop: Any = None, **kwargs: Any) -> dict[str, Any]:
        # An invoke-time ``cache_control`` would land on the last message: the
        # policy owns every breakpoint.
        kwargs.pop("cache_control", None)
        if convert is not None:
            input_ = replay_prior_turn_thinking(
                convert(input_).to_messages(),
                receiver,
                enabled=settings.prior_turn_thinking_replay_enabled,
            )
        return shape_claude_payload(
            original(input_, stop=stop, **kwargs), extended_ttl=extended_horizon_requested()
        )

    llm._get_request_payload = _get_request_payload


def _install_stream_hook(llm: Any) -> None:
    original: Callable[..., tuple[Any, Any]] = llm._make_message_chunk_from_anthropic_event

    def _make_message_chunk(event: Any, **kwargs: Any) -> tuple[Any, Any]:
        chunk, block_start_event = original(event, **kwargs)
        if chunk is not None and getattr(event, "type", None) == "message_start":
            chunk = with_stream_write_breakdown(chunk, event)
        return chunk, block_start_event

    llm._make_message_chunk_from_anthropic_event = _make_message_chunk


def with_stream_write_breakdown(chunk: Any, event: Any) -> Any:
    """The stream start's chunk, carrying the lifetime breakdown of its writes.

    Args:
        chunk: The ``AIMessageChunk`` the client built for ``message_start``.
        event: The SDK's ``RawMessageStartEvent``.

    Returns:
        A copy of ``chunk`` whose usage also holds the breakdown, its own counts
        kept as they were (today the client puts them all on the stream's END,
        so they are 0 here), or ``chunk`` itself when there is nothing to carry.
    """
    message = getattr(event, "message", None)
    usage = getattr(message, "usage", None)
    breakdown = _as_mapping(getattr(usage, "cache_creation", None))
    if breakdown is None:
        written = _count(getattr(usage, "cache_creation_input_tokens", None))
        if written > 0:
            model = str(getattr(message, "model", "unknown"))
            llm_cache_write_breakdown_missing_total.labels(model=model).inc()
            logger.warning(
                "llm_cache_write_breakdown_missing", model=model, cache_write_tokens=written
            )
        return chunk
    short = _count(breakdown.get(_SHORT_LIFETIME))
    extended = _count(breakdown.get(_EXTENDED_LIFETIME))
    if short + extended == 0:
        return chunk
    merged: dict[str, Any] = dict(
        chunk.usage_metadata or {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    )
    merged["input_token_details"] = {
        **(merged.get("input_token_details") or {}),
        STREAM_CACHE_WRITE_SHORT_KEY: short,
        STREAM_CACHE_WRITE_EXTENDED_KEY: extended,
    }
    return chunk.model_copy(update={"usage_metadata": merged})


def _as_mapping(value: Any) -> Mapping[str, Any] | None:
    if isinstance(value, BaseModel):
        return value.model_dump()
    return value if isinstance(value, Mapping) else None


def _count(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


__all__ = ["install_claude_hooks", "with_stream_write_breakdown"]
