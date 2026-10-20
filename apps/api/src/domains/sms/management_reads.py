"""Personal metadata shares fresh authority with the archive, without assistant data access."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import ResourceConflictError, raise_invalid_input
from src.core.security.utils import decrypt_data
from src.domains.ingestion.models import (
    IngestionDelivery,
    IngestionReceipt,
    IngestionSource,
    IngestionToken,
)
from src.domains.ingestion.registry import IngestionResource
from src.domains.ingestion.schemas import IngestionTokenRow
from src.domains.sms.content import read_sms_content
from src.domains.sms.management_read_schemas import (
    SmsArchiveUsage,
    SmsDeviceDeliveryCounts,
    SmsManagementPageQuery,
    SmsSenderBlockPage,
    SmsSenderBlockView,
    SmsSettingsView,
    SmsTokenPage,
)
from src.domains.sms.models import SmsMessage, SmsSenderBlock
from src.domains.sms.preferences import SmsPreferences
from src.domains.sms.reads import require_read


def _as_of(query: SmsManagementPageQuery) -> datetime:
    stamp = query.as_of or datetime.now(UTC)
    if stamp > datetime.now(UTC):
        raise_invalid_input("Observation time cannot be in the future")
    return stamp


def _token_view(token: IngestionToken, source: IngestionSource) -> IngestionTokenRow:
    try:
        label = decrypt_data(source.label_encrypted)
    except ValueError:
        label = None
    return IngestionTokenRow(
        id=token.id,
        source_id=source.id,
        resource=IngestionResource.SMS,
        label=label,
        token_prefix=token.token_prefix,
        scopes=tuple(token.scopes),
        created_at=token.created_at,
        last_used_at=token.last_used_at,
        revoked_at=token.revoked_at,
    )


class SmsManagementReader:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def settings(self, owner: UUID) -> SmsSettingsView:
        actor = await require_read(self.db, owner, assistant=False)
        messages = (
            await self.db.execute(
                select(
                    func.count(SmsMessage.id),
                    func.coalesce(func.sum(SmsMessage.logical_bytes), 0),
                    func.max(SmsMessage.received_at),
                ).where(SmsMessage.user_id == owner)
            )
        ).one()
        receipts = int(
            await self.db.scalar(
                select(func.count(IngestionReceipt.id))
                .join(IngestionSource, IngestionSource.id == IngestionReceipt.source_id)
                .where(IngestionReceipt.user_id == owner, IngestionSource.resource == "sms")
            )
            or 0
        )
        groups = (
            await self.db.execute(
                select(IngestionDelivery.state, func.count())
                .where(IngestionDelivery.user_id == owner, IngestionDelivery.device_id.is_not(None))
                .group_by(IngestionDelivery.state)
            )
        ).all()
        counts = {state: int(count) for state, count in groups}
        return SmsSettingsView(
            preferences=SmsPreferences.from_stored(actor.sms_preferences),
            usage=SmsArchiveUsage(
                message_count=messages[0],
                logical_bytes=messages[1],
                last_received_at=messages[2],
                receipt_count=receipts,
                max_logical_bytes=settings.sms_archive_max_logical_bytes,
                max_receipts=settings.ingestion_max_receipts_per_user,
            ),
            device_deliveries=SmsDeviceDeliveryCounts.model_validate(counts),
        )

    async def tokens(self, owner: UUID, query: SmsManagementPageQuery) -> SmsTokenPage:
        await require_read(self.db, owner, assistant=False)
        query = SmsManagementPageQuery.model_validate(query.model_dump())
        stamp = _as_of(query)
        statement = (
            select(IngestionToken, IngestionSource)
            .join(IngestionSource, IngestionSource.id == IngestionToken.source_id)
            .where(
                IngestionToken.user_id == owner,
                IngestionSource.resource == "sms",
                IngestionToken.created_at <= stamp,
            )
        )
        total = int(
            await self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        )
        if query.after_id is not None:
            cursor = (
                await self.db.execute(statement.where(IngestionToken.id == query.after_id))
            ).first()
            if cursor is None:
                raise ResourceConflictError("sms_tokens", detail={"error_code": "STALE_STATE"})
            statement = statement.where(
                tuple_(IngestionToken.created_at, IngestionToken.id)
                < (cursor[0].created_at, cursor[0].id)
            )
        rows = (
            await self.db.execute(
                statement.order_by(
                    IngestionToken.created_at.desc(), IngestionToken.id.desc()
                ).limit(query.limit + 1)
            )
        ).all()
        items = [_token_view(token, source) for token, source in rows[: query.limit]]
        return SmsTokenPage(
            tokens=items,
            total=total,
            as_of=stamp,
            next_cursor=items[-1].id if len(rows) > query.limit else None,
        )

    async def blocks(self, owner: UUID, query: SmsManagementPageQuery) -> SmsSenderBlockPage:
        await require_read(self.db, owner, assistant=False)
        query = SmsManagementPageQuery.model_validate(query.model_dump())
        stamp = _as_of(query)
        statement = select(SmsSenderBlock).where(
            SmsSenderBlock.user_id == owner, SmsSenderBlock.created_at <= stamp
        )
        total = int(
            await self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        )
        if query.after_id is not None:
            cursor = await self.db.scalar(statement.where(SmsSenderBlock.id == query.after_id))
            if cursor is None:
                raise ResourceConflictError("sms_blocks", detail={"error_code": "STALE_STATE"})
            statement = statement.where(
                tuple_(SmsSenderBlock.created_at, SmsSenderBlock.id)
                < (cursor.created_at, cursor.id)
            )
        rows = (
            await self.db.scalars(
                statement.order_by(
                    SmsSenderBlock.created_at.desc(), SmsSenderBlock.id.desc()
                ).limit(query.limit + 1)
            )
        ).all()
        items = [
            SmsSenderBlockView(
                id=row.id, sender=read_sms_content(row.sender_encrypted), created_at=row.created_at
            )
            for row in rows[: query.limit]
        ]
        return SmsSenderBlockPage(
            blocks=items,
            total=total,
            as_of=stamp,
            next_cursor=items[-1].id if len(rows) > query.limit else None,
        )
