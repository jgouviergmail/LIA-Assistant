"""What a condition routine has already seen (ADR-322).

The ledger used to hold ONE fingerprint of the whole matching set
(``last_fingerprint``), so ANY change to the set read as a new fact — a set
that shrank included. Checked twice a day that was rare; checked every ten
minutes it became the rule: an agenda watch re-fired each time an event ended,
a task watch each time a task was ticked off, a mail watch each time one of two
matching mails was read.

A fact is now new when its KEY was never seen. The evaluators produce the keys
(stable identities, hashed — no title, no subject, no address is stored here);
this module decides novelty and writes the ledger, which lives in
``scheduled_actions.condition_state``:

``{"seen": [key, ...], "last_checked_at": iso, "last_check_error": code | null,
"last_fired_at": iso | null}``

Three rules, none of them stylistic:

- **a new fact the tick did not serve stays new** — a daily cap reached, a
  question pending in the conversation, a run that failed: the next check tries
  again rather than losing what the person was waiting for;
- **a fact still present is never evicted** by the bound, or it would read as
  new the next time; the bound drops the facts that left longest ago;
- **every write is a NEW dict**: a JSONB column mutated in place is never
  saved (``test_jsonb_mutation_guard``).

A legacy ledger (a set fingerprint, no ``seen``) reads as having seen
nothing: the first check after the upgrade serves what it finds. Announcing an
awaited fact twice is recoverable; never announcing it is not.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Literal, get_args

#: How many fact keys a ledger keeps. Not a tunable: it only has to exceed
#: what one check can return (every source is capped by its own briefing
#: setting — the task page at four times it) plus the facts that left
#: recently; raising it costs bytes, lowering it could make a returning fact
#: read as new.
CONDITION_LEDGER_MAX_KEYS: Final[int] = 200

#: Why a check could not read its source. ``not_configured``: nothing to read
#: (no connector, no location) — the person can fix it. ``unavailable``: the
#: source was asked and did not answer.
ConditionCheckError = Literal["not_configured", "unavailable"]

CONDITION_CHECK_ERRORS: Final[frozenset[str]] = frozenset(get_args(ConditionCheckError))


def _parse_instant(raw: object) -> datetime | None:
    """An ISO instant written by this module, or ``None``."""
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class ConditionLedger:
    """The stored ledger of one condition routine, read forgivingly.

    Attributes:
        seen: Fact keys already seen, most recent first.
        last_checked_at: When the condition was last checked.
        last_check_error: Why the last check could not read its source.
        last_fired_at: The stored instant of the last served check, carried
            as written.
    """

    seen: tuple[str, ...]
    last_checked_at: datetime | None
    last_check_error: ConditionCheckError | None
    last_fired_at: str | None

    @classmethod
    def read(cls, state: Mapping[str, Any] | None) -> ConditionLedger:
        """The ledger stored in ``condition_state``.

        Args:
            state: The column's value, possibly ``None`` or a legacy shape.

        Returns:
            The ledger; anything malformed reads as empty rather than crashing
            a background tick.
        """
        state = state or {}
        raw_seen = state.get("seen")
        seen = (
            tuple(key for key in raw_seen if isinstance(key, str))
            if isinstance(raw_seen, list)
            else ()
        )
        raw_error = state.get("last_check_error")
        error: ConditionCheckError | None = (
            raw_error if raw_error == "not_configured" or raw_error == "unavailable" else None
        )
        raw_fired = state.get("last_fired_at")
        return cls(
            seen=seen,
            last_checked_at=_parse_instant(state.get("last_checked_at")),
            last_check_error=error,
            last_fired_at=raw_fired if isinstance(raw_fired, str) else None,
        )

    def new_keys(self, keys: Iterable[str]) -> list[str]:
        """The keys never seen, in the order they came, each once.

        Args:
            keys: What a check saw.

        Returns:
            The new ones.
        """
        known = set(self.seen)
        fresh: list[str] = []
        for key in keys:
            if key not in known:
                known.add(key)
                fresh.append(key)
        return fresh

    def after_check(
        self,
        *,
        at: datetime,
        present: Sequence[str],
        fired: bool,
        error: ConditionCheckError | None = None,
    ) -> dict[str, Any]:
        """The ledger to store once a check has ended.

        Args:
            at: When the check ran (UTC).
            present: Every fact key the check saw — empty when it could not read.
            fired: Whether the check's new facts were served (a run that
                answered, or a proposal sent). When ``False`` they stay new.
            error: Why the source could not be read, if it could not.

        Returns:
            A NEW dict for ``condition_state``.
        """
        known = set(self.seen)
        kept = list(dict.fromkeys(present if fired else [k for k in present if k in known]))
        kept_set = set(kept)
        merged = kept + [key for key in self.seen if key not in kept_set]
        return {
            "seen": merged[: max(CONDITION_LEDGER_MAX_KEYS, len(kept))],
            "last_checked_at": at.isoformat(),
            "last_check_error": error,
            "last_fired_at": at.isoformat() if fired else self.last_fired_at,
        }


__all__ = [
    "CONDITION_CHECK_ERRORS",
    "CONDITION_LEDGER_MAX_KEYS",
    "ConditionCheckError",
    "ConditionLedger",
]
