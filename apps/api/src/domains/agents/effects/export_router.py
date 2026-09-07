"""Downloading a register: to read, to count, or to analyse (ADR-263, ADR-273).

One endpoint for two registers and three formats, because the combinations are
the same operation with a different renderer — and because a second endpoint
would be a second place for the period, the timezone and the completeness to be
spelled slightly differently.

The third format, JSON Lines, is the SAME contract the administrator's export
obeys: an allowlist of columns, no content, identifiers pseudonymised. Reusing
it rather than inventing a user variant is deliberate. It makes the file safe
to HAND ON — the readable export already carries the reader's own wording;
what this one adds is a record of the same events that reveals nothing when
attached to a bug report, a complaint or a portability request — and it takes
no new privacy decision, where a second contract for the same rows would be a
second place for a column to slip from « forbidden » to « exported ».

The document is rendered in the READER's language and the READER's display
timezone, both taken from their own account rather than from a query string: an
export is evidence, and evidence a caller can restyle is weaker evidence.

**Nothing is truncated** (ADR-273). The rows are streamed under a header that
states the exact total, and the period is closed at the instant the file is
generated so the two describe the same set. The download is compressed on the
way out when the client offers to decompress, which is what makes a complete
register practical over a domestic uplink.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, Literal

import structlog
from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE, RATE_LIMIT_EFFECTS_READ_PER_MINUTE
from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.core.streaming_download import attachment_stream
from src.domains.agents.effects.article12_export import (
    SourceStream,
    article12_filters,
    known_sources,
    stream_article12,
)
from src.domains.agents.effects.export_readable import (
    ACTIONS,
    TREATMENTS,
    RegisterSpec,
    stream_csv,
    stream_markdown,
)
from src.domains.agents.effects.technical_export import (
    TECHNICAL_SPECS,
    TechnicalSpec,
    export_header,
    stream_jsonl,
    technical_row,
)
from src.domains.agents.effects.technical_reads import (
    TechnicalQuery,
    count_register,
    stated_query,
    stream_register,
)
from src.domains.auth.dependencies import create_user_rate_limiter
from src.domains.users.models import User
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/effects/export", tags=["Effects"])

rate_limit_export = create_user_rate_limiter(
    action="effects_export",
    max_calls=RATE_LIMIT_EFFECTS_READ_PER_MINUTE,
)

#: Which register, by the name it carries in its own download.
REGISTERS: dict[str, RegisterSpec] = {ACTIONS.slug: ACTIONS, TREATMENTS.slug: TREATMENTS}

#: Format → (media type, extension). A table rather than a branch: a fourth
#: format is an entry, not an edit. The renderer is chosen beside it, in
#: :func:`_document`, because the three no longer share one signature — a
#: machine-readable file has no reader to localise for.
FORMATS: dict[str, tuple[str, str]] = {
    "markdown": ("text/markdown; charset=utf-8", "md"),
    "csv": ("text/csv; charset=utf-8", "csv"),
    "technical": ("application/x-ndjson", "jsonl"),
}


def _display_timezone(user: User) -> str:
    """The reader's own clock, or the instance default.

    Args:
        user: The authenticated caller.

    Returns:
        An IANA name. Never a hardcoded literal at the call site — the default
        lives in ``core.constants`` and nowhere else.
    """
    return getattr(user, "timezone", None) or DEFAULT_USER_DISPLAY_TIMEZONE


async def _shaped(
    rows: AsyncIterator[Any], contract: TechnicalSpec
) -> AsyncIterator[dict[str, Any]]:
    """Put each row through its register's column contract, one at a time.

    Args:
        rows: The register's rows.
        contract: What the file may show, and what it must never show.

    Yields:
        The pseudonymised, allowlisted mapping for one row.
    """
    async for row in rows:
        yield technical_row(row, contract)


async def _document(
    spec: RegisterSpec,
    asked: TechnicalQuery,
    *,
    export_format: str,
    total: int,
    language: str,
    timezone: str,
    generated_at: datetime,
    batch: int,
) -> AsyncIterator[str]:
    """Render the whole register, reading it as it is written out.

    The session is opened HERE and belongs to this generator: the cursor
    underneath empties the identity map between partitions, which would detach
    whatever else a shared session held (``export_stream``).

    Args:
        spec: Which register, in its readable declaration.
        asked: What was asked for — the caller's own account, and a closed
            period.
        export_format: ``markdown``, ``csv`` or ``technical``.
        total: The exact row count, already published in the header.
        language: The reader's language.
        timezone: The reader's display timezone.
        generated_at: When the file was produced.
        batch: How many rows the cursor buffers at a time.

    Yields:
        The document, chunk by chunk.
    """
    async with get_db_context() as db:
        rows = stream_register(db, asked, batch=batch)
        if export_format == "technical":
            contract = TECHNICAL_SPECS[spec.slug]
            header = export_header(
                row_count=total,
                filters=stated_query(asked),
                generated_at=generated_at,
                spec=contract,
            )
            async for chunk in stream_jsonl(header, _shaped(rows, contract)):
                yield chunk
            return
        renderer = stream_markdown if export_format == "markdown" else stream_csv
        async for chunk in renderer(spec, rows, language, timezone):
            yield chunk


@router.get(
    "",
    dependencies=[Depends(rate_limit_export)],
    summary="Download one of the two registers: to read, to count, or to analyse",
)
async def export_register(
    register: Literal["actions", "consultations"] = Query(..., description="Which register"),
    export_format: Literal["markdown", "csv", "technical"] = Query(
        "markdown",
        alias="format",
        description="Read it, count it, or analyse it — the last one carries no "
        "content and is pseudonymised, so it can be handed on",
    ),
    since: datetime | None = Query(None, description="Inclusive lower bound"),
    until: datetime | None = Query(None, description="Exclusive upper bound"),
    accept_encoding: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_session),
) -> Response:
    """Render the caller's own register as a downloadable document.

    Args:
        register: ``actions`` (what the assistant did) or ``consultations``
            (what it looked at) — two lists, never merged.
        export_format: ``markdown`` to read, ``csv`` to count, ``technical``
            to analyse — the last one is the administrator's own contract, so
            it holds no content and can be shared without exposing anything.
        since: Inclusive lower bound on the period.
        until: Exclusive upper bound. Left out, it becomes the instant the file
            is generated: the count in the headers and the rows in the body
            must describe the same closed window.
        accept_encoding: What the client can decompress.
        db: Session — used for the exact count; the rows are streamed on a
            session of their own.
        user: The authenticated caller. The register exported is always
            theirs; there is no account parameter on this route, so there is
            no way to ask for someone else's by mistake.

    Returns:
        The document, as an attachment named after the register and the day.
        Complete: no ceiling applies, and ``X-Register-Truncated`` says so
        rather than leaving a reader to assume it.
    """
    from src.core.config import settings

    spec = REGISTERS[register]
    media_type, extension = FORMATS[export_format]
    generated_at = datetime.now(UTC)
    asked = TechnicalQuery(
        register=spec.slug,
        since=since,
        until=until or generated_at,
        user_ids=[user.id],
    )

    total = await count_register(db, asked)
    filename = f"lia-{spec.slug}-{generated_at.strftime('%Y%m%d')}.{extension}"
    logger.info(
        "register_exported",
        register=spec.slug,
        export_format=export_format,
        rows=total,
    )
    return attachment_stream(
        _document(
            spec,
            asked,
            export_format=export_format,
            total=total,
            language=user.language,
            timezone=_display_timezone(user),
            generated_at=generated_at,
            batch=settings.effect_export_batch_rows,
        ),
        filename=filename,
        media_type=media_type,
        accept_encoding=accept_encoding,
        extra_headers={
            # The total is EXACT — an aggregate over the same statement the
            # body streams, never the length of what came back (ADR-185).
            "X-Register-Rows": str(total),
            "X-Register-Truncated": "false",
        },
    )


async def _article12_document(
    since: datetime | None,
    until: datetime,
    scope: list[Any],
    *,
    totals: dict[str, int],
    generated_at: datetime,
    batch: int,
) -> AsyncIterator[str]:
    """Compose the five records into one file, reading them one after another.

    Args:
        since: Inclusive lower bound.
        until: Exclusive upper bound — closed, so the totals hold.
        scope: The single account covered.
        totals: The exact count per source, already in the header.
        generated_at: When the file was produced.
        batch: How many rows each cursor buffers at a time.

    Yields:
        The extraction, chunk by chunk.
    """
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


@router.get(
    "/article12",
    dependencies=[Depends(rate_limit_export)],
    summary="Everything recorded about YOUR activity, in one machine-readable file",
)
async def export_article12(
    since: datetime | None = Query(None, description="Inclusive lower bound"),
    until: datetime | None = Query(None, description="Exclusive upper bound"),
    accept_encoding: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_session),
) -> Response:
    """The five records LIA keeps about the caller, composed into one file.

    The same extraction the administrator can run, narrowed to one account —
    and narrowed by CONSTRUCTION rather than by a default: this route declares
    no account parameter, so there is nothing to tamper with, exactly as on
    ``/effects/statistics`` and ``/effects/export``.

    It is also the same CONTRACT, not a reader's variant: the same columns, the
    same exclusions, the same pseudonymisation, including of the caller's own
    identifier. That is what makes the file safe to hand to a lawyer, a data
    protection authority or a bug report without editing it first — and a
    second contract for the same rows would be a second place for a column to
    slip from « forbidden » to « exported ».

    Five sources answer five different questions and never add up, so the
    header states an exact count PER SOURCE. None of them is capped: a file
    complete in four records of five is not a complete file, and the way to
    honour that is to be complete in five (ADR-185, ADR-273).

    Args:
        since: Inclusive lower bound on the period.
        until: Exclusive upper bound; left out, the instant of generation.
        accept_encoding: What the client can decompress.
        db: Session, for the five exact counts.
        user: The authenticated caller, and the only account covered.

    Returns:
        The extraction, as a JSON Lines attachment.
    """
    from src.core.config import settings

    generated_at = datetime.now(UTC)
    closed_until = until or generated_at
    scope = [user.id]
    totals = {
        spec.slug: await count_register(
            db,
            TechnicalQuery(register=spec.slug, since=since, until=closed_until, user_ids=scope),
        )
        for spec in known_sources()
    }

    lines = sum(totals.values())
    logger.info("article12_self_export_served", sources=len(totals), lines=lines)
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
        accept_encoding=accept_encoding,
        extra_headers={
            "X-Register-Rows": str(lines),
            "X-Register-Truncated": "false",
        },
    )
