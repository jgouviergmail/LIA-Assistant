"""Reading the five registers for a technical extraction (ADR-263, ADR-273).

Extracted from ``admin_router`` when the account holder gained the unified
Article-12 extraction: the reads are the same reads, and the only difference
between the two surfaces is the SCOPE they pass — an operator names accounts,
a reader has exactly one and no way to express another.

Keeping this in the admin router would have forced the reader's router to
import it, which is the wrong direction and the kind of dependency that turns
into an accidental privilege path. Keeping two copies would have been worse: a
sixth register, or a filter that stops being honoured, would have to be
remembered twice.

Since ADR-273 an extraction is not capped, so each register answers TWO
questions rather than one: how many rows the filters match, and the rows
themselves, streamed. Both come out of the same branch of the same dispatch —
a count published in a header while a different query fills the body is how a
file comes to disagree with its own first line.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.export_stream import count_all


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


#: How one register is read: the filtered statement, and the streamer that
#: walks it. They travel together because they must describe the same set.
_Streamer = Callable[[AsyncSession, Select[Any], int], AsyncIterator[Any]]


@dataclass(frozen=True)
class RegisterRead:
    """One register's two halves of an extraction.

    Attributes:
        query: The filtered SELECT, without order or ceiling.
        stream: Walks that statement at constant memory.
    """

    query: Select[Any]
    stream: _Streamer


#: Every filter a register MIGHT be asked for beyond the period and the account
#: list. Which of them a given register actually honours is declared on its
#: ``TechnicalSpec``; a request naming one it cannot is REPORTED in the header
#: rather than silently dropped, or a reader mistakes an unfiltered file for a
#: filtered one.
_OPTIONAL_FILTERS: tuple[str, ...] = (
    "tool_name",
    "mutation_policy",
    "status",
    "source",
    "execution_mode",
)


def stated_query(asked: TechnicalQuery) -> dict[str, Any]:
    """What the file SAYS was asked of it.

    It lives beside :class:`TechnicalQuery` rather than in the administrator's
    router because both surfaces now state their own period: since ADR-273 an
    extraction with no upper bound is given one — the instant it was generated
    — so that the exact count in its header and the rows in its body describe
    the same closed window. A file that pinned a window without naming it would
    be reproducible and unexplained.

    Args:
        asked: What was asked for.

    Returns:
        The header's ``filters`` mapping, with the filters this register cannot
        honour listed under ``ignored_filters`` rather than dropped. Account
        ids are pseudonymised downstream by ``export_header``, with the same
        key as the rows.
    """
    from src.domains.agents.effects.technical_export import TECHNICAL_SPECS

    honoured = TECHNICAL_SPECS[asked.register].filters
    values = {
        "tool_name": asked.tool_name,
        "mutation_policy": asked.mutation_policy,
        "status": getattr(asked.status, "value", asked.status),
        "source": getattr(asked.source, "value", asked.source),
        "execution_mode": asked.execution_mode,
    }
    stated: dict[str, Any] = {
        "register": asked.register,
        "since": asked.since.isoformat() if asked.since else None,
        "until": asked.until.isoformat() if asked.until else None,
        "user_ids": [str(one) for one in asked.user_ids] if asked.user_ids else None,
    }
    stated.update({name: values[name] if name in honoured else None for name in _OPTIONAL_FILTERS})
    stated["ignored_filters"] = sorted(
        name for name in _OPTIONAL_FILTERS if values[name] and name not in honoured
    )
    return stated


def register_read(asked: TechnicalQuery) -> RegisterRead:
    """The statement and the streamer for one register.

    Args:
        asked: What was asked for, scope included.

    Returns:
        Both halves, from one branch — so the exact count a header publishes
        and the rows the body carries cannot come from two different queries.
    """
    if asked.register == "actions":
        from src.domains.agents.effects.repository import EffectLedgerRepository

        return RegisterRead(
            query=EffectLedgerRepository.export_query(
                since=asked.since,
                until=asked.until,
                user_ids=asked.user_ids,
                tool_name=asked.tool_name,
                mutation_policy=asked.mutation_policy,
                status=asked.status,
                source=asked.source,
                execution_mode=asked.execution_mode,
            ),
            stream=lambda db, query, batch: EffectLedgerRepository(db).stream_for_export(
                query, batch=batch
            ),
        )

    if asked.register == "integrity":
        from src.domains.agents.effects.integrity_repository import IntegrityRepository

        return RegisterRead(
            query=IntegrityRepository.export_query(
                since=asked.since, until=asked.until, user_ids=asked.user_ids
            ),
            stream=lambda db, query, batch: IntegrityRepository(db).stream_for_export(
                query, batch=batch
            ),
        )

    if asked.register == "inference":
        from src.domains.chat.repository import ChatRepository

        return RegisterRead(
            query=ChatRepository.inference_export_query(
                since=asked.since, until=asked.until, user_ids=asked.user_ids
            ),
            stream=lambda db, query, batch: ChatRepository(db).stream_inference_for_export(
                query, batch=batch
            ),
        )

    if asked.register == "decisions":
        from src.domains.agents.effects.decision_repository import DecisionRepository

        return RegisterRead(
            query=DecisionRepository.export_query(
                since=asked.since, until=asked.until, user_ids=asked.user_ids
            ),
            stream=lambda db, query, batch: DecisionRepository(db).stream_for_export(
                query, batch=batch
            ),
        )

    from src.domains.agents.effects.treatment_repository import TreatmentRepository

    return RegisterRead(
        query=TreatmentRepository.export_query(
            since=asked.since,
            until=asked.until,
            user_ids=asked.user_ids,
            tool_name=asked.tool_name,
        ),
        stream=lambda db, query, batch: TreatmentRepository(db).stream_for_export(
            query, batch=batch
        ),
    )


def stream_register(db: AsyncSession, asked: TechnicalQuery, *, batch: int) -> AsyncIterator[Any]:
    """Every row of one register the filters match, oldest first.

    Args:
        db: A session dedicated to the read — the cursor empties the identity
            map between partitions (``export_stream``).
        asked: What was asked for, scope included.
        batch: How many rows the cursor buffers at a time.

    Returns:
        The rows, oldest first. All of them: an extraction of a register is
        complete, or it is not an extraction (ADR-273).
    """
    read = register_read(asked)
    return read.stream(db, read.query, batch)


async def count_register(db: AsyncSession, asked: TechnicalQuery) -> int:
    """How many rows one register's filters match.

    Args:
        db: Session.
        asked: What was asked for, scope included.

    Returns:
        The exact total, counted over the same statement the stream walks.
    """
    return await count_all(db, register_read(asked).query)


__all__ = [
    "RegisterRead",
    "TechnicalQuery",
    "count_register",
    "register_read",
    "stated_query",
    "stream_register",
]
