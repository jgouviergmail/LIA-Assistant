"""The deferred half of the debug panel, as one door (B8).

Two families of debug data cannot be in the payload emitted with the answer:

- **the background extractions** (journals, open loops) run fire-and-forget and
  have only just been awaited;
- **the two DEFERRED registers of ADR-263** — what the turn CONSULTED and the
  turn's own record — are captured before their collectors close, then handed
  here explicitly after accounting. The recording contexts are no longer active.

Both reach the browser on the ``debug_metrics_update`` channel, which the
frontend merges into the panel. They are assembled here rather than at the call
site for a measured reason: the streaming entry point is this codebase's worst
complexity hotspot, and every ``try`` and every ``for`` added there is paid by
the whole function.

**Nothing here may cost the user their answer.** The answer is already written
by the time this runs, so each family is guarded on its own: a failure logs and
yields nothing rather than breaking the stream.
"""

from __future__ import annotations

from collections.abc import Iterator

from src.domains.agents.api.schemas import ChatStreamChunk
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

__all__ = ["capture_registers_debug", "deferred_debug_chunks"]


def _extraction_chunks(run_id: str) -> Iterator[ChatStreamChunk]:
    """One chunk per populated background-extraction family.

    Args:
        run_id: The run whose pop-once debug caches to drain.

    Yields:
        The merge chunks.
    """
    try:
        from src.domains.agents.services.streaming.extraction_debug import (
            pop_background_extraction_debug,
        )

        for key, payload in pop_background_extraction_debug(run_id):
            yield ChatStreamChunk(type="debug_metrics_update", content="", metadata={key: payload})
    except Exception as err:  # noqa: BLE001 - the answer must survive this
        logger.debug("debug_metrics_extraction_emit_failed", run_id=run_id, error=str(err))


def capture_registers_debug(run_id: str, *, enabled: bool) -> dict[str, object] | None:
    """Snapshot the live registers before their recording scopes close.

    The snapshot says what was observed, never whether persistence succeeded.
    A capture failure must not interrupt an answer that was already produced.

    Args:
        run_id: The run, for the failure log only.
        enabled: Whether this reader may receive debug output.

    Returns:
        The detached payload, or None when disabled, unavailable or outside a turn.
    """
    if not enabled:
        return None
    try:
        from src.domains.agents.services.streaming.register_debug import registers_debug

        return registers_debug()
    except Exception as err:  # noqa: BLE001 - the answer must survive this
        logger.debug("debug_metrics_registers_emit_failed", run_id=run_id, error=str(err))
        return None


def deferred_debug_chunks(
    run_id: str, *, registers: dict[str, object] | None
) -> Iterator[ChatStreamChunk]:
    """Everything the panel learns after the answer was sent.

    Args:
        run_id: The run being streamed.
        registers: The snapshot captured before this run's recording scopes closed.

    Yields:
        The ``debug_metrics_update`` chunks, in the order the panel merges them.
    """
    yield from _extraction_chunks(run_id)
    if registers is not None:
        yield ChatStreamChunk(
            type="debug_metrics_update", content="", metadata={"registers": registers}
        )
