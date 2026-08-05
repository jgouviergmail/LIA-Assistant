"""Run-level in-memory collectors shared by every TrackingContext of a run.

All TrackingContext instances sharing the same ``run_id`` publish their
committed records here, so the debug panel can show EVERY LLM / Google API /
image-generation / TTS call of a run (pipeline + background tasks) in a
single view, on a single timeline (``anchor_run_start`` / ``run_offset_ms``).

Lifecycle:
    - Populated by ``TrackingContext._persist_to_database()`` after each commit
    - Read by the ``get_*_breakdown()`` methods and ``get_tts_debug``
    - Cleaned up by ``cleanup_run(run_id)`` once the debug panel has been
      emitted (``TrackingContext.cleanup_run_records`` delegates here)

Safety: these module-level dicts are safe under asyncio's single-threaded
cooperative model (no yield point between dict mutation operations). If the
server moves to multi-threaded workers, they MUST become thread-safe
structures (e.g. threading.Lock or per-request storage).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from src.core.constants import RUN_RECORDS_MAX_RUNS

if TYPE_CHECKING:
    from src.domains.chat.service import (
        GoogleApiRecord,
        ImageGenerationRecord,
        TokenUsageRecord,
        TTSUsageRecord,
    )

_run_records: dict[str, list[TokenUsageRecord]] = {}
_run_google_api_records: dict[str, list[GoogleApiRecord]] = {}
_run_image_generation_records: dict[str, list[ImageGenerationRecord]] = {}
_run_tts_records: dict[str, list[TTSUsageRecord]] = {}
# Run-level t0 (epoch seconds), anchored by the FIRST TrackingContext of the
# run. Every started_offset_ms is measured against it so pipeline and
# background contexts land on one timeline (debug-panel waterfall, v3.4).
_run_started_at: dict[str, float] = {}


def anchor_run_start(run_id: str) -> None:
    """Anchor the run t0 (first context of the run wins), bounded.

    A run that never records anything must not leak its anchor forever, so
    the anchor dict carries the same cap as the record collectors.

    Args:
        run_id: The pipeline run to anchor.
    """
    _run_started_at.setdefault(run_id, time.time())
    while len(_run_started_at) > RUN_RECORDS_MAX_RUNS:
        _run_started_at.pop(next(iter(_run_started_at)))


def run_offset_ms(run_id: str, started_at: float | None, duration_ms: float) -> float:
    """Position a call's start on the run timeline, in milliseconds.

    Measured against the run-level t0. Clamped at 0 (a start stamped before
    the anchor carries no usable position).

    Args:
        run_id: The run whose timeline the call belongs to.
        started_at: Epoch seconds when the call started, if known.
        duration_ms: Call duration, used to derive the start when
            ``started_at`` is absent (now − duration).

    Returns:
        Offset from the run t0 in milliseconds, >= 0.
    """
    t0 = _run_started_at.get(run_id)
    if t0 is None:
        # Anchor evicted or context built outside the normal path — re-anchor
        # now so subsequent calls of this run stay on one timeline.
        t0 = _run_started_at.setdefault(run_id, time.time())
    effective_start = started_at if started_at is not None else time.time() - duration_ms / 1000
    return max(0.0, (effective_start - t0) * 1000)


def cleanup_run(run_id: str) -> None:
    """Remove all collected records and the timeline anchor for a run.

    Args:
        run_id: The pipeline run_id to clean up.
    """
    _run_records.pop(run_id, None)
    _run_google_api_records.pop(run_id, None)
    _run_image_generation_records.pop(run_id, None)
    _run_tts_records.pop(run_id, None)
    _run_started_at.pop(run_id, None)


def evict_excess_runs() -> list[str]:
    """Evict the OLDEST run_ids beyond the cap (leak guard, F23 2026-07).

    Runs that never reach ``cleanup_run`` (errors, abandoned HITL
    interrupts) used to accumulate forever on a long-running server.

    Returns:
        The evicted run_ids (for the caller to log).
    """
    evicted: list[str] = []
    while len(_run_records) > RUN_RECORDS_MAX_RUNS:
        oldest_run_id = next(iter(_run_records))
        cleanup_run(oldest_run_id)
        evicted.append(oldest_run_id)
    return evicted


def get_tts_debug(run_id: str) -> dict[str, Any] | None:
    """Voice-synthesis debug payload for the panel (None when no TTS ran).

    TTS spend was tracked and billed but invisible in the debug panel; this
    read powers the ``voice`` family of the ``debug_metrics_update`` channel.
    Non-destructive on purpose: the records are still needed by the archive
    backfill, and ``cleanup_run`` releases them afterwards.

    Args:
        run_id: The pipeline run whose TTS calls to expose.

    Returns:
        Aggregate + per-call breakdown, or None when the run had no paid TTS.
    """
    records = _run_tts_records.get(run_id)
    if not records:
        return None
    return {
        "total_calls": len(records),
        "total_characters": sum(r.characters for r in records),
        "total_cost_eur": round(float(sum(r.cost_eur for r in records)), 6),
        "calls": [
            {
                "provider": r.provider,
                "model": r.model,
                "characters": r.characters,
                "cost_eur": float(r.cost_eur),
                "duration_ms": r.duration_ms,
            }
            for r in records
        ],
    }
