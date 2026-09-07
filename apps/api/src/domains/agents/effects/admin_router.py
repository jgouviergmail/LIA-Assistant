"""Administrator surfaces over the effect register (ADR-263).

Two questions, two answers, and the difference between them is the whole point.

- *Is the execution chain behaving?* — the **technical** export: pseudonymised
  by construction, no content of any kind, meant to be handed to a tool or a
  model. Nothing here needs to name anybody, so nothing here does.
- *What happened on this account?* — the **readable** view: it names people,
  so it is MASKED by default and every unmasking is written to
  ``AdminAuditLog``. An administrator may need it; nobody needs it silently.

Read-only, like the user-facing router: correcting a row stays a reviewed
database operation.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.dependencies import get_db
from src.core.security.authorization import require_superuser
from src.core.session_dependencies import get_current_active_session
from src.core.streaming_download import attachment_stream
from src.domains.agents.effects.article12_export import article12_filters, known_sources
from src.domains.agents.effects.models import EffectSource, EffectStatus
from src.domains.agents.effects.technical_reads import (
    TechnicalQuery,
    count_register,
    stated_query,
    stream_register,
)
from src.domains.users.models import AdminAuditLog, User
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin/effects", tags=["Admin", "Effects"])

#: What a masked readable row shows instead of the wording.
MASKED_LABEL = "•••"


class AdminEffectRow(BaseModel):
    """One row of the readable admin view — masked unless asked otherwise."""

    id: str = Field(..., description="Ledger row id")
    user_id: str = Field(..., description="Account the effect belongs to")
    tool_name: str = Field(..., description="Capability that acted")
    mutation_policy: str = Field(..., description="Declared policy")
    status: str = Field(..., description="Outcome")
    source: str = Field(..., description="Authority source")
    claimed_at: datetime = Field(..., description="When it was claimed")
    label: str = Field(..., description="The wording, or the mask")
    masked: bool = Field(..., description="Whether the wording was withheld")


def _given(value: Any) -> Any:
    """The value the caller actually supplied, or None.

    FastAPI substitutes real values at request time, but its declared defaults
    are ``Query`` OBJECTS — and those are truthy. A handler that reads them
    with a truthiness test behaves one way through the framework and another
    when called directly (a test, a script), which is exactly how a masking
    default or an optional filter turns into a surprise.

    Args:
        value: A parameter value, possibly the un-substituted placeholder.

    Returns:
        The value, or None when nothing was supplied.
    """
    from fastapi.params import Param

    return None if isinstance(value, Param) else value


def _enum_value(value: Any) -> str:
    """The stored spelling of an enum column, or the string itself."""
    return str(getattr(value, "value", value))


@router.get(
    "/export",
    response_class=StreamingResponse,
    summary="Pseudonymised technical export (JSON Lines)",
)
async def export_technical(
    register: Literal["actions", "consultations", "decisions", "inference", "integrity"] = Query(
        "actions",
        description="Which record — they count different things and never add up: one "
        "row per ACTION, one per CONSULTATION, one per TURN, one per LLM CALL, one per "
        "GAP in the record itself",
    ),
    since: datetime | None = Query(None, description="Lower bound on claimed_at"),
    until: datetime | None = Query(None, description="Upper bound on claimed_at"),
    user_ids: list[UUID] | None = Query(
        None, description="One, several, or (omitted) every account"
    ),
    tool_name: str | None = Query(None),
    mutation_policy: str | None = Query(None),
    status: EffectStatus | None = Query(None),
    source: EffectSource | None = Query(None),
    execution_mode: str | None = Query(None),
    accept_encoding: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_session),
) -> Response:
    """Export the register for analysis, naming nobody.

    Args:
        register: ``actions`` (what the assistant did) or ``consultations``
            (what it looked at). Two registers, never one list with a filter:
            they count different things, and their column contracts differ.
        since: Lower bound on ``claimed_at``.
        until: Upper bound on ``claimed_at``.
        user_ids: The accounts to cover. Omitted means every account —
            deliberately, because an operator asking a question about the
            instance is asking about the instance; the header states how many
            rows that turned out to be.
        tool_name: One capability.
        mutation_policy: One declared policy.
        status: One outcome.
        source: One authority source.
        execution_mode: ``pipeline`` or ``react``.
        db: Session.
        current_user: Must be a superuser.

    Returns:
        A JSON Lines file whose first line states what was asked, what is
        excluded, and whether the answer was truncated.
    """
    require_superuser(current_user, "export the effect register")

    from src.domains.agents.effects.technical_export import TECHNICAL_SPECS

    which = _given(register) or "actions"
    spec = TECHNICAL_SPECS[which]
    generated_at = datetime.now(UTC)
    since, until = _given(since), _given(until)
    tool_name, mutation_policy = _given(tool_name), _given(mutation_policy)
    status, source, execution_mode = _given(status), _given(source), _given(execution_mode)
    scope = _given(user_ids)

    asked = TechnicalQuery(
        register=which,
        since=since,
        # Closed at the instant the file is generated, so the exact count in
        # its header and the rows in its body describe the same set.
        until=until or generated_at,
        user_ids=scope,
        tool_name=tool_name,
        mutation_policy=mutation_policy,
        status=status,
        source=source,
        execution_mode=execution_mode,
    )
    total = await count_register(db, asked)
    logger.info("effect_technical_export", register=which, row_count=total)
    return attachment_stream(
        _technical_document(
            asked,
            spec=spec,
            total=total,
            generated_at=generated_at,
            batch=settings.effect_export_batch_rows,
        ),
        filename=f"lia-{spec.slug}.jsonl",
        media_type="application/x-ndjson",
        accept_encoding=_given(accept_encoding),
        extra_headers={"X-Register-Rows": str(total), "X-Register-Truncated": "false"},
    )


@router.get(
    "/readable",
    response_model=list[AdminEffectRow],
    summary="Readable admin view — masked unless explicitly unmasked",
)
async def read_admin_view(
    request: Request,
    user_id: UUID | None = Query(None, description="Restrict to one account"),
    limit: int = Query(50, ge=1, le=200),
    unmask: bool = Query(False, description="Reveal the wording — audited"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_session),
) -> list[AdminEffectRow]:
    """The readable register across accounts, masked by default.

    Unmasking is a deliberate act and is recorded as one: an administrator may
    legitimately need to read what an action said, and nobody should be able to
    do so without leaving a trace.

    Args:
        request: For the audited client details.
        user_id: One account, when the question is about one account.
        limit: Rows to return.
        unmask: Reveal the wordings — writes an ``AdminAuditLog`` entry.
        db: Session.
        current_user: Must be a superuser.

    Returns:
        The rows, with wordings masked unless ``unmask`` was requested.
    """
    require_superuser(current_user, "read the effect register of other accounts")

    # `unmask is True`, never a truthiness test: FastAPI's default is a `Query`
    # object, which is TRUTHY. A masking default that only holds when the
    # framework is in the loop is not a default at all.
    revealed = unmask is True

    from src.core.i18n_effects import render_effect_label
    from src.domains.agents.effects.repository import EffectLedgerRepository

    # ONE reading of what was asked: the audit entry must describe the query
    # that actually ran, and the raw parameter is a truthy ``Query`` object
    # whenever the framework is not in the loop.
    scoped_to = _given(user_id)
    repository = EffectLedgerRepository(db)
    rows = await repository.list_latest(
        EffectLedgerRepository.export_query(user_id=scoped_to), limit=_given(limit) or 50
    )

    if revealed:
        db.add(
            AdminAuditLog(
                admin_user_id=str(current_user.id),
                action="effect_register_unmasked",
                resource_type="agent_effects",
                resource_id=scoped_to,
                details={"row_count": len(rows), "scoped_to_user": scoped_to is not None},
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
        )
        await db.commit()
        logger.warning(
            "effect_register_unmasked",
            admin_user_id=str(current_user.id),
            row_count=len(rows),
        )

    language = getattr(current_user, "language", None) or "en"
    return [
        AdminEffectRow(
            id=str(row.id),
            user_id=str(row.user_id),
            tool_name=row.tool_name,
            mutation_policy=_enum_value(row.mutation_policy),
            status=_enum_value(row.status),
            source=_enum_value(row.source),
            claimed_at=row.claimed_at,
            label=(
                render_effect_label(EffectLedgerRepository.decrypted_label(row), language)
                if revealed
                else MASKED_LABEL
            ),
            masked=not revealed,
        )
        for row in rows
    ]


#: Columns the readable renderer reads. Listed rather than copied wholesale so
#: a new column cannot silently join a masked export.
_ACTION_COLUMNS: tuple[str, ...] = (
    "id",
    "tool_name",
    "mutation_policy",
    "status",
    "source",
    "execution_mode",
    "approval_kind",
    "provider_ref",
    "error_code",
    "thread_id",
    "claimed_at",
    "closed_at",
)


def _audit_unmask(
    db: AsyncSession, request: Request, admin: User, *, scope: str, row_count: int
) -> None:
    """Record that a wording was revealed. Reading is a deliberate act.

    Args:
        db: Session — the row is committed by the caller.
        request: For the client details worth keeping.
        admin: Who read.
        scope: What they asked for, in one word.
        row_count: How much they read.
    """
    db.add(
        AdminAuditLog(
            admin_user_id=str(admin.id),
            action="effect_register_unmasked",
            resource_type="agent_effects",
            resource_id=None,
            details={"row_count": row_count, "scope": scope, "surface": "readable_export"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    logger.warning(
        "effect_register_unmasked",
        admin_user_id=str(admin.id),
        row_count=row_count,
        surface="readable_export",
    )


def _masked_action(row: Any) -> Any:
    """The same row with its wording withheld, and nothing else hidden.

    Masking must cost the operator the CONTENT of an action, never the fact
    that it happened, which capability performed it, under what authority or
    with what outcome — those are what an administrator opens the register for.

    Args:
        row: An ``AgentEffect`` row.

    Returns:
        A stand-in whose label renders as the generic wording.
    """
    from types import SimpleNamespace

    masked = SimpleNamespace(**{column: getattr(row, column) for column in _ACTION_COLUMNS})
    masked.label = {"i18n_key": "effects.labels.generic", "values": {"tool": row.tool_name}}
    return masked


async def _technical_document(
    asked: TechnicalQuery,
    *,
    spec: Any,
    total: int,
    generated_at: datetime,
    batch: int,
) -> AsyncIterator[str]:
    """Render one register as pseudonymised JSON Lines, as it is read.

    The session belongs to this generator: the cursor under it empties the
    identity map between partitions, which would detach whatever else a shared
    session held (``export_stream``).

    Args:
        asked: What was asked for, scope included.
        spec: The register's column contract.
        total: The exact row count, already published in the header.
        generated_at: When the file was produced.
        batch: How many rows the cursor buffers at a time.

    Yields:
        The document, chunk by chunk.
    """
    from src.domains.agents.effects.technical_export import (
        export_header,
        stream_jsonl,
        technical_row,
    )

    async with get_db_context() as db:

        async def shaped() -> AsyncIterator[dict[str, Any]]:
            """Each row through its register's column contract."""
            async for row in stream_register(db, asked, batch=batch):
                yield technical_row(row, spec)

        header = export_header(
            row_count=total,
            filters=stated_query(asked),
            generated_at=generated_at,
            spec=spec,
        )
        async for chunk in stream_jsonl(header, shaped()):
            yield chunk


