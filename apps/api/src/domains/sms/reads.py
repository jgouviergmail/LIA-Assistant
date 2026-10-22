"""Fresh consent gates every reader; one projection powers all SMS surfaces."""

import builtins
from collections.abc import Callable
from datetime import datetime
from time import perf_counter
from typing import Never
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError, ResourceNotFoundError
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.ingestion.key_material import key_for_owner
from src.domains.sms.content import read_sms_content
from src.domains.sms.cursors import SmsCursor, cursor_for
from src.domains.sms.models import SmsMessage
from src.domains.sms.preferences import SmsPreferences
from src.domains.sms.read_schemas import SmsPage, SmsQuery, SmsSenderPage, SmsSenderView, SmsView
from src.domains.sms.repository import (
    after_cursor,
    count_messages,
    lexical_candidates,
    message_query,
    project,
)
from src.domains.sms.search import blind_digest, blind_terms, tokenize
from src.domains.sms.sender_policy import normalize_sender
from src.domains.users.models import User


async def require_read(db: AsyncSession, owner: UUID, *, assistant: bool = False) -> User:
    # Short shared owner fence: no provider I/O while held. Withdrawal and erase
    # acquire the exclusive counterpart, so a publication cannot straddle them.
    actor = await db.scalar(
        select(User)
        .where(User.id == owner, User.is_active.is_(True), User.deleted_at.is_(None))
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    if actor is None:
        raise AuthorizationError(detail={"error_code": "FORBIDDEN"})
    await require_capability_fresh(db, PlatformCapability.SMS)
    if assistant and not SmsPreferences.from_stored(actor.sms_preferences).assistant_enabled:
        raise AuthorizationError(detail={"error_code": "SMS_CONSENT_REQUIRED"})
    return actor


class SmsReadService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list(
        self,
        owner: UUID,
        query: SmsQuery,
        *,
        assistant: bool,
        unmentioned_only: bool = False,
        on_read: Callable[[], None] | None = None,
    ) -> SmsPage:
        actor = await require_read(self.db, owner, assistant=assistant)
        cursor = cursor_for(owner, query, actor.extraction_revision or 0)
        if on_read is not None:
            on_read()
        if actor.ingestion_key_encrypted is None and (
            query.sender is not None or query.query is not None
        ):
            existing = await self.db.scalar(
                select(SmsMessage.id).where(SmsMessage.user_id == owner).limit(1)
            )
            if existing is None:
                if query.query is not None:
                    _required_terms(query.query)
                await require_read(self.db, owner, assistant=assistant)
                return SmsPage(items=[], total=0, as_of=cursor.as_of, revision=cursor.revision)
        sender_digest = (
            blind_digest(owner, "sender", normalize_sender(query.sender), key=key_for_owner(actor))
            if query.sender is not None
            else None
        )
        statement = await message_query(self.db, owner, query, cursor, sender_digest=sender_digest)
        if unmentioned_only:
            statement = statement.where(SmsMessage.proactive_mentioned_at.is_(None))
        if query.query is not None:
            rows, total = await self._search(actor, query, statement, cursor)
        else:
            total = await count_messages(self.db, statement)
            rows = list(
                (
                    await self.db.scalars(after_cursor(statement, cursor).limit(query.limit + 1))
                ).all()
            )
        views = [project(row) for row in rows[: query.limit]]
        next_cursor = (
            _next(cursor, views[-1].received_at, views[-1].id) if len(rows) > query.limit else None
        )
        await require_read(self.db, owner, assistant=assistant)
        return SmsPage(
            items=views,
            total=total,
            as_of=cursor.as_of,
            revision=cursor.revision,
            next_cursor=next_cursor,
        )

    async def _search(
        self, actor: User, query: SmsQuery, statement: Select[tuple[SmsMessage]], cursor: SmsCursor
    ) -> tuple[builtins.list[SmsMessage], int]:
        started = perf_counter()
        text = query.query or ""
        terms = _required_terms(text)
        hashes = blind_terms(actor.id, text, key=key_for_owner(actor))
        candidates = await self._candidates(lexical_candidates(statement, actor.id, hashes))
        verified = _verify(candidates, set(terms), started + settings.sms_search_timeout_ms / 1000)
        total = len(verified)
        if cursor.stamp is not None and cursor.id is not None:
            verified = [
                row for row in verified if (row.received_at, row.id) < (cursor.stamp, cursor.id)
            ]
        return verified[: query.limit + 1], total

    async def _candidates(self, statement: Select[tuple[SmsMessage]]) -> builtins.list[SmsMessage]:
        previous = await self.db.scalar(select(func.current_setting("statement_timeout"))) or "0"
        await self.db.execute(
            select(func.set_config("statement_timeout", str(settings.sms_search_timeout_ms), True))
        )
        try:
            candidates = list(
                (
                    await self.db.scalars(
                        statement.order_by(
                            SmsMessage.received_at.desc(), SmsMessage.id.desc()
                        ).limit(settings.sms_search_max_candidates + 1)
                    )
                ).all()
            )
        except DBAPIError as error:
            await self.db.rollback()
            if getattr(error.orig, "sqlstate", None) == "57014":
                _too_broad()
            raise
        await self.db.execute(select(func.set_config("statement_timeout", previous, True)))
        if len(candidates) > settings.sms_search_max_candidates:
            _too_broad()
        return candidates

    async def get(
        self,
        owner: UUID,
        message_id: UUID,
        *,
        assistant: bool,
        on_read: Callable[[], None] | None = None,
    ) -> SmsView:
        """Read one of the owner's SMS, the read guard checked before and after.

        Args:
            owner: The account.
            message_id: The SMS.
            assistant: Whether the assistant reads it, which needs the person's consent.
            on_read: Called once the guard passed, before the row is read.

        Returns:
            The SMS view.

        Raises:
            AuthorizationError: SMS are off, or the assistant may not read them.
            ResourceNotFoundError: The SMS is not the owner's.
        """
        await require_read(self.db, owner, assistant=assistant)
        if on_read is not None:
            on_read()
        message = await self.db.scalar(
            select(SmsMessage).where(SmsMessage.id == message_id, SmsMessage.user_id == owner)
        )
        if message is None:
            raise ResourceNotFoundError("sms", message_id)
        result = project(message)
        await require_read(self.db, owner, assistant=assistant)
        return result

    async def senders(
        self, owner: UUID, *, assistant: bool, limit: int = 20, cursor: str | None = None
    ) -> SmsSenderPage:
        actor = await require_read(self.db, owner, assistant=assistant)
        selected = SmsQuery(limit=limit, cursor=cursor)
        window = cursor_for(owner, selected, actor.extraction_revision or 0, surface="senders")
        ranked = (
            select(
                SmsMessage.id.label("id"),
                func.row_number()
                .over(
                    partition_by=SmsMessage.sender_hash,
                    order_by=(SmsMessage.received_at.desc(), SmsMessage.id.desc()),
                )
                .label("rank"),
                func.count().over(partition_by=SmsMessage.sender_hash).label("total"),
            )
            .where(SmsMessage.user_id == owner, SmsMessage.created_at <= window.as_of)
            .subquery()
        )
        statement = select(SmsMessage).where(
            SmsMessage.user_id == owner,
            SmsMessage.id.in_(select(ranked.c.id).where(ranked.c.rank == 1)),
        )
        total = await count_messages(self.db, statement)
        rows = (
            await self.db.execute(
                after_cursor(statement, window)
                .add_columns(ranked.c.total)
                .join(ranked, ranked.c.id == SmsMessage.id)
                .limit(limit + 1)
            )
        ).all()
        items = []
        for row, count in rows[:limit]:
            sender = read_sms_content(row.sender_encrypted)
            items.append(
                SmsSenderView(
                    id=row.id,
                    sender=sender,
                    display_name=sender,
                    total=count,
                    latest_at=row.received_at,
                )
            )
        next_cursor = (
            _next(window, items[-1].latest_at, items[-1].id) if len(rows) > limit else None
        )
        await require_read(self.db, owner, assistant=assistant)
        return SmsSenderPage(
            items=items,
            total=total,
            as_of=window.as_of,
            revision=window.revision,
            next_cursor=next_cursor,
        )


def _next(cursor: SmsCursor, stamp: datetime, identifier: UUID) -> str:
    return cursor.model_copy(update={"stamp": stamp, "id": identifier}).encode()


def _too_broad() -> Never:
    raise ResourceConflictError("sms_search", detail={"error_code": "QUERY_TOO_BROAD"})


def _required_terms(text: str) -> tuple[str, ...]:
    terms = tokenize(text)
    if not terms or len(terms) > settings.sms_search_max_query_terms:
        _too_broad()
    return terms


def _verify(candidates: list[SmsMessage], required: set[str], deadline: float) -> list[SmsMessage]:
    result = []
    decoded = 0
    for row in candidates:
        body = read_sms_content(row.body_encrypted)
        decoded += len(body)
        if decoded > settings.sms_search_max_verified_chars or perf_counter() > deadline:
            _too_broad()
        if required.issubset(tokenize(body)):
            result.append(row)
    if perf_counter() > deadline:
        _too_broad()
    return result
