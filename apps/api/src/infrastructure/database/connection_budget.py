"""Connection-budget invariant (audit F004).

The worst-case burst — every uvicorn worker holding its full SQLAlchemy pool +
overflow, plus the LangGraph checkpointer and store pools — must fit under
PostgreSQL's ``max_connections`` (minus a reserve for superuser + exporters), or
peak load exhausts the server and refuses connections. This module computes that
budget and validates it at startup.

Policy (audit F004): **fail-fast in production, warn in development**. The
shipped prod profile now fits (4 workers → burst 168 ≤ 195 usable, right-sized
in ``.env.prod.example``), so an overcommit in production means a genuinely
mis-sized deployment and the app must refuse to boot rather than exhaust the
server under peak load. In development an overcommit is only logged, so local
experiments with WEB_CONCURRENCY / pool sizes are not blocked. Enforcement is in
``enforce_connection_budget``; ``validate_connection_budget`` stays a pure
predicate used by both the enforcer and the tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.config import Settings


class ConnectionBudgetError(RuntimeError):
    """Raised at startup when the worst-case DB burst exceeds usable capacity.

    Only raised in production (``enforce_connection_budget``): a profile whose
    peak connection burst cannot fit under PostgreSQL ``max_connections`` would
    intermittently exhaust the server, so booting it is worse than failing loudly.
    """


@dataclass(frozen=True)
class ConnectionBudget:
    """Per-deployment PostgreSQL connection accounting."""

    workers: int
    max_connections: int
    reserved: int
    sqlalchemy_burst: int
    checkpoint_burst: int
    store_burst: int

    @property
    def usable(self) -> int:
        """Connections available to the app (max minus the reserve)."""
        return self.max_connections - self.reserved

    @property
    def burst_total(self) -> int:
        """Absolute worst case: every pool at its ceiling across all workers."""
        return self.sqlalchemy_burst + self.checkpoint_burst + self.store_burst

    @property
    def fits(self) -> bool:
        """True when the worst-case burst fits under the usable connections."""
        return self.burst_total <= self.usable


def compute_connection_budget(settings: Settings) -> ConnectionBudget:
    """Compute the connection budget from the effective settings."""
    workers = settings.web_concurrency
    return ConnectionBudget(
        workers=workers,
        max_connections=settings.database_max_connections,
        reserved=settings.database_reserved_connections,
        sqlalchemy_burst=workers * (settings.database_pool_size + settings.database_max_overflow),
        checkpoint_burst=workers * settings.langgraph_checkpoint_pool_max_size,
        store_burst=workers * settings.langgraph_store_pool_max_size,
    )


def validate_connection_budget(settings: Settings) -> list[str]:
    """Return warnings when the worst-case burst overcommits PostgreSQL.

    Pure predicate: an empty list means the budget fits. This is the single
    source of truth shared by ``enforce_connection_budget`` and the tests; it
    never raises, so it can be asserted on directly.
    """
    budget = compute_connection_budget(settings)
    if budget.fits:
        return []
    return [
        f"DB connection budget overcommit: worst-case burst {budget.burst_total} "
        f"(SQLAlchemy {budget.sqlalchemy_burst} + checkpointer {budget.checkpoint_burst} "
        f"+ store {budget.store_burst}) exceeds usable {budget.usable} "
        f"(max_connections {budget.max_connections} - reserved {budget.reserved}) for "
        f"{budget.workers} worker(s). Right-size database_pool_size / "
        f"database_max_overflow, lower WEB_CONCURRENCY, or raise database_max_connections."
    ]


def enforce_connection_budget(settings: Settings) -> list[str]:
    """Enforce the budget invariant: fail-fast in production, warn in development.

    Args:
        settings: The composed application settings.

    Returns:
        The (possibly empty) list of overcommit warnings for the caller to log.
        In **development** an overcommit is returned as a warning and boot
        continues; in **production** a non-empty overcommit raises instead, so an
        unsafe profile can never silently reach peak load.

    Raises:
        ConnectionBudgetError: In production when the worst-case burst exceeds the
            usable connections. The message is the actionable right-sizing hint.
    """
    warnings = validate_connection_budget(settings)
    if warnings and settings.is_production:
        raise ConnectionBudgetError(" ".join(warnings))
    return warnings
