"""Indexed, deterministic owner predicates; no provider or model calls."""

from uuid import UUID

from sqlalchemy import Select, func, literal, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceNotFoundError
from src.domains.sms.constants import SMS_SEARCH_INDEX_VERSION
from src.domains.sms.content import read_sms_content
from src.domains.sms.cursors import SmsCursor
from src.domains.sms.models import SmsMessage, SmsSearchTerm
from src.domains.sms.read_schemas import SmsQuery, SmsView


async def message_query(
    db: AsyncSession,
    owner: UUID,
    query: SmsQuery,
    cursor: SmsCursor,
    *,
    sender_digest: str | None = None,
) -> Select[tuple[SmsMessage]]:
    statement = select(SmsMessage).where(
        SmsMessage.user_id == owner, SmsMessage.created_at <= cursor.as_of
    )
    if query.sender is not None:
        if sender_digest is None:
            raise ValueError("SENDER_DIGEST_REQUIRED")
        statement = statement.where(SmsMessage.sender_hash == sender_digest)
    if query.from_ts:
        statement = statement.where(SmsMessage.received_at >= query.from_ts)
    if query.to_ts:
        statement = statement.where(SmsMessage.received_at < query.to_ts)
    if query.sender_id:
        sender = await db.scalar(
            select(SmsMessage.sender_hash).where(
                SmsMessage.user_id == owner, SmsMessage.id == query.sender_id
            )
        )
        if sender is None:
            raise ResourceNotFoundError("sms_sender", query.sender_id)
        statement = statement.where(SmsMessage.sender_hash == sender)
    return statement


def after_cursor(
    statement: Select[tuple[SmsMessage]], cursor: SmsCursor
) -> Select[tuple[SmsMessage]]:
    if cursor.stamp is not None and cursor.id is not None:
        statement = statement.where(
            tuple_(SmsMessage.received_at, SmsMessage.id)
            < tuple_(literal(cursor.stamp), literal(cursor.id))
        )
    return statement.order_by(SmsMessage.received_at.desc(), SmsMessage.id.desc())


def lexical_candidates(
    statement: Select[tuple[SmsMessage]], owner: UUID, required: tuple[str, ...]
) -> Select[tuple[SmsMessage]]:
    matching = select(SmsSearchTerm.message_id).where(
        SmsSearchTerm.user_id == owner,
        SmsSearchTerm.index_version == SMS_SEARCH_INDEX_VERSION,
        SmsSearchTerm.term_hashes.contains([bytes.fromhex(term) for term in required]),
    )
    present = (
        select(SmsSearchTerm.message_id)
        .where(
            SmsSearchTerm.user_id == owner,
            SmsSearchTerm.message_id == SmsMessage.id,
            SmsSearchTerm.index_version == SMS_SEARCH_INDEX_VERSION,
        )
        .exists()
    )
    return statement.where(
        or_(SmsMessage.id.in_(matching), SmsMessage.search_complete.is_(False), ~present)
    )


def project(message: SmsMessage) -> SmsView:
    sender = read_sms_content(message.sender_encrypted)
    return SmsView(
        id=message.id,
        sender=sender,
        display_name=sender,
        body=read_sms_content(message.body_encrypted),
        received_at=message.received_at,
        date_kind=message.date_kind,
        origin=message.origin,
    )


async def count_messages(db: AsyncSession, statement: Select[tuple[SmsMessage]]) -> int:
    return int(await db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
