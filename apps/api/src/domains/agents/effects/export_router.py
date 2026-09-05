"""Downloading a register: to read, to count, or to analyse (ADR-263).

One endpoint for two registers and three formats, because the combinations are
the same operation with a different renderer — and because a second endpoint
would be a second place for the period, the timezone and the cap to be spelled
slightly differently.

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

The cap travels into the answer's headers, so a truncated register says it was
truncated instead of looking complete.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

import structlog
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE, RATE_LIMIT_EFFECTS_READ_PER_MINUTE
from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.agents.effects.article12_export import (
    article12_filters,
    extract_of,
    known_sources,
    render_article12,
)
from src.domains.agents.effects.export_readable import (
    ACTIONS,
    TREATMENTS,
    RegisterSpec,
    render_csv,
    render_markdown,
)
from src.domains.agents.effects.technical_export import (
    TECHNICAL_SPECS,
    export_header,
    render_jsonl,
    technical_row,
)
from src.domains.agents.effects.technical_reads import TechnicalQuery, read_register
from src.domains.auth.dependencies import create_user_rate_limiter
from src.domains.users.models import User

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/effects/export", tags=["Effects"])

rate_limit_export = create_user_rate_limiter(
    action="effects_export",
    max_calls=RATE_LIMIT_EFFECTS_READ_PER_MINUTE,
)

#: Which register, by the name it carries in its own download.
REGISTERS: dict[str, RegisterSpec] = {ACTIONS.slug: ACTIONS, TREATMENTS.slug: TREATMENTS}


def render_technical(spec: RegisterSpec, rows: list[object], language: str, timezone: str) -> str:
    """Render one register as pseudonymised JSON Lines.

    Signature-compatible with the two readable renderers so the format table
    stays a table. ``language`` and ``timezone`` are deliberately unused: a
    machine-readable file has no reader to localise for, and rendering
    timestamps in a display zone would make two exports of the same rows
    disagree.

    The contract is found BY SLUG, which is why a test pins that the readable
    and technical spec families still share theirs.

    Args:
        spec: Which register, in its readable declaration.
        rows: Its rows, oldest first.
        language: Unused — see above.
        timezone: Unused — see above.

    Returns:
        The file content: one header line, then one line per row.
    """
    from src.core.config import settings

    contract = TECHNICAL_SPECS[spec.slug]
    cap = settings.effect_technical_export_max_rows
    return render_jsonl(
        [technical_row(row, contract) for row in rows],
        export_header(
            row_count=len(rows),
            cap=cap,
            # No account filter to state: this route has none to state.
            filters={},
            generated_at=datetime.now(UTC),
            spec=contract,
        ),
    )


#: Format → (renderer, media type, extension). A table rather than a branch:
#: a third format is an entry, not an edit.
FORMATS: dict[str, tuple[object, str, str]] = {
    "markdown": (render_markdown, "text/markdown; charset=utf-8", "md"),
    "csv": (render_csv, "text/csv; charset=utf-8", "csv"),
    "technical": (render_technical, "application/x-ndjson", "jsonl"),
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


async def _rows(
    spec: RegisterSpec,
    db: AsyncSession,
    user: User,
    since: datetime | None,
    until: datetime | None,
    limit: int,
) -> list[object]:
    """Read one register's rows for this user and period, oldest first.

    Args:
        spec: Which register.
        db: Session.
        user: Whose register — always the caller's, never a parameter.
        since: Inclusive lower bound.
        until: Exclusive upper bound.
        limit: Row ceiling.

    Returns:
        The rows.
    """
    if spec is ACTIONS:
        from src.domains.agents.effects.repository import EffectLedgerRepository

        return list(
            await EffectLedgerRepository(db).list_for_export(
                user_id=user.id, since=since, until=until, limit=limit
            )
        )
    from src.domains.agents.effects.treatment_repository import TreatmentRepository

    return list(
        await TreatmentRepository(db).list_for_export(
            user_id=user.id, since=since, until=until, limit=limit
        )
    )


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
        until: Exclusive upper bound.
        db: Session.
        user: The authenticated caller. The register exported is always
            theirs; there is no account parameter on this route, so there is
            no way to ask for someone else's by mistake.

    Returns:
        The document, as an attachment named after the register and the day.
    """
    from src.core.config import settings

    spec = REGISTERS[register]
    renderer, media_type, extension = FORMATS[export_format]
    limit = settings.effect_technical_export_max_rows

    rows = await _rows(spec, db, user, since, until, limit)
    body: str = renderer(  # type: ignore[operator]
        spec, rows, user.language, _display_timezone(user)
    )

    stamp = datetime.now(UTC).strftime("%Y%m%d")
    filename = f"lia-{spec.slug}-{stamp}.{extension}"
    logger.info(
        "register_exported",
        register=spec.slug,
        export_format=export_format,
        rows=len(rows),
        truncated=len(rows) >= limit,
    )
    return Response(
        content=body,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            # The cap is PUBLISHED, never applied in silence: a reader who got
            # exactly `limit` rows must be able to tell that more exist.
            "X-Register-Rows": str(len(rows)),
            "X-Register-Truncated": "true" if len(rows) >= limit else "false",
        },
    )


@router.get(
    "/article12",
    dependencies=[Depends(rate_limit_export)],
    summary="Everything recorded about YOUR activity, in one machine-readable file",
)
async def export_article12(
    since: datetime | None = Query(None, description="Inclusive lower bound"),
    until: datetime | None = Query(None, description="Exclusive upper bound"),
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
    ceiling applies PER SOURCE and the header states, per source, whether it
    was reached (ADR-185).

    Args:
        since: Inclusive lower bound on the period.
        until: Exclusive upper bound.
        db: Session.
        user: The authenticated caller, and the only account covered.

    Returns:
        The extraction, as a JSON Lines attachment.
    """
    from src.core.config import settings

    scope = [user.id]
    cap = settings.article12_export_max_rows_per_source
    extracts = []
    for spec in known_sources():
        rows = await read_register(
            db, TechnicalQuery(register=spec.slug, since=since, until=until, user_ids=scope), cap
        )
        extracts.append(extract_of(spec, rows, cap=cap))

    lines = sum(len(extract.rows) for extract in extracts)
    logger.info("article12_self_export_served", sources=len(extracts), lines=lines)
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    return Response(
        content=render_article12(
            extracts,
            cap=cap,
            filters=article12_filters(since=since, until=until, user_ids=scope),
        ),
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": f'attachment; filename="lia-article12-{stamp}.jsonl"',
            "X-Register-Rows": str(lines),
            "X-Register-Truncated": (
                "true" if any(extract.capped for extract in extracts) else "false"
            ),
        },
    )
