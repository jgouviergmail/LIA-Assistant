"""Follow-up suggestion sanitization + metadata enrichment (UXR Lot 4, A2).

The Initiative node (ADR-062) emits 0-3 tappable follow-up suggestions in the
user's language. This module owns their normalization (defense in depth over
the structured LLM output) and the branch-free enrichment of the archived
assistant message metadata — the same composable idiom as
``with_persisted_trace`` (``streaming/trace_capture.py``). The SSE ``done``
chunk carries the same list under ``FIELD_FOLLOWUP_SUGGESTIONS`` so the chips
render live and survive a reload while the answer stays the latest.
"""

from __future__ import annotations

import time as _time
from typing import Any

from src.core.constants import (
    INITIATIVE_FOLLOWUP_MAX_CHARS,
    INITIATIVE_FOLLOWUPS_MAX,
)
from src.core.field_names import FIELD_FOLLOWUP_SUGGESTIONS


def sanitize_followups(raw: list[str] | None) -> list[str]:
    """Normalize raw follow-up suggestions from the initiative LLM.

    Rules: non-strings dropped, whitespace stripped, inner newlines flattened
    to single spaces, empties dropped, case-insensitive dedupe (first wins),
    each entry clamped to ``INITIATIVE_FOLLOWUP_MAX_CHARS``, list capped at
    ``INITIATIVE_FOLLOWUPS_MAX``.

    Args:
        raw: Structured-output list, possibly absent or malformed.

    Returns:
        A clean, bounded list — empty when nothing usable remains.
    """
    if not raw:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        text = " ".join(item.split())[:INITIATIVE_FOLLOWUP_MAX_CHARS]
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= INITIATIVE_FOLLOWUPS_MAX:
            break
    return out


# ---------------------------------------------------------------------------
# Per-run handoff (initiative node → SSE generator)
# ---------------------------------------------------------------------------
# The service's `state` variable is the PRE-RUN snapshot (loaded before the
# graph streams — `agents/api/service.py` load_or_create_state) and is never
# refreshed, so reading the state key there would surface the PREVIOUS turn's
# chips. The node therefore pushes the sanitized list into this pop-once,
# TTL-evicted, per-run cache (same pattern and same same-process guarantee as
# `open_loop_extractor`'s debug cache).

_HANDOFF_MAX_AGE_SECONDS = 300.0
_pending_followups: dict[str, tuple[float, list[str]]] = {}


def _evict_stale_followups() -> None:
    now = _time.monotonic()
    stale = [
        run_id
        for run_id, (ts, _s) in _pending_followups.items()
        if now - ts > _HANDOFF_MAX_AGE_SECONDS
    ]
    for run_id in stale:
        _pending_followups.pop(run_id, None)


def push_followups(run_id: str, suggestions: list[str]) -> None:
    """Store a run's sanitized follow-ups for the SSE generator (last wins)."""
    _evict_stale_followups()
    _pending_followups[run_id] = (_time.monotonic(), list(suggestions))


def pop_followups(run_id: str) -> list[str]:
    """Pop a run's follow-ups (once) — empty list when none were emitted."""
    _evict_stale_followups()
    entry = _pending_followups.pop(run_id, None)
    return entry[1] if entry is not None else []


def with_followup_suggestions(
    metadata: dict[str, Any],
    suggestions: list[str],
) -> dict[str, Any]:
    """Return metadata enriched with the follow-up suggestions (new dict).

    Branch-free at the call site: an empty list returns the input untouched;
    otherwise a NEW dict is returned (mirror of the JSONB new-dict rule — the
    caller may hand the original to other enrichers).

    Args:
        metadata: Assistant message metadata being assembled at archive time.
        suggestions: Already-sanitized follow-up suggestions.

    Returns:
        The same dict when there is nothing to add, a new enriched dict else.
    """
    if not suggestions:
        return metadata
    return {**metadata, FIELD_FOLLOWUP_SUGGESTIONS: list(suggestions)}
