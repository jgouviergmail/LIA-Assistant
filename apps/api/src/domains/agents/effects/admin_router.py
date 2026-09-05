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

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.dependencies import get_db
from src.core.security.authorization import require_superuser
from src.core.session_dependencies import get_current_active_session
from src.domains.agents.effects.article12_export import (
    article12_filters,
    extract_of,
    known_sources,
    render_article12,
)
from src.domains.agents.effects.models import EffectSource, EffectStatus
from src.domains.agents.effects.technical_reads import TechnicalQuery, read_register
from src.domains.users.models import AdminAuditLog, User

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


def _stated_query(asked: TechnicalQuery) -> dict[str, Any]:
    """What the file SAYS was asked of it.

    Args:
        asked: The operator's request.

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


@router.get(
    "/export",
    response_class=PlainTextResponse,
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_session),
) -> PlainTextResponse:
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

    from src.domains.agents.effects.technical_export import (
        TECHNICAL_SPECS,
        export_header,
        render_jsonl,
        technical_row,
    )

    cap = settings.effect_technical_export_max_rows
    which = _given(register) or "actions"
    spec = TECHNICAL_SPECS[which]
    since, until = _given(since), _given(until)
    tool_name, mutation_policy = _given(tool_name), _given(mutation_policy)
    status, source, execution_mode = _given(status), _given(source), _given(execution_mode)
    scope = _given(user_ids)

    asked = TechnicalQuery(
        register=which,
        since=since,
        until=until,
        user_ids=scope,
        tool_name=tool_name,
        mutation_policy=mutation_policy,
        status=status,
        source=source,
        execution_mode=execution_mode,
    )
    rows = await read_register(db, asked, cap)
    filters = _stated_query(asked)
    content = render_jsonl(
        [technical_row(row, spec) for row in rows],
        export_header(
            row_count=len(rows),
            cap=cap,
            filters=filters,
            generated_at=datetime.now(UTC),
            spec=spec,
        ),
    )
    logger.info(
        "effect_technical_export",
        register=which,
        row_count=len(rows),
        truncated=len(rows) >= cap,
    )
    return PlainTextResponse(
        content,
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="lia-{spec.slug}.jsonl"'},
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
    rows = await EffectLedgerRepository(db).list_for_export(
        user_id=scoped_to, limit=_given(limit) or 50
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


#: Format -> (renderer, media type, file extension). A table rather than three
#: parallel ternaries: a third format becomes an entry, not an edit in three
#: places that can disagree.
_RENDERERS: dict[str, tuple[Any, str, str]] = {}


def _renderers() -> dict[str, tuple[Any, str, str]]:
    """The format table, built on first use (the renderers import lazily)."""
    if not _RENDERERS:
        from src.domains.agents.effects.export_readable import render_csv, render_markdown

        _RENDERERS["markdown"] = (render_markdown, "text/markdown; charset=utf-8", "md")
        _RENDERERS["csv"] = (render_csv, "text/csv; charset=utf-8", "csv")
    return _RENDERERS


def _rendered(
    spec: Any,
    rows: list[Any],
    *,
    export_format: str,
    reader: User,
    limit: int,
    masked: bool,
) -> Response:
    """Shape one register as a downloadable document.

    Args:
        spec: The register's rendering spec.
        rows: Its rows, oldest first.
        export_format: ``markdown`` or ``csv``.
        reader: Whose language and clock the document is written in.
        limit: The cap that was applied, published in the headers.
        masked: Whether the wordings were withheld.

    Returns:
        The attachment. The cap travels in ``X-Register-Truncated``, so a
        register cut at the ceiling says so instead of looking complete.
    """
    renderer, media_type, extension = _renderers()[export_format]
    language = getattr(reader, "language", None) or "en"
    timezone = getattr(reader, "timezone", None) or DEFAULT_USER_DISPLAY_TIMEZONE
    filename = f"lia-admin-{spec.slug}-{datetime.now(UTC).strftime('%Y%m%d')}.{extension}"
    return Response(
        content=renderer(spec, rows, language, timezone),
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Register-Rows": str(len(rows)),
            "X-Register-Truncated": "true" if len(rows) >= limit else "false",
            "X-Register-Masked": "true" if masked else "false",
        },
    )


async def _admin_rows(
    register: str,
    db: AsyncSession,
    user_ids: list[UUID] | None,
    since: datetime | None,
    until: datetime | None,
    limit: int,
) -> list[Any]:
    """Read one register across the accounts an administrator named.

    Args:
        register: ``actions`` or ``consultations``.
        db: Session.
        user_ids: The accounts, or None for every account.
        since: Inclusive lower bound.
        until: Exclusive upper bound.
        limit: Row ceiling.

    Returns:
        The rows, oldest first.
    """
    if register == "actions":
        from src.domains.agents.effects.repository import EffectLedgerRepository

        return list(
            await EffectLedgerRepository(db).list_for_export(
                user_ids=user_ids, since=since, until=until, limit=limit
            )
        )
    from src.domains.agents.effects.treatment_repository import TreatmentRepository

    return list(
        await TreatmentRepository(db).list_for_export(
            user_ids=user_ids, since=since, until=until, limit=limit
        )
    )


async def _reveal(
    db: AsyncSession, request: Request, admin: User, rows: list[Any], scope: list[UUID] | None
) -> None:
    """Decrypt the wordings in place and leave a trace that it happened.

    Args:
        db: Session.
        request: For the audited client details.
        admin: Who read.
        rows: The rows to reveal.
        scope: The accounts asked for, or None for every account.
    """
    from src.domains.agents.effects.repository import EffectLedgerRepository

    for row in rows:
        row.label = EffectLedgerRepository.decrypted_label(row)
    _audit_unmask(
        db,
        request,
        admin,
        scope="all" if scope is None else f"{len(scope)} account(s)",
        row_count=len(rows),
    )
    await db.commit()


@router.get(
    "/export/article12",
    response_class=PlainTextResponse,
    summary="One pseudonymised extraction over every record (JSON Lines)",
)
async def export_article12(
    since: datetime | None = Query(None, description="Inclusive lower bound"),
    until: datetime | None = Query(None, description="Exclusive upper bound"),
    user_ids: list[UUID] | None = Query(
        None, description="One, several, or (omitted) every account"
    ),
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

    cap = settings.article12_export_max_rows_per_source
    filters = article12_filters(since=since, until=until, user_ids=user_ids)
    extracts = []
    for spec in known_sources():
        rows = await read_register(
            db,
            TechnicalQuery(
                register=spec.slug,
                since=since,
                until=until,
                user_ids=user_ids,
                tool_name=None,
                mutation_policy=None,
                status=None,
                source=None,
                execution_mode=None,
            ),
            cap,
        )
        extracts.append(extract_of(spec, rows, cap=cap))

    logger.info(
        "article12_export_served",
        admin_id=str(current_user.id),
        sources=len(extracts),
        lines=sum(len(extract.rows) for extract in extracts),
    )
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    return PlainTextResponse(
        content=render_article12(extracts, cap=cap, filters=filters),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="lia-article12-{stamp}.jsonl"'},
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
    limit = settings.effect_technical_export_max_rows

    rows = await _admin_rows(which, db, scope, _given(since), _given(until), limit)
    if which == "actions":
        if revealed:
            await _reveal(db, request, current_user, rows, scope)
        else:
            rows = [_masked_action(row) for row in rows]

    return _rendered(
        ACTIONS if which == "actions" else TREATMENTS,
        rows,
        export_format=fmt,
        reader=current_user,
        limit=limit,
        masked=not (which == "actions" and revealed),
    )
