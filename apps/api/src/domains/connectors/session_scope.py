"""Where a connector client does its own database work (ADR-304).

A connector client writes to the database for two reasons of its own: a
refreshed OAuth token, and a connector invalidated on an authentication
failure. Until ADR-304 it did both on its CALLER's session, entered as a
context manager — and ``AsyncSession.__aexit__`` CLOSES the session, which
expunges every object the caller had loaded. A caller that later changed one
of them committed nothing, in silence (proved on PostgreSQL:
``tests/integration/domains/connectors/test_client_session_ownership.py``).
The borrowing had a second cost: a client can only borrow a session its
caller keeps OPEN, so every caller held a transaction for as long as it used
the client, network calls included — the ``idle in transaction`` the Drive
push path pinned for 22 minutes (measured in production, 2026-09-22).

``connector_unit_of_work`` is the one seam a client writes through:

- handed the caller's ``ConnectorService``, it answers with that service and
  never closes its session — the session is the caller's;
- handed a ``ConnectorUnitOfWork``, it lets that object decide: a
  ``DetachedConnectorService`` (what a caller that holds no session passes)
  opens a session for the unit and commits and releases it at the end — and
  so does the chat's wrapper, whose units never run on the turn's session.

Only a session the unit of work OWNS may have its transaction ended early —
before the token endpoint, for instance. A caller's transaction is the
caller's: ending it would commit its pending writes even when the refresh then
fails (``owns_session``).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from src.domains.connectors.service import ConnectorService
from src.infrastructure.database.session import get_db_context


class ConnectorUnitOfWork(ABC):
    """A connector service that decides where a client's own writes run.

    Attributes:
        owns_units: True when every unit of work runs on a session of its own,
            so a client may end the unit's transaction before a network call.
    """

    owns_units: bool = False

    @abstractmethod
    def unit_of_work(self) -> AbstractAsyncContextManager[ConnectorService]:
        """The ``ConnectorService`` one unit of work runs on."""


class DetachedConnectorService(ConnectorUnitOfWork):
    """The connector service of a caller that holds no database session.

    Stateless: every unit of work opens its own session, so one instance may
    be handed to a client that lives across many network calls.
    """

    owns_units = True

    @asynccontextmanager
    async def unit_of_work(self) -> AsyncIterator[ConnectorService]:
        """A ``ConnectorService`` on a session of its own, committed at the end.

        Yields:
            The service; its session is committed and released when the block
            exits, rolled back when it raises.
        """
        async with get_db_context() as db:
            yield ConnectorService(db)


def owns_session(connector_service: object) -> bool:
    """Whether a client's unit of work runs on a session no caller shares.

    Args:
        connector_service: What the client was built with.

    Returns:
        True for a unit of work whose units run on sessions of their own.
    """
    return isinstance(connector_service, ConnectorUnitOfWork) and connector_service.owns_units


@asynccontextmanager
async def connector_unit_of_work(
    connector_service: ConnectorService | ConnectorUnitOfWork,
) -> AsyncIterator[ConnectorService]:
    """The service a client's own database write runs on.

    Args:
        connector_service: What the client was built with — the caller's
            ``ConnectorService``, or a ``ConnectorUnitOfWork``.

    Yields:
        The unit of work a ``ConnectorUnitOfWork`` opens; otherwise the
        caller's service itself, whose session is left open and attached — it
        belongs to the caller.
    """
    if isinstance(connector_service, ConnectorUnitOfWork):
        async with connector_service.unit_of_work() as service:
            yield service
        return
    yield connector_service
