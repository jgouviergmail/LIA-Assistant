"""Resolve a connector OWNER's configured default container (calendar, task list).

The same block — read the connector row, decrypt the preference, resolve the
name to an id, fall back on failure — was written out at TEN call sites:
``calendar_tools`` (4), ``briefing/fetchers`` (2), ``heartbeat``
(2), ``tasks_tools`` (1) and ``telephony/availability`` (1). Every one of them
resolves it for the user whose data is being read; the peers read path was the
only one that skipped it and hardcoded ``primary`` / ``@default`` — which is
how a single missing block became a wrong answer nobody could see.

Reported 2026-07-30: after the routing and the data plumbing were both fixed,
the assistant still answered that a peer had no timed slot tomorrow while he
had a 10:00 appointment — it was reading his ``primary`` calendar while his
agenda lives in a named one. Free-when-busy is the costliest shape of wrong
answer here, because the user acts on it.

``owner_id`` is an explicit argument, never "the current user": a peer read
runs under the ASKING user's runtime, so resolving the ambient identity would
read the wrong person's preference — and look perfectly correct in any
single-user test.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog

from src.domains.connectors.preferences.resolver import (
    resolve_calendar_name,
    resolve_task_list_name,
)
from src.domains.connectors.preferences.service import ConnectorPreferencesService
from src.domains.connectors.repository import ConnectorRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.domains.connectors.models import ConnectorType

logger = structlog.get_logger(__name__)

CALENDAR_PREFERENCE: str = "default_calendar_name"
TASK_LIST_PREFERENCE: str = "default_task_list_name"

# Deliberately NARROW, and identical to the eight call sites this helper
# replaces: these are the shapes a malformed or absent preference takes
# (missing key, undecryptable blob, unexpected payload type).
#
# A broader net would swallow a database or provider failure and quietly serve
# `primary` instead — i.e. answer from the WRONG calendar while looking
# successful. That is the exact defect this whole module exists to close
# (2026-07-30: a peer reported free at 10:00 because his agenda lives in a
# named calendar). Losing the operation loudly beats answering confidently
# from the wrong data, so anything outside this tuple propagates.
_PREFERENCE_ERRORS: tuple[type[Exception], ...] = (
    ValueError,
    KeyError,
    AttributeError,
    TypeError,
)


async def read_owner_preference_name(
    db: AsyncSession,
    owner_id: UUID,
    connector_type: ConnectorType,
    preference_name: str,
) -> str | None:
    """Read one decrypted preference value from the owner's connector row.

    Public because one call site legitimately needs the NAME without resolving
    it: ``calendar_tools`` search feeds the configured name back into its own
    later name→id resolution, so resolving here would do the work twice.

    Args:
        db: Session to read the connector on.
        owner_id: The user who OWNS the data being read.
        connector_type: Active connector for the functional category.
        preference_name: Preference field to read.

    Returns:
        The configured name, or None when unset or unreadable.
    """
    connector = await ConnectorRepository(db).get_by_user_and_type(owner_id, connector_type)
    if not connector or not connector.preferences_encrypted:
        return None
    return ConnectorPreferencesService.get_preference_value(
        connector_type.value,
        connector.preferences_encrypted,
        preference_name,
    )


async def resolve_owner_calendar_id(
    *,
    db: AsyncSession,
    client: Any,
    owner_id: UUID,
    connector_type: ConnectorType,
) -> str:
    """Calendar id the OWNER configured as their default, or ``primary``.

    Args:
        db: Session to read the connector on.
        client: Calendar client (Google or Apple — same list interface).
        owner_id: The user whose calendar is being read.
        connector_type: Their active calendar connector.

    Returns:
        A calendar id, degrading to ``primary`` when the preference is unset
        or unreadable; other failures propagate (see
        :data:`_PREFERENCE_ERRORS`).
    """
    try:
        name = await read_owner_preference_name(db, owner_id, connector_type, CALENDAR_PREFERENCE)
        if not name:
            return "primary"
        return await resolve_calendar_name(client=client, name=name, fallback="primary")
    except _PREFERENCE_ERRORS as exc:
        logger.warning(
            "owner_default_calendar_resolution_failed",
            owner_id=str(owner_id),
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return "primary"


async def resolve_owner_task_list_id(
    *,
    db: AsyncSession,
    client: Any,
    owner_id: UUID,
    connector_type: ConnectorType,
) -> str:
    """Task list id the OWNER configured as their default, or ``@default``.

    Args:
        db: Session to read the connector on.
        client: Tasks client (Google Tasks or Microsoft To Do).
        owner_id: The user whose tasks are being read.
        connector_type: Their active tasks connector.

    Returns:
        A task list id, degrading to ``@default`` when the preference is
        unset or unreadable; other failures propagate (see
        :data:`_PREFERENCE_ERRORS`).
    """
    try:
        name = await read_owner_preference_name(db, owner_id, connector_type, TASK_LIST_PREFERENCE)
        if not name:
            return "@default"
        return await resolve_task_list_name(client=client, name=name, fallback="@default")
    except _PREFERENCE_ERRORS as exc:
        logger.warning(
            "owner_default_task_list_resolution_failed",
            owner_id=str(owner_id),
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return "@default"
