"""The API key's « last used » stamp, written in a transaction of its own (ADR-304).

``get_api_key_credentials`` used to reassign the connector's metadata and FLUSH
it on its CALLER's session. That is an UPDATE, so the connector row stayed
locked for as long as the caller's transaction lived — a whole chat turn, a
whole telephony dial — and any other writer of that row waited behind a read
(measured in production on 2026-09-22). It was also a read-modify-write of the
WHOLE metadata dict: a concurrent writer of another key (the telephony agent's
config fingerprint, its live-tools flag) could be silently overwritten by a
stamp computed from the dict it had loaded before.

The stamp is now ONE atomic statement — the key merged into the stored JSONB by
PostgreSQL, never recomputed in Python — in a short session of its own, under a
bounded lock wait. A read of credentials leaves nothing in its caller's
transaction, and « last used » is informational: a stamp that cannot take the
row in time is skipped, never waited for.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import func, text, update
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from src.core.constants import CONNECTOR_USE_STAMP_LOCK_TIMEOUT_MS
from src.domains.connectors.models import Connector
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)


async def stamp_api_key_use(connector_id: UUID) -> None:
    """Record that a connector's API key was just read. Never raises.

    Args:
        connector_id: The connector whose key was read.
    """
    stamped_at = datetime.now(UTC).isoformat()
    try:
        async with get_db_context() as db:
            try:
                # A literal, not a bind: SET does not take parameters. The value
                # is an integer constant, so nothing reaches it from outside.
                await db.execute(
                    text(f"SET LOCAL lock_timeout = {CONNECTOR_USE_STAMP_LOCK_TIMEOUT_MS}")
                )
                await db.execute(
                    update(Connector)
                    .where(Connector.id == connector_id, Connector.connector_metadata.is_not(None))
                    .values(
                        connector_metadata=Connector.connector_metadata.op("||")(
                            func.jsonb_build_object("last_used_at", stamped_at)
                        )
                    )
                )
            except DBAPIError as exc:
                # The row stayed busy past the bound, or the statement failed:
                # skipped by contract. The failed transaction ends HERE, so the
                # session helper does not report a database incident for an
                # informational stamp.
                await db.rollback()
                logger.debug(
                    "api_key_use_stamp_skipped",
                    connector_id=str(connector_id),
                    error_type=type(exc).__name__,
                )
    except SQLAlchemyError as exc:
        # The session itself could not be had or closed: same contract.
        logger.debug(
            "api_key_use_stamp_skipped",
            connector_id=str(connector_id),
            error_type=type(exc).__name__,
        )
