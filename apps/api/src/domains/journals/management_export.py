"""Complete portability uses public entry fields and the stored portrait, without retrieval."""

from collections.abc import AsyncGenerator, Mapping
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import raise_user_not_found
from src.core.management_export_file import prepare_management_export_file
from src.core.management_export_response import ManagementExportResponse
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.journals.models import JournalEntry
from src.domains.journals.schemas import JournalEntryResponse
from src.domains.users.models import User
from src.domains.users.repository import UserRepository

# Preserve the legacy CSV order; append newer public fields automatically.
JOURNAL_CSV_FIELDS = tuple(
    dict.fromkeys(
        (
            "id",
            "theme",
            "level",
            "title",
            "content",
            "mood",
            "status",
            "source",
            "personality_code",
            "char_count",
            "confidence",
            "evidence_count",
            "contradiction_count",
            "injection_count",
            "last_injected_at",
            "created_at",
            "updated_at",
            *JournalEntryResponse.model_fields,
        )
    )
)


class StoredJournalPortrait(BaseModel):
    """Portability preserves legacy stored provenance without current-publication filtering."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    full: str | None
    brief: str | None
    compiled_at: datetime | None
    sources: JsonValue


async def lock_journal_export_actor(db: AsyncSession, actor_id: UUID) -> User:
    await require_capability_fresh(db, PlatformCapability.JOURNALS)
    actor = await UserRepository(db).get_by_id_for_preference_update(actor_id)
    if actor is None or not actor.is_active or actor.is_deleted:
        raise_user_not_found(actor_id)
    return actor


async def journal_export_metadata(
    db: AsyncSession, actor_id: UUID, format: Literal["csv", "json"], observed_at: datetime
) -> Mapping[str, object]:
    if format == "csv":
        return {}
    row = (
        (
            await db.execute(
                select(
                    User.journal_portrait_full.label("full"),
                    User.journal_portrait_brief.label("brief"),
                    User.journal_portrait_compiled_at.label("compiled_at"),
                    User.journal_portrait_sources.label("sources"),
                ).where(User.id == actor_id, User.is_active, User.deleted_at.is_(None))
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise_user_not_found(actor_id)
    return {"portrait": StoredJournalPortrait.model_validate(dict(row)).model_dump(mode="json")}


async def journal_export_rows(
    db: AsyncSession,
    actor_id: UUID,
    format: Literal["csv", "json"],
    observed_at: datetime,
    for_update: bool = False,
) -> AsyncGenerator[Mapping[str, object]]:
    fields = tuple(JournalEntryResponse.model_fields)
    statement = (
        select(*(getattr(JournalEntry, name) for name in fields))
        .where(
            JournalEntry.user_id == actor_id,
        )
        .order_by(JournalEntry.created_at.desc(), JournalEntry.id.desc())
    )
    if for_update:
        statement = statement.with_for_update()
    result = await db.stream(statement.execution_options(yield_per=200))
    try:
        async for row in result.mappings():
            yield JournalEntryResponse.model_validate(dict(row)).model_dump(mode="json")
    finally:
        await result.close()


async def export_managed_journals(
    db: AsyncSession, actor_id: UUID, format: Literal["csv", "json"]
) -> ManagementExportResponse:
    await lock_journal_export_actor(db, actor_id)
    now = datetime.now(UTC)
    metadata = await journal_export_metadata(db, actor_id, format, now)
    reader = await prepare_management_export_file(
        journal_export_rows(db, actor_id, format, now, True),
        format=format,
        fieldnames=JOURNAL_CSV_FIELDS,
        collection="entries",
        metadata=metadata,
        max_bytes=settings.account_export_max_bytes,
    )
    try:
        await require_capability_fresh(db, PlatformCapability.JOURNALS)
        return ManagementExportResponse(reader, collection="journals", format=format)
    except BaseException:
        await reader.close()
        raise
