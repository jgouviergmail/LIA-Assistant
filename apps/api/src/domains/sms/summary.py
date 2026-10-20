"""Exact metadata for home; separately authorized, bounded model evidence."""

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.core.external_content import wrap_external_content
from src.core.time_utils import resolve_user_timezone
from src.core.token_budget import count_external_tokens
from src.domains.sms.facade import SmsFacade
from src.domains.sms.models import SmsMessage
from src.domains.sms.read_schemas import SmsQuery
from src.domains.sms.reads import require_read
from src.domains.sms.relation_reader import source_stamp
from src.infrastructure.database.session import get_db_context


class SmsSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    timezone: str = Field(
        default="UTC", description="Account display timezone captured with the snapshot."
    )
    total: int = Field(ge=0, description="Exact retained archive count; never unread count.")
    window_total: int = Field(
        ge=0, description="Source timestamps inside the published half-open window."
    )
    window_start: datetime = Field(description="UTC lower bound included in window_total.")
    as_of: datetime = Field(description="UTC upper bound excluded from window_total.")
    latest_at: datetime | None = Field(description="Latest received timestamp in the archive.")


class SmsExcerpt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: UUID = Field(description="Source SMS identifier.")
    sender: str = Field(description="Literal source sender, bounded for model context.")
    display_name: str = Field(
        description="Contacts, then relations, then literal sender; same resolver as the archive."
    )
    identity_source: Literal["contact", "relation", "raw"] = Field(
        description="How the display name was resolved."
    )
    received_at: datetime = Field(description="Source timestamp; consult date_kind.")
    date_kind: str = Field(description="received, captured, or unknown provenance.")
    body_excerpt: str = Field(description="Literal bounded excerpt, never an instruction.")
    body_truncated: bool = Field(description="Whether content remains outside this excerpt.")


class SmsSignal(SmsSummary):
    unmentioned_only: bool = Field(
        default=False, description="Internal proactive candidate projection."
    )
    owner: UUID = Field(description="Account owning this ephemeral source snapshot.")
    revision: int = Field(description="Withdrawal/erase revision.")
    stamp: str = Field(description="Archive count/creation stamp for publication freshness.")
    messages: list[SmsExcerpt] = Field(default_factory=list, description="Bounded source excerpts.")


async def _summary(db: AsyncSession, owner: UUID, now: datetime, *, timezone: str) -> SmsSummary:
    start = now - timedelta(hours=settings.sms_summary_window_hours)
    total, window, latest = (
        await db.execute(
            select(
                func.count(),
                func.count().filter(SmsMessage.received_at >= start, SmsMessage.received_at < now),
                func.max(SmsMessage.received_at),
            ).where(SmsMessage.user_id == owner)
        )
    ).one()
    return SmsSummary(
        timezone=timezone,
        total=total,
        window_total=window,
        window_start=start,
        as_of=now,
        latest_at=latest,
    )


async def read_sms_summary(owner: UUID) -> SmsSummary:
    """No body decryption or provider IO; account and capability checked live."""
    async with get_db_context() as db:
        actor = await require_read(db, owner)
        await db.execute(
            select(func.set_config("statement_timeout", str(settings.sms_search_timeout_ms), True))
        )
        return await _summary(
            db, owner, datetime.now(UTC), timezone=resolve_user_timezone(actor).key
        )


