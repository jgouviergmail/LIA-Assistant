"""The person's egress grants: what a card answer writes, what the tool reads.

A grant is a decision the person took on a HITL card — « this host, with or
without the turn's data » — remembered per account so the next run needs no
question. The cap (``PYTHON_SANDBOX_MAX_GRANTS_PER_USER``) bounds NEW rows
only: at the cap an approval still holds for the run it answers (``one_shot``)
and the card says so; changing one's mind on a host already granted is free.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Protocol
from uuid import UUID

import structlog

from src.core.config import get_settings
from src.domains.agents.python_sandbox.egress.hosts import HostStatus

logger = structlog.get_logger(__name__)

#: The card's three answers, as the resume path canonises them (ADR-298).
ANSWER_WITH_DATA = "confirm"
ANSWER_WITHOUT_DATA = "confirm_without_data"
ANSWER_REFUSE = "cancel"


class Decision(str, Enum):
    """What the person answered."""

    WITH_DATA = "with_data"
    WITHOUT_DATA = "without_data"
    REFUSED = "refused"


def decision_from_answer(action: str) -> Decision:
    """The decision behind a card action id.

    Raises:
        ValueError: On an action the card does not offer.
    """
    mapping = {
        ANSWER_WITH_DATA: Decision.WITH_DATA,
        ANSWER_WITHOUT_DATA: Decision.WITHOUT_DATA,
        ANSWER_REFUSE: Decision.REFUSED,
    }
    try:
        return mapping[action]
    except KeyError as exc:
        raise ValueError(f"not an egress answer: {action!r}") from exc


@dataclass(frozen=True)
class RecordOutcome:
    """What recording a decision produced.

    Attributes:
        allowed: Whether the hosts may be reached at all.
        share_turn_data: The scope the person chose (meaningless when refused).
        one_shot: True when the cap kept the decision from being remembered —
            it holds for this run only, and the card said so.
    """

    allowed: bool
    share_turn_data: bool
    one_shot: bool


class GrantStore(Protocol):
    """What the service needs of the repository."""

    async def count_for_user(self, user_id: UUID) -> int: ...

    async def scopes_for_user(self, user_id: UUID) -> dict[str, bool]: ...

    async def upsert(self, user_id: UUID, host: str, *, share_turn_data: bool) -> object: ...

    async def touch(self, user_id: UUID, hosts: Iterable[str], *, when: datetime) -> None: ...


class EgressGrantService:
    """Reads and writes of one account's grants, under the cap."""

    def __init__(self, *, repository: GrantStore) -> None:
        self._repository = repository

    async def scopes(self, user_id: UUID) -> Mapping[str, bool]:
        """``{host: share_turn_data}`` — what the classification reads."""
        return await self._repository.scopes_for_user(user_id)

    async def record(
        self, user_id: UUID, hosts: Iterable[str], decision: Decision
    ) -> RecordOutcome:
        """Write the person's decision for the hosts a card asked about.

        Args:
            user_id: The account.
            hosts: The unknown hosts the card named.
            decision: What the person answered.

        Returns:
            The outcome the replay reads.

        The room check and the writes are two statements: two answers of the
        SAME account landing in the same instant could overshoot the cap by
        one card's hosts. An answer is a person's click on one card at a time
        (ADR-288 shows one draft per interrupt), so the cap is a bound on
        growth, not a counter — and the unique index keeps a host from ever
        being stored twice.
        """
        if decision is Decision.REFUSED:
            return RecordOutcome(allowed=False, share_turn_data=False, one_shot=False)
        share = decision is Decision.WITH_DATA
        cap = get_settings().python_sandbox_max_grants_per_user
        known = await self._repository.scopes_for_user(user_id)
        names = list(hosts)
        new_names = [h for h in names if h not in known]
        room = cap - await self._repository.count_for_user(user_id)
        if new_names and len(new_names) > room:
            # Nothing is written: a partial memory would make the same question
            # come back for half the hosts, which reads as a bug.
            logger.info(
                "sandbox_egress_grant_one_shot", user_id=str(user_id), cap=cap, asked=len(new_names)
            )
            return RecordOutcome(allowed=True, share_turn_data=share, one_shot=True)
        for host in names:
            await self._repository.upsert(user_id, host, share_turn_data=share)
        return RecordOutcome(allowed=True, share_turn_data=share, one_shot=False)

    async def mark_used(self, user_id: UUID, hosts: Iterable[str], *, when: datetime) -> None:
        """Stamp the grants a run relied on."""
        await self._repository.touch(user_id, hosts, when=when)


async def load_grants(user_id: UUID) -> Mapping[str, bool]:
    """``{host: share_turn_data}`` for this account, on a session of its own.

    A session of its own rather than the tool container's: the classification
    may run beside other tools' database work (parallel sub-agent steps), and
    an ``AsyncSession`` is not safe for concurrent use.
    """
    from src.domains.agents.python_sandbox.egress.grants_repository import EgressGrantRepository
    from src.infrastructure.database.session import get_db_context

    async with get_db_context() as db:
        return await EgressGrantService(repository=EgressGrantRepository(db)).scopes(user_id)


async def record_decision(user_id: UUID, hosts: Iterable[str], decision: Decision) -> RecordOutcome:
    """Write the person's card answer, on a session of its own, committed."""
    from src.domains.agents.python_sandbox.egress.grants_repository import EgressGrantRepository
    from src.infrastructure.database.session import get_db_context

    async with get_db_context() as db:
        outcome = await EgressGrantService(repository=EgressGrantRepository(db)).record(
            user_id, hosts, decision
        )
        await db.commit()
    return outcome


async def mark_relied_grants(user_id: UUID, statuses: Mapping[str, HostStatus]) -> None:
    """Stamp the STORED grants among a run's hosts — the one reading of
    « which hosts did this run rely on », shared by the tool path and the
    draft executor. Nothing to stamp is a no-op, not a query."""
    relied_on = [host for host, status in statuses.items() if status is HostStatus.GRANT]
    if relied_on:
        await mark_grants_used(user_id, relied_on)


async def mark_grants_used(user_id: UUID, hosts: Iterable[str]) -> None:
    """Best effort: stamp the grants a run relied on, never failing the run."""
    from src.domains.agents.python_sandbox.egress.grants_repository import EgressGrantRepository
    from src.infrastructure.database.session import get_db_context

    try:
        async with get_db_context() as db:
            await EgressGrantService(repository=EgressGrantRepository(db)).mark_used(
                user_id, hosts, when=datetime.now(UTC)
            )
            await db.commit()
    except Exception as exc:  # noqa: BLE001 - a stamp must never cost the run
        logger.debug("sandbox_egress_grant_touch_failed", error_type=type(exc).__name__)


__all__ = [
    "ANSWER_REFUSE",
    "ANSWER_WITHOUT_DATA",
    "ANSWER_WITH_DATA",
    "Decision",
    "EgressGrantService",
    "GrantStore",
    "RecordOutcome",
    "decision_from_answer",
    "load_grants",
    "mark_grants_used",
    "mark_relied_grants",
    "record_decision",
]