async def _article12_document(
    since: datetime | None,
    until: datetime,
    scope: list[UUID] | None,
    *,
    totals: dict[str, int],
    generated_at: datetime,
    batch: int,
) -> AsyncIterator[str]:
    """Compose the five records into one file, reading them one after another.

    Args:
        since: Inclusive lower bound.
        until: Exclusive upper bound — closed, so the totals hold.
        scope: The accounts covered, or None for every account.
        totals: The exact count per source, already in the header.
        generated_at: When the file was produced.
        batch: How many rows each cursor buffers at a time.

    Yields:
        The extraction, chunk by chunk.
    """
    from src.domains.agents.effects.article12_export import SourceStream, stream_article12

    async with get_db_context() as db:
        sources = [
            SourceStream(
                spec=spec,
                total=totals[spec.slug],
                rows=stream_register(
                    db,
                    TechnicalQuery(register=spec.slug, since=since, until=until, user_ids=scope),
                    batch=batch,
                ),
            )
            for spec in known_sources()
        ]
        async for chunk in stream_article12(
            sources,
            filters=article12_filters(since=since, until=until, user_ids=scope),
            generated_at=generated_at,
        ):
            yield chunk


async def _readable_document(
    spec: Any,
    asked: TechnicalQuery,
    *,
    export_format: str,
    reveal: bool,
    mask: bool,
    reader: User,
    batch: int,
) -> AsyncIterator[str]:
    """Render one register as a readable document, row by row.

    Masking and revealing both happen HERE, one row at a time, because there is
    no longer a list to walk twice. The audit entry is written by the caller
    before the first byte leaves: an administrator asked to see the wordings,
    and that is true whether or not the download completes.

    Args:
        spec: The register's rendering spec.
        asked: What was asked for, scope included.
        export_format: ``markdown`` or ``csv``.
        reveal: Decrypt the wordings.
        mask: Withhold the wordings.
        reader: Whose language and clock the document is written in.
        batch: How many rows the cursor buffers at a time.

    Yields:
        The document, chunk by chunk.
    """
    from src.domains.agents.effects.export_readable import stream_csv, stream_markdown
    from src.domains.agents.effects.repository import EffectLedgerRepository

    language = getattr(reader, "language", None) or "en"
    timezone = getattr(reader, "timezone", None) or DEFAULT_USER_DISPLAY_TIMEZONE

    async with get_db_context() as db:

        async def shown() -> AsyncIterator[Any]:
            """Each row as this reader is allowed to see it."""
            async for row in stream_register(db, asked, batch=batch):
                if reveal:
                    row.label = EffectLedgerRepository.decrypted_label(row)
                    yield row
                elif mask:
                    yield _masked_action(row)
                else:
                    yield row

        renderer = stream_markdown if export_format == "markdown" else stream_csv
        async for chunk in renderer(spec, shown(), language, timezone):
            yield chunk


