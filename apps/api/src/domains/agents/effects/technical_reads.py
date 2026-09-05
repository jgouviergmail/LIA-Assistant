"""Reading the five registers for a technical extraction (ADR-263).

Extracted from ``admin_router`` when the account holder gained the unified
Article-12 extraction: the reads are the same reads, and the only difference
between the two surfaces is the SCOPE they pass — an operator names accounts,
a reader has exactly one and no way to express another.

Keeping this in the admin router would have forced the reader's router to
import it, which is the wrong direction and the kind of dependency that turns
into an accidental privilege path. Keeping two copies would have been worse: a
sixth register, or a filter that stops being honoured, would have to be
remembered twice.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class TechnicalQuery:
    """What a technical extraction was asked for.

    A value object rather than nine parameters threaded twice: reading the rows
    and STATING what was asked are two jobs, and they must agree.

    Attributes:
        register: Which of the five records.
        since: Inclusive lower bound.
        until: Exclusive upper bound.
        user_ids: The accounts covered. ``None`` means every account and is
            reachable only from the administrator's surface — the reader's
            route passes their own id and offers no parameter to change it.
        tool_name: Filter honoured by the two tool-keyed registers.
        mutation_policy: Filter honoured by the actions register.
        status: Filter honoured by the actions register.
        source: Filter honoured by the actions register.
        execution_mode: Filter honoured by the actions register.
    """

    register: str
    since: datetime | None = None
    until: datetime | None = None
    user_ids: list[uuid.UUID] | None = None
    tool_name: str | None = None
    mutation_policy: str | None = None
    status: Any = None
    source: Any = None
    execution_mode: str | None = None


async def read_register(db: AsyncSession, asked: TechnicalQuery, cap: int) -> list[Any]:
    """Read one register's rows for a technical extraction.

    Args:
        db: Session.
        asked: What was asked for, scope included.
        cap: Row ceiling, published in the header by the caller.

    Returns:
        The matching rows, oldest first — each repository reads its newest
        window and reverses it, so a capped extraction keeps the recent end
        while still reading chronologically (``export_window``).
    """
    if asked.register == "actions":
        from src.domains.agents.effects.repository import EffectLedgerRepository

        return list(
            await EffectLedgerRepository(db).list_for_export(
                since=asked.since,
                until=asked.until,
                user_ids=asked.user_ids,
                tool_name=asked.tool_name,
                mutation_policy=asked.mutation_policy,
                status=asked.status,
                source=asked.source,
                execution_mode=asked.execution_mode,
                limit=cap,
            )
        )

    if asked.register == "integrity":
        from src.domains.agents.effects.integrity_repository import IntegrityRepository

        return list(
            await IntegrityRepository(db).list_for_export(
                since=asked.since, until=asked.until, user_ids=asked.user_ids, limit=cap
            )
        )

    if asked.register == "inference":
        from src.domains.chat.repository import ChatRepository

        return list(
            await ChatRepository(db).list_inference_for_export(
                since=asked.since, until=asked.until, user_ids=asked.user_ids, limit=cap
            )
        )

    if asked.register == "decisions":
        from src.domains.agents.effects.decision_repository import DecisionRepository

        return list(
            await DecisionRepository(db).list_for_export(
                since=asked.since, until=asked.until, user_ids=asked.user_ids, limit=cap
            )
        )

    from src.domains.agents.effects.treatment_repository import TreatmentRepository

    return list(
        await TreatmentRepository(db).list_for_export(
            since=asked.since,
            until=asked.until,
            user_ids=asked.user_ids,
            tool_name=asked.tool_name,
            limit=cap,
        )
    )


__all__ = ["TechnicalQuery", "read_register"]
