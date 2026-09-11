"""Which heartbeat sources this account can actually be served from.

The settings panel labels a source « Non connecté » when the backend does not
list it as available. The probe used to know eight sources (the connector-
backed ones plus interests, memories, journals and health), so the five
added later — birthdays, departure, open loops, habits, workboard — were
« not connected » on every account, whatever the account held: measured
2026-09-11 on an account with an active learned rhythm (ADR-197 published the
switches, nothing published their availability).

One probe per source, in a registry checked against ``HEARTBEAT_SOURCE_KEYS``
in BOTH directions at boot and in a unit test (ADR-085): a source added to
the policy without a probe refuses to start, and so does a probe for a source
that does not exist. A probe answers « could this source open for this
person right now » — a connector, a flag, a record — never « did it produce
something today ».
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.connectors.models import CONNECTOR_FUNCTIONAL_CATEGORIES, ConnectorType
from src.domains.connectors.repository import ConnectorRepository
from src.domains.heartbeat.source_policy import HEARTBEAT_SOURCE_KEYS, HEARTBEAT_SOURCE_ORDER

if TYPE_CHECKING:
    from src.domains.users.models import User

#: ``(user, db, connectors) -> available``.
Probe = Callable[["User", AsyncSession, ConnectorRepository], Awaitable[bool]]


async def _active_connector(repo: ConnectorRepository, user_id: UUID, category: str) -> bool:
    """Any ACTIVE connector of a functional category (calendar, email, …)."""
    for connector_type in CONNECTOR_FUNCTIONAL_CATEGORIES.get(category, frozenset()):
        connector = await repo.get_by_user_and_type(user_id, connector_type)
        if connector and connector.status.value == "active":
            return True
    return False


async def _calendar(user: User, db: AsyncSession, repo: ConnectorRepository) -> bool:
    return await _active_connector(repo, user.id, "calendar")


async def _tasks(user: User, db: AsyncSession, repo: ConnectorRepository) -> bool:
    return await _active_connector(repo, user.id, "tasks")


async def _emails(user: User, db: AsyncSession, repo: ConnectorRepository) -> bool:
    return await _active_connector(repo, user.id, "email")


async def _weather(user: User, db: AsyncSession, repo: ConnectorRepository) -> bool:
    connector = await repo.get_by_user_and_type(user.id, ConnectorType.OPENWEATHERMAP)
    return bool(connector and connector.status.value == "active" and user.home_location_encrypted)


async def _interests(user: User, db: AsyncSession, repo: ConnectorRepository) -> bool:
    if not user.interests_enabled:
        return False
    from src.domains.interests.repository import InterestRepository

    return bool(await InterestRepository(db).get_active_for_user(user.id))


async def _memories(user: User, db: AsyncSession, repo: ConnectorRepository) -> bool:
    return bool(user.memory_enabled)


async def _journals(user: User, db: AsyncSession, repo: ConnectorRepository) -> bool:
    return bool(getattr(user, "journals_enabled", settings.journals_enabled))


async def _health_signals(user: User, db: AsyncSession, repo: ConnectorRepository) -> bool:
    return bool(
        getattr(settings, "health_metrics_enabled", False)
        and getattr(user, "health_metrics_agents_enabled", False)
    )


async def _birthdays(user: User, db: AsyncSession, repo: ConnectorRepository) -> bool:
    connector = await repo.get_by_user_and_type(user.id, ConnectorType.GOOGLE_CONTACTS)
    return bool(connector and connector.status.value == "active")


async def _departure(user: User, db: AsyncSession, repo: ConnectorRepository) -> bool:
    # The fetcher opens with the flag, then needs calendar events and a
    # Routes key — the declared dependency on ``calendar`` is checked here
    # too, so the panel never shows a live switch that yields nothing.
    if not getattr(settings, "heartbeat_departure_enabled", False):
        return False
    if not getattr(settings, "google_api_key", ""):
        return False
    return await _calendar(user, db, repo)


async def _open_loops(user: User, db: AsyncSession, repo: ConnectorRepository) -> bool:
    return bool(getattr(settings, "open_loops_enabled", False))


async def _has_habit_profile(db: AsyncSession, user_id: UUID) -> bool:
    from src.domains.habits.models import UserHabitProfile

    return (
        await db.scalar(select(UserHabitProfile.id).where(UserHabitProfile.user_id == user_id))
    ) is not None


async def _habits(user: User, db: AsyncSession, repo: ConnectorRepository) -> bool:
    # The deployment switch, the person's own switch, and something learned
    # to read: the fetcher returns None until a profile exists.
    if not getattr(settings, "habits_enabled", False) or not getattr(user, "habits_enabled", True):
        return False
    return await _has_habit_profile(db, user.id)


async def _workboard(user: User, db: AsyncSession, repo: ConnectorRepository) -> bool:
    return bool(getattr(settings, "workboard_enabled", False))


#: Every source the policy publishes, and how to tell whether it can open.
SOURCE_AVAILABILITY_PROBES: dict[str, Probe] = {
    "calendar": _calendar,
    "tasks": _tasks,
    "emails": _emails,
    "weather": _weather,
    "interests": _interests,
    "memories": _memories,
    "journals": _journals,
    "health_signals": _health_signals,
    "birthdays": _birthdays,
    "departure": _departure,
    "open_loops": _open_loops,
    "habits": _habits,
    "workboard": _workboard,
}


def assert_availability_probes_complete() -> None:
    """Fail loudly when a published source has no probe, or a probe no source.

    Raises:
        RuntimeError: On any divergence with ``HEARTBEAT_SOURCE_KEYS``.
    """
    probed = frozenset(SOURCE_AVAILABILITY_PROBES)
    missing = HEARTBEAT_SOURCE_KEYS - probed
    extra = probed - HEARTBEAT_SOURCE_KEYS
    if missing or extra:
        raise RuntimeError(
            "heartbeat source availability probes drifted from the source policy: "
            f"missing={sorted(missing)} extra={sorted(extra)}"
        )


async def compute_available_sources(user: User, db: AsyncSession) -> list[str]:
    """The sources this account can be served from, in the published order.

    Args:
        user: The account row.
        db: Request session.

    Returns:
        Source keys, ordered like ``HEARTBEAT_SOURCE_ORDER``.
    """
    repo = ConnectorRepository(db)
    available: list[str] = []
    for name in HEARTBEAT_SOURCE_ORDER:
        if await SOURCE_AVAILABILITY_PROBES[name](user, db, repo):
            available.append(name)
    return available


assert_availability_probes_complete()
