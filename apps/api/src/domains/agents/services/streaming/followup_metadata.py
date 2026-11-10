"""What a turn hands its stream besides the answer, and how it is archived.

The Initiative node (ADR-062) emits 0-3 tappable follow-up suggestions in the
user's language and a provenance line; the response node may add ONE habit
proposal card (ADR-375). This module owns their normalization (defense in
depth over the structured LLM output), the per-run handoff the stream pops
ONCE (:func:`pop_turn_extras`), and the branch-free enrichment of the archived
assistant message metadata — the same composable idiom as
``with_persisted_trace`` (``streaming/trace_capture.py``). The SSE ``done``
chunk carries the same values so the chips and the card render live and
survive a reload while the answer stays the latest.
"""

from __future__ import annotations

import time as _time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from src.core.constants import (
    INITIATIVE_FOLLOWUP_MAX_CHARS,
    INITIATIVE_FOLLOWUPS_MAX,
    INITIATIVE_MOTIVATION_MAX_CHARS,
)
from src.core.field_names import (
    FIELD_FOLLOWUP_SUGGESTIONS,
    FIELD_HABIT_PROPOSAL,
    FIELD_INITIATIVE_MOTIVATION,
)


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
# Per-run handoff (graph nodes → SSE generator)
# ---------------------------------------------------------------------------
# The service's `state` variable is the PRE-RUN snapshot (loaded before the
# graph streams — `agents/api/service.py` load_or_create_state) and is never
# refreshed, so reading the state key there would surface the PREVIOUS turn's
# chips. The nodes therefore push what they hand the stream into this
# pop-once, TTL-evicted, per-run cache (same pattern and same same-process
# guarantee as `open_loop_extractor`'s debug cache).

_HANDOFF_MAX_AGE_SECONDS = 300.0


class PerRunHandoff[T]:
    """Pop-once, TTL-evicted, per-run in-process cache (node → SSE generator).

    Factored out of the follow-ups handoff so every artifact a node hands the
    stream (the chips, the motivation, the habit proposal card) crosses the
    node/generator seam the same audited way.
    """

    def __init__(self) -> None:
        self._pending: dict[str, tuple[float, T]] = {}

    def _evict_stale(self) -> None:
        now = _time.monotonic()
        stale = [
            run_id
            for run_id, (ts, _v) in self._pending.items()
            if now - ts > _HANDOFF_MAX_AGE_SECONDS
        ]
        for run_id in stale:
            self._pending.pop(run_id, None)

    def push(self, run_id: str, value: T) -> None:
        """Store a run's value for the SSE generator (last wins)."""
        self._evict_stale()
        self._pending[run_id] = (_time.monotonic(), value)

    def pop(self, run_id: str) -> T | None:
        """Pop a run's value (once) — ``None`` when nothing was emitted."""
        self._evict_stale()
        entry = self._pending.pop(run_id, None)
        return entry[1] if entry is not None else None


_followups_handoff: PerRunHandoff[list[str]] = PerRunHandoff()
_motivation_handoff: PerRunHandoff[str] = PerRunHandoff()
_proposal_handoff: PerRunHandoff[dict[str, Any]] = PerRunHandoff()


def push_followups(run_id: str, suggestions: list[str]) -> None:
    """Store a run's sanitized follow-ups for the SSE generator (last wins)."""
    _followups_handoff.push(run_id, list(suggestions))


def pop_followups(run_id: str) -> list[str]:
    """Pop a run's follow-ups (once) — empty list when none were emitted."""
    return _followups_handoff.pop(run_id) or []


def sanitize_motivation(raw: str | None) -> str | None:
    """Normalize the initiative's provenance line (Lot 1-A3).

    Whitespace collapsed, clamped to ``INITIATIVE_MOTIVATION_MAX_CHARS``;
    ``None`` when nothing usable remains.
    """
    if not isinstance(raw, str):
        return None
    text = " ".join(raw.split())[:INITIATIVE_MOTIVATION_MAX_CHARS]
    return text or None


def push_motivation(run_id: str, motivation: str) -> None:
    """Store a run's sanitized provenance line (last wins)."""
    _motivation_handoff.push(run_id, motivation)


def pop_motivation(run_id: str) -> str | None:
    """Pop a run's provenance line (once) — ``None`` when absent."""
    return _motivation_handoff.pop(run_id)


@dataclass(frozen=True, slots=True)
class TurnExtras:
    """Everything a run handed its stream besides the answer, popped once.

    Attributes:
        followups: The initiative's sanitized follow-up chips.
        motivation: The initiative's provenance line, when any.
        habit_proposal: The habit proposal shown under the answer (ADR-375),
            as its JSON projection, when any.
    """

    followups: tuple[str, ...] = ()
    motivation: str | None = None
    habit_proposal: dict[str, Any] | None = None


#: A turn that hands nothing besides its answer.
NO_TURN_EXTRAS = TurnExtras()


def push_turn_proposal(run_id: str, proposal: dict[str, Any]) -> None:
    """Store the habit proposal a run shows under its answer (last wins)."""
    _proposal_handoff.push(run_id, proposal)


def pop_turn_extras(run_id: str) -> TurnExtras:
    """Pop every extra a run handed its stream, once, for the archive AND ``done``.

    Args:
        run_id: The run.

    Returns:
        The extras; :data:`NO_TURN_EXTRAS` when the run pushed none.
    """
    return TurnExtras(
        followups=tuple(pop_followups(run_id)),
        motivation=pop_motivation(run_id),
        habit_proposal=_proposal_handoff.pop(run_id),
    )


def with_followup_suggestions(
    metadata: dict[str, Any],
    suggestions: Sequence[str],
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


def with_initiative_motivation(
    metadata: dict[str, Any],
    motivation: str | None,
) -> dict[str, Any]:
    """Return metadata enriched with the provenance line (new dict).

    Branch-free at the call site: ``None`` returns the input untouched
    (same composable idiom as ``with_followup_suggestions``).
    """
    if not motivation:
        return metadata
    return {**metadata, FIELD_INITIATIVE_MOTIVATION: motivation}


def with_habit_proposal(
    metadata: dict[str, Any],
    proposal: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return metadata enriched with the habit proposal card (new dict, ADR-375).

    Branch-free at the call site: ``None`` returns the input untouched.

    Args:
        metadata: Assistant message metadata being assembled.
        proposal: The proposal's JSON projection, when the answer shows one.

    Returns:
        The same dict when there is nothing to add, a new enriched dict else.
    """
    if not proposal:
        return metadata
    return {**metadata, FIELD_HABIT_PROPOSAL: proposal}