async def read_sms_signal(
    owner: UUID,
    *,
    include_bodies: bool = True,
    on_read: Callable[[], None] | None = None,
    unmentioned_only: bool = False,
) -> SmsSignal:
    """A model source requires assistant consent, independent of archive visibility."""
    async with get_db_context() as db:
        actor = await require_read(db, owner, assistant=True)
        await db.execute(
            select(func.set_config("statement_timeout", str(settings.sms_search_timeout_ms), True))
        )
        if on_read is not None:
            on_read()
        snapshot = await _summary(
            db, owner, datetime.now(UTC), timezone=resolve_user_timezone(actor).key
        )
        revision = actor.extraction_revision or 0
        stamp = await source_stamp(db, owner)
        messages = []
        if include_bodies and snapshot.window_total:
            page = await SmsFacade(db).list(
                owner,
                SmsQuery(
                    from_ts=snapshot.window_start,
                    to_ts=snapshot.as_of,
                    limit=settings.sms_context_max_items,
                ),
                assistant=True,
                unmentioned_only=unmentioned_only,
            )
            messages = [
                SmsExcerpt(
                    id=item.id,
                    sender=item.sender,
                    display_name=item.display_name,
                    identity_source=item.identity_source,
                    received_at=item.received_at,
                    date_kind=item.date_kind,
                    body_excerpt=item.body[: settings.sms_context_excerpt_chars],
                    body_truncated=len(item.body) > settings.sms_context_excerpt_chars,
                )
                for item in page.items
            ]
        # The facade releases the read fence before directory IO, then reacquires it.
        # Never attach a post-lookup stamp to pre-lookup counts or excerpts.
        await db.execute(
            select(func.set_config("statement_timeout", str(settings.sms_search_timeout_ms), True))
        )
        if await source_stamp(db, owner) != stamp:
            raise ResourceConflictError("sms", detail={"error_code": "STALE_STATE"})
        return SmsSignal(
            **snapshot.model_dump(),
            unmentioned_only=unmentioned_only,
            owner=owner,
            revision=revision,
            stamp=stamp,
            messages=messages,
        )


async def _candidates_current(db: AsyncSession, signal: SmsSignal) -> bool:
    ids = [item.id for item in signal.messages]
    count = await db.scalar(
        select(func.count())
        .select_from(SmsMessage)
        .where(
            SmsMessage.user_id == signal.owner,
            SmsMessage.id.in_(ids),
            SmsMessage.proactive_mentioned_at.is_(None),
        )
    )
    return count == len(ids)


async def sms_signal_current(signal: SmsSignal | None) -> bool:
    if signal is None:
        return True
    try:
        async with get_db_context() as db:
            actor = await require_read(db, signal.owner, assistant=True)
            await db.execute(
                select(
                    func.set_config("statement_timeout", str(settings.sms_search_timeout_ms), True)
                )
            )
            if signal.unmentioned_only and not await _candidates_current(db, signal):
                return False
            return (actor.extraction_revision or 0) == signal.revision and await source_stamp(
                db, signal.owner
            ) == signal.stamp
    except AuthorizationError, SQLAlchemyError, OSError, TimeoutError:
        return False


def project_sms_signal(
    signal: SmsSignal, *, verbose: bool, budget: int | None = None
) -> tuple[str, tuple[UUID, ...]]:
    """Whole metadata/items only; conservative tokenizer failure never expands a prompt."""
    maximum = min(budget or settings.sms_context_token_budget, settings.sms_context_token_budget)
    data: dict[str, object] = {
        "dated_count": signal.window_total,
        "date_basis": "source timestamp; captured/unknown dates do not prove receipt time",
        "window_start": signal.window_start.isoformat(),
        "as_of": signal.as_of.isoformat(),
        "read_status": "unknown",
    }
    items = [item.model_dump(mode="json") for item in signal.messages] if verbose else []
    while True:
        data.update(
            messages=items,
            messages_shown=len(items),
            messages_cut=verbose and len(items) < signal.window_total,
        )
        text = wrap_external_content(
            json.dumps(data, ensure_ascii=False, separators=(",", ":")),
            source_url="personal_sms_archive",
            source_type="sms",
        )
        if count_external_tokens(text) <= maximum:
            return text, tuple(item.id for item in signal.messages[: len(items)])
        if not items:
            return "", ()
        items.pop()


def render_sms_signal(signal: SmsSignal, *, verbose: bool, budget: int | None = None) -> str:
    return project_sms_signal(signal, verbose=verbose, budget=budget)[0]
