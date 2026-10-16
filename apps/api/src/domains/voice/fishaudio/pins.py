"""The public Fish Audio voices the instance pinned, as they are stored (ADR-345 amendment 2026-10-14).

ONE list for every voice slot, in the order the voices were pinned. Every read and
write opens a short session of its own and closes it before anything waits on the
network (ADR-304): a listing reads the ids, then asks the vendor. A pin is added
under the instance's lock, so two administrators pinning at once cannot pass the
published ceiling together; pinning a voice already pinned changes nothing.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.llm_config.authorization import lock_current_admin
from src.domains.voice.fishaudio.catalogue_revision import advance_revision, lock_catalogue
from src.domains.voice.fishaudio.credential import require_current_account
from src.domains.voice.fishaudio.library_errors import VOICE_IN_USE, refuse
from src.domains.voice.fishaudio.models import FishAudioPinnedVoice
from src.domains.voice.fishaudio.slot_references import slots_by_voice
from src.infrastructure.database.owner_lock import INSTANCE_OWNER, hold_owner_lock
from src.infrastructure.database.session import get_db_context

#: The scope the pins' writers are serialised in.
_LOCK_SCOPE = "fishaudio_pinned_voices"


class PinsFull(Exception):
    """The list holds the published ceiling: nothing more can be pinned."""


async def _ids(db: AsyncSession) -> tuple[str, ...]:
    rows = await db.execute(
        select(FishAudioPinnedVoice.voice_id).order_by(
            FishAudioPinnedVoice.created_at, FishAudioPinnedVoice.id
        )
    )
    return tuple(rows.scalars())


async def read_pins() -> tuple[str, ...]:
    """The pinned voice ids, in the order they were pinned."""
    async with get_db_context() as db:
        return await _ids(db)


async def add_pin(
    voice_id: str, pinned_by: UUID, *, credential_fingerprint: str
) -> tuple[tuple[str, ...], bool]:
    """Pin ``voice_id`` once, unless the list is full.

    Args:
        voice_id: A well-formed vendor model id.
        pinned_by: The administrator pinning it.

    Returns:
        The pins after the act, and whether THIS call pinned the voice
        (``False`` when it already was).

    Raises:
        PinsFull: The list already holds ``settings.fishaudio_pinned_voices_max`` voices.
    """
    async with get_db_context() as db:
        await require_current_account(db, credential_fingerprint)
        await lock_current_admin(db, pinned_by, action="pin a Fish Audio voice")
        await hold_owner_lock(db, _LOCK_SCOPE, INSTANCE_OWNER)
        pins = await _ids(db)
        if voice_id in pins:
            return pins, False
        if len(pins) >= settings.fishaudio_pinned_voices_max:
            raise PinsFull(len(pins))
        db.add(FishAudioPinnedVoice(voice_id=voice_id, pinned_by=pinned_by))
        await db.flush()
        return (*pins, voice_id), True


async def remove_pin(voice_id: str, admin_id: UUID) -> tuple[tuple[str, ...], bool]:
    """Unpin ``voice_id``; nothing happens when it was not pinned.

    Returns:
        The pins after the act, and whether THIS call unpinned the voice.
    """
    async with get_db_context() as db:
        await lock_catalogue(db)
        await lock_current_admin(db, admin_id, action="unpin a Fish Audio voice")
        await hold_owner_lock(db, _LOCK_SCOPE, INSTANCE_OWNER)
        slots = (await slots_by_voice(db)).get(voice_id, [])
        if slots:
            refuse(status.HTTP_409_CONFLICT, VOICE_IN_USE, slots=slots)
        removed = await db.execute(
            delete(FishAudioPinnedVoice)
            .where(FishAudioPinnedVoice.voice_id == voice_id)
            .returning(FishAudioPinnedVoice.id)
        )
        unpinned = removed.first() is not None
        if unpinned:
            await advance_revision(db)
        return await _ids(db), unpinned


__all__ = ["PinsFull", "add_pin", "read_pins", "remove_pin"]