@router.get(
    "/export/article12",
    response_class=StreamingResponse,
    summary="One pseudonymised extraction over every record (JSON Lines)",
)
async def export_article12(
    since: datetime | None = Query(None, description="Inclusive lower bound"),
    until: datetime | None = Query(None, description="Exclusive upper bound"),
    user_ids: list[UUID] | None = Query(
        None, description="One, several, or (omitted) every account"
    ),
    accept_encoding: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_session),
) -> Response:
    """Everything LIA records about a period, in one machine-readable file.

    Five sources, one file, and a ``kind`` on every line — because they answer
    five different questions and must never be added up: one line per TURN, per
    EFFECT, per CONSULTATION, per LLM CALL, and per GAP in the record itself.

    Composed from the contracts each source already declares, so nothing here
    decides what may be shown. Identifiers are pseudonymised with one key across
    all five, which is what lets a reader correlate a turn with its effects
    without learning whose they are.

    The ceiling applies PER SOURCE and the header states, per source, whether it
    was reached: a file complete in four records of five is not a complete file
    (ADR-185).

    Args:
        since: Inclusive lower bound on the period.
        until: Exclusive upper bound.
        user_ids: The accounts to cover; omitted means every account.
        db: Session.
        current_user: Must be a superuser.

    Returns:
        The extraction, as an attachment.
    """
    # Its OWN ceiling, lower than the per-record one and measured: five sources
    # at 5 000 rows peak at 33,9 MB and take 939 ms to serialise, before the ORM
    # instances behind them — a poor bargain on the hardware this deploys to.
    require_superuser(current_user, "export every record of every account")

    generated_at = datetime.now(UTC)
    since, until = _given(since), _given(until)
    closed_until = until or generated_at
    scope = _given(user_ids)
    totals = {
        spec.slug: await count_register(
            db,
            TechnicalQuery(register=spec.slug, since=since, until=closed_until, user_ids=scope),
        )
        for spec in known_sources()
    }

    lines = sum(totals.values())
    logger.info(
        "article12_export_served",
        admin_id=str(current_user.id),
        sources=len(totals),
        lines=lines,
    )
    return attachment_stream(
        _article12_document(
            since,
            closed_until,
            scope,
            totals=totals,
            generated_at=generated_at,
            batch=settings.effect_export_batch_rows,
        ),
        filename=f"lia-article12-{generated_at.strftime('%Y%m%d')}.jsonl",
        media_type="application/x-ndjson",
        accept_encoding=_given(accept_encoding),
        extra_headers={"X-Register-Rows": str(lines), "X-Register-Truncated": "false"},
    )


