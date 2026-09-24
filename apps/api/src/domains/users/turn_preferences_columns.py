"""How the person wants LIA to run a turn — the columns of ``users`` they live in.

A declarative mixin like ``LivePreferencesColumns`` and ``PhoneIdentityColumns``:
the execution mode (ADR-070, pipeline or ReAct, the chat header's toggle) and the
exchange rhythm (ADR-311, what the ReAct loop shapes its prompt for). Both are
read once per turn by the chat's stream service and carried by the run's typed
context; the exchange rhythm is written through the generic profile update.
Migrations ``add_execution_mode_preference`` and ``402dd18bbf2a``.
"""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column


class TurnPreferencesColumns:
    """Mapped columns of the turn preferences (a declarative mixin)."""

    # Execution mode preference (pipeline vs react)
    execution_mode: Mapped[str] = mapped_column(
        String(20),
        default="pipeline",
        nullable=False,
        server_default="pipeline",
        comment="Execution mode preference: 'pipeline' (classic planner) or 'react' (ReAct agent loop).",
    )

    # Exchange rhythm (ADR-311): what the ReAct loop shapes its prompt for. NULL means
    # never chosen — the account follows REACT_CROSS_TURN_CACHE_ENABLED, the operator's
    # default — so no deployment changes behaviour when the column appears.
    exchange_rhythm: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment=(
            "Exchange rhythm preference: 'frequent' (every tool bound, prompt shaped for the "
            "next turn's cache) or 'occasional' (relevance selection); NULL = instance default."
        ),
    )


__all__ = ["TurnPreferencesColumns"]
