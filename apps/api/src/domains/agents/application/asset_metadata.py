"""Owned generated metadata is read once without loading extracted document bodies."""

from uuid import UUID

from pydantic import JsonValue, TypeAdapter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.command_service import CommandRejected
from src.domains.attachments.models import Attachment
from src.domains.attachments.origin import GENERATED_ORIGINS
from src.domains.attachments.schemas import GeneratedAssetSummary

_ROW = TypeAdapter(dict[str, JsonValue])
_METADATA_FIELDS = (
    "id",
    "user_id",
    "original_filename",
    "stored_filename",
    "mime_type",
    "file_size",
    "file_path",
    "content_type",
    "origin",
    "title",
    "shared_by_name",
    "conversation_id",
    "status",
    "expires_at",
    "created_at",
    "updated_at",
)
assert set(GeneratedAssetSummary.model_fields) <= set(_METADATA_FIELDS)


async def owned_generated_metadata(
    db: AsyncSession, actor_id: UUID, ids: tuple[UUID, ...], *, lock: bool = False
) -> list[dict[str, JsonValue]]:
    predicate = (
        Attachment.id.in_(ids),
        Attachment.user_id == actor_id,
        Attachment.origin.in_([origin.value for origin in GENERATED_ORIGINS]),
    )
    if lock:
        await db.execute(
            select(Attachment.id).where(*predicate).order_by(Attachment.id).with_for_update()
        )
    fields = [value for name in _METADATA_FIELDS for value in (name, Attachment.__table__.c[name])]
    rows = [
        _ROW.validate_python(row)
        for row in (
            await db.scalars(
                select(func.jsonb_build_object(*fields)).where(*predicate).order_by(Attachment.id)
            )
        ).all()
    ]
    by_id = {UUID(str(row["id"])): row for row in rows}
    if len(by_id) != len(ids):
        raise CommandRejected("NOT_FOUND_OR_UNAUTHORIZED")
    return [by_id[identity] for identity in ids]
