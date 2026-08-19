"""Per-run journal-extraction debug registry (extracted from extraction_service).

In-process dict storing extraction debug data keyed by run_id. Entries are
written by ``extract_journal_entry_background()`` and consumed (popped) by the
SSE streaming service. A TTL-based eviction prevents unbounded growth when
entries are never consumed (e.g., streaming error, debug panel disabled).

Extracted 2026-08-19 (file-size ratchet): ``extraction_service.py`` sits at
its frozen cap and this block is a self-contained store with two importers.
"""

from __future__ import annotations

import time as _time
from typing import Any

_EXTRACTION_DEBUG_TTL_SECONDS: int = 300  # 5 minutes

_extraction_debug_results: dict[str, tuple[float, dict[str, Any]]] = {}


def _evict_stale_debug_entries() -> None:
    """Drop entries older than the TTL — called on BOTH store and pop.

    Store-side eviction is what actually honours the "debug panel
    disabled" promise above: with pop-only eviction, a deployment that
    never opens the panel never pops, and the cache grew one entry per
    turn for the process lifetime (2026-07-22 counter-review).
    """
    now = _time.monotonic()
    stale_keys = [
        k
        for k, (ts, _) in _extraction_debug_results.items()
        if now - ts > _EXTRACTION_DEBUG_TTL_SECONDS
    ]
    for k in stale_keys:
        del _extraction_debug_results[k]


def store_extraction_debug(run_id: str, data: dict[str, Any]) -> None:
    """Store extraction debug results for a given run_id with a timestamp.

    Args:
        run_id: The pipeline run_id to associate the results with.
        data: Debug dict with actions_parsed, actions_applied, entries.
    """
    _evict_stale_debug_entries()
    _extraction_debug_results[run_id] = (_time.monotonic(), data)


def pop_extraction_debug(run_id: str) -> dict[str, Any] | None:
    """Pop and return extraction debug results for a given run_id.

    Called by the streaming service after await_run_id_tasks to include
    journal extraction details in the debug panel.

    Args:
        run_id: The pipeline run_id whose extraction results to retrieve.

    Returns:
        Debug dict with actions_parsed, actions_applied, entries details,
        or None if no results found for this run_id.
    """
    _evict_stale_debug_entries()
    entry = _extraction_debug_results.pop(run_id, None)
    return entry[1] if entry is not None else None