@router.get(
    "/export/readable",
    summary="Readable register extraction across accounts — masked unless unmasked",
)
async def export_readable_admin(
    request: Request,
    register: Literal["actions", "consultations"] = Query("actions"),
    export_format: Literal["markdown", "csv"] = Query("markdown", alias="format"),
    user_ids: list[UUID] | None = Query(
        None, description="One, several, or (omitted) every account"
    ),
    since: datetime | None = Query(None, description="Inclusive lower bound"),
    until: datetime | None = Query(None, description="Exclusive upper bound"),
    unmask: bool = Query(False, description="Reveal the wordings — audited"),
    accept_encoding: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_session),
) -> Response:
    """A human-readable register for one account, several, or all of them.

    The same engine the user's own export uses, so the two documents cannot
    disagree about what a register says.

    Masking applies to the ACTION register, whose wording names people. The
    consultation register has nothing to mask — it records the capability and
    never the call — and masking it would be theatre that costs an operator
    information for no privacy gained.

    Args:
        request: For the audited client details.
        register: ``actions`` or ``consultations`` — two lists, never merged.
        export_format: ``markdown`` to read, ``csv`` to count.
        user_ids: The accounts to cover; omitted means every account,
            deliberately — an operator asking about the instance is asking
            about the instance, and the row header says how much that was.
        since: Inclusive lower bound on the period.
        until: Exclusive upper bound.
        unmask: Reveal the action wordings — writes an ``AdminAuditLog`` entry.
        db: Session.
        current_user: Must be a superuser.

    Returns:
        The document, as an attachment.
    """
    require_superuser(current_user, "export the register of other accounts")

    from src.domains.agents.effects.export_readable import ACTIONS, TREATMENTS

    # `unmask is True`, never a truthiness test: FastAPI's declared default is
    # a `Query` OBJECT, and those are truthy — a masking default that only
    # holds when the framework is in the loop is not a default at all.
    revealed = unmask is True
    which = _given(register) or "actions"
    fmt = _given(export_format) or "markdown"
    scope = _given(user_ids)
    generated_at = datetime.now(UTC)
    asked = TechnicalQuery(
        register=which,
        since=_given(since),
        until=_given(until) or generated_at,
        user_ids=scope,
    )

    total = await count_register(db, asked)
    if which == "actions" and revealed:
        # Audited BEFORE a byte is sent, and on the request's own session: the
        # trace records that an administrator asked to see the wordings, which
        # is true whether or not the download completes.
        _audit_unmask(
            db,
            request,
            current_user,
            scope="all" if scope is None else f"{len(scope)} account(s)",
            row_count=total,
        )
        await db.commit()

    spec = ACTIONS if which == "actions" else TREATMENTS
    return attachment_stream(
        _readable_document(
            spec,
            asked,
            export_format=fmt,
            reveal=which == "actions" and revealed,
            mask=which == "actions" and not revealed,
            reader=current_user,
            batch=settings.effect_export_batch_rows,
        ),
        filename=(
            f"lia-admin-{spec.slug}-{generated_at.strftime('%Y%m%d')}."
            f"{'md' if fmt == 'markdown' else 'csv'}"
        ),
        media_type=(
            "text/markdown; charset=utf-8" if fmt == "markdown" else "text/csv; charset=utf-8"
        ),
        accept_encoding=_given(accept_encoding),
        extra_headers={
            "X-Register-Rows": str(total),
            "X-Register-Truncated": "false",
            "X-Register-Masked": "false" if (which == "actions" and revealed) else "true",
        },
    )
