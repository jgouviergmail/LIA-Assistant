"""What the transparency register keeps of the radio (ADR-263, ADR-324 decision 31).

The radio's model calls were already in the ledger (every euro under the
session's run) and its reads in the consultation register (``consultations``);
the run they are filed under pointed at nothing, so the register's overview —
the turns of a day, how they ended — never saw a radio session happen. Two acts
now take one row each in the decision register, under the run their euros and
reads already carry:

- a SESSION, filed when it ends, by whoever sees the end — its loop, or the
  service closing a session no loop holds. Two of them may race, so the row is
  written ONCE (``record_decision_once``): the first filing stands;
- an ARTICLE translated on opening, filed when the call returns — a reading
  served from the cache called no model and files nothing.

Neither is an ACTION: nothing of the person's changed. Both were asked for by
the listener, so their authorship is ``user`` — like the session's
consultations — and neither ever appears among LIA's initiatives.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from types import MappingProxyType
from typing import Final
from uuid import UUID

from src.domains.agents.effects.decision_recorder import record_decision_once
from src.domains.agents.effects.decisions import out_of_turn_decision
from src.domains.agents.effects.models import DecisionOutcome, EffectSource
from src.domains.radio.session import EndReason

#: The route a session's row reads as — what a chat turn's router would have decided.
SESSION_ROUTE: Final[str] = "radio"
#: The route of an article translated on opening.
ARTICLE_ROUTE: Final[str] = "radio_article"

#: How each end reads in the register: its outcome, and why it stopped when it
#: did not run to its plan. A listener ending the programme is its ordinary end,
#: said as such; nobody listening or a spending ceiling cut it short; failing
#: productions are a failure.
END_OUTCOMES: Final[Mapping[EndReason, tuple[DecisionOutcome, str | None]]] = MappingProxyType(
    {
        EndReason.TIMER: (DecisionOutcome.ANSWERED, None),
        EndReason.LISTENER: (DecisionOutcome.ANSWERED, EndReason.LISTENER.value),
        EndReason.IDLE: (DecisionOutcome.INTERRUPTED, EndReason.IDLE.value),
        EndReason.BUDGET: (DecisionOutcome.INTERRUPTED, EndReason.BUDGET.value),
        EndReason.FAILURES: (DecisionOutcome.FAILED, EndReason.FAILURES.value),
    }
)

# A new way to end, left out of the table, would be filed as nothing: refuse to import.
_UNMAPPED = set(EndReason) - set(END_OUTCOMES)
if _UNMAPPED:
    raise RuntimeError(f"radio ends without a register outcome: {sorted(_UNMAPPED)}")


async def file_session(
    *, user_id: UUID, run_id: str, started_at: datetime, reason: EndReason
) -> None:
    """File a session that ended — once, whoever closes it. Never raises.

    Args:
        user_id: The listener who started it.
        run_id: The session's run, every euro and read of it already filed under.
        started_at: When the listener started it.
        reason: Why it ended.
    """
    decision = out_of_turn_decision(
        run_id=run_id, user_id=user_id, thread_id=run_id, source=EffectSource.USER.value
    )
    decision.route = SESSION_ROUTE
    decision.started_at = started_at
    decision.outcome, decision.stop_reason = END_OUTCOMES[reason]
    await record_decision_once(decision)


async def file_article(
    *, user_id: UUID, run_id: str, started_at: datetime, translated: bool
) -> None:
    """File one translation the listener's opening asked the model for. Never raises.

    Args:
        user_id: The listener who opened the article.
        run_id: The translation's own run, its euros already filed under.
        started_at: When the call began.
        translated: Whether a usable translation came back.
    """
    decision = out_of_turn_decision(
        run_id=run_id, user_id=user_id, thread_id=run_id, source=EffectSource.USER.value
    )
    decision.route = ARTICLE_ROUTE
    decision.started_at = started_at
    decision.outcome = DecisionOutcome.ANSWERED if translated else DecisionOutcome.FAILED
    await record_decision_once(decision)


__all__ = ["ARTICLE_ROUTE", "END_OUTCOMES", "SESSION_ROUTE", "file_article", "file_session"]
