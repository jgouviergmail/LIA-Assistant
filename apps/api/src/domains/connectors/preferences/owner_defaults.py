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

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog

from src.domains.connectors.preferences.resolver import (
    resolve_calendar_name,
    resolve_task_list_name,
)
from src.domains.connectors.preferences.service import ConnectorPreferencesService
from src.domains.connectors.repository import ConnectorRepository
from src.infrastructure.database.session import get_db_context

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


@dataclass(frozen=True, slots=True)
class OwnerContainer:
    """One kind of default container an owner configures (a calendar, a task list).

    Attributes:
        preference: The connector preference holding its NAME.
        fallback: The provider's own default when no name resolves.
        resolve: Resolves a name to an id on the provider (a network call).
        failure_event: What a degraded resolution logs.
    """

    preference: str
    fallback: str
    resolve: Callable[..., Awaitable[str]]
    failure_event: str


CALENDAR = OwnerContainer(
    CALENDAR_PREFERENCE,
    "primary",
    resolve_calendar_name,
    "owner_default_calendar_resolution_failed",
)
TASK_LIST = OwnerContainer(
    TASK_LIST_PREFERENCE,
    "@default",
    resolve_task_list_name,
    "owner_default_task_list_resolution_failed",
)


async def read_owner_container_name(
    db: AsyncSession, owner_id: UUID, connector_type: ConnectorType, container: OwnerContainer
) -> str | None:
    """The DATABASE half: the container name the owner configured, if readable.

    Split from the resolution so a caller reads it in a short session and
    closes that session before the network call that resolves it (ADR-304).

    Args:
        db: Session to read the connector on.
        owner_id: The user who OWNS the data being read.
        connector_type: Their active connector for the category.
        container: Which default (:data:`CALENDAR`, :data:`TASK_LIST`).

    Returns:
        The configured name; None when unset or unreadable (logged).
    """
    try:
        return await read_owner_preference_name(db, owner_id, connector_type, container.preference)
    except _PREFERENCE_ERRORS as exc:
        _log_fallback(container, owner_id, exc)
        return None


async def resolve_owner_container_id(
    *, client: Any, name: str | None, owner_id: UUID, container: OwnerContainer
) -> str:
    """The NETWORK half: the id of a configured name, or the provider's default.

    Args:
        client: The category's client (same list interface across providers).
        name: What :func:`read_owner_container_name` returned.
        owner_id: The user whose data is being read (for the log).
        container: Which default (:data:`CALENDAR`, :data:`TASK_LIST`).

    Returns:
        An id; the container's fallback when no name is configured or it
        cannot be resolved; other failures propagate (see
        :data:`_PREFERENCE_ERRORS`).
    """
    if not name:
        return container.fallback
    try:
        return await container.resolve(client=client, name=name, fallback=container.fallback)
    except _PREFERENCE_ERRORS as exc:
        _log_fallback(container, owner_id, exc)
        return container.fallback


def _log_fallback(container: OwnerContainer, owner_id: UUID, exc: Exception) -> None:
    logger.warning(
        container.failure_event,
        owner_id=str(owner_id),
        error=str(exc),
        error_type=type(exc).__name__,
    )


async def resolve_owner_calendar_id(
    *, client: Any, owner_id: UUID, connector_type: ConnectorType
) -> str:
    """Calendar id the OWNER configured as their default, or ``primary``.

    Args:
        client: Calendar client (Google or Apple — same list interface).
        owner_id: The user whose calendar is being read.
        connector_type: Their active calendar connector.

    Returns:
        A calendar id, degrading to ``primary`` when the preference is unset
        or unreadable; other failures propagate (see
        :data:`_PREFERENCE_ERRORS`).
    """
    return await _resolve_owner_default(CALENDAR, client, owner_id, connector_type)


async def resolve_owner_task_list_id(
    *, client: Any, owner_id: UUID, connector_type: ConnectorType
) -> str:
    """Task list id the OWNER configured as their default, or ``@default``.

    Args:
        client: Tasks client (Google Tasks or Microsoft To Do).
        owner_id: The user whose tasks are being read.
        connector_type: Their active tasks connector.

    Returns:
        A task list id, degrading to ``@default`` when the preference is
        unset or unreadable; other failures propagate (see
        :data:`_PREFERENCE_ERRORS`).
    """
    return await _resolve_owner_default(TASK_LIST, client, owner_id, connector_type)


async def _resolve_owner_default(
    container: OwnerContainer, client: Any, owner_id: UUID, connector_type: ConnectorType
) -> str:
    """Read the name in a short session of its own, then resolve it on the network.

    The callers are chat tools holding the turn's shared session: they used
    to pass it here, read on it outside the tools' lock, and leave its
    transaction open while the name was resolved on the provider (ADR-304).
    """
    async with get_db_context() as db:
        name = await read_owner_container_name(db, owner_id, connector_type, container)
    return await resolve_owner_container_id(
        client=client, name=name, owner_id=owner_id, container=container
    )
