"""Original UI and confirmed tools share one serial preference transaction."""

import asyncio
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import ResourceConflictError
from src.core.meeting_templates import canonical_template_reference
from src.domains.meetings.models import MeetingPreference, MeetingSttEnginePreference
from src.domains.meetings.preference_owner import lock_meeting_preference_owner
from src.domains.meetings.repository import MeetingPreferenceRepository
from src.domains.meetings.schemas import MeetingPreferencesResponse, MeetingPreferencesUpdate
from src.domains.meetings.template_service import MeetingTemplateService
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.meeting_preferences import (
    MeetingPreferenceCheck,
    MeetingPreferenceCompletionUnknown,
    MeetingPreferenceState,
)


def preference_response(row: MeetingPreference | None) -> MeetingPreferencesResponse:
    return MeetingPreferencesResponse(
        stt_engine=row.stt_engine if row else MeetingSttEnginePreference.AUTO,
        language=row.language if row else "auto",
        auto_email=row.auto_email if row else False,
        keep_audio_hours=row.keep_audio_hours if row else 0,
        default_template_ref=(
            canonical_template_reference(row.default_template_ref) if row else None
        ),
        keep_audio_hours_max=settings.meetings_audio_retention_hours_max,
    )


def require_expected_preferences(
    before: MeetingPreferencesResponse, expected: MeetingPreferenceState | None
) -> None:
    if (
        expected is not None
        and MeetingPreferenceState.model_validate(before.model_dump(mode="json")) != expected
    ):
        raise ResourceConflictError("meeting_preferences", detail={"error_code": "STALE_STATE"})


async def _write_preferences_row(
    repository: MeetingPreferenceRepository,
    row: MeetingPreference | None,
    user_id: UUID,
    desired: MeetingPreferencesUpdate,
    skip: bool,
) -> MeetingPreference | None:
    if skip:
        return row
    if row is None:
        return await repository.create({"user_id": user_id, **desired.model_dump()})
    return await repository.update(row, desired.model_dump())


async def _commit_preferences(
    db: AsyncSession,
    desired: MeetingPreferencesUpdate,
    receipt: PreferenceWriteReceipt | None,
    changed: bool,
) -> None:
    try:
        await db.commit()
    except SQLAlchemyError, asyncio.CancelledError:
        if receipt is not None:
            raise MeetingPreferenceCompletionUnknown() from None
        raise
    if receipt is not None:
        receipt.committed = True
        receipt.no_op = not changed
        receipt.values = desired.model_dump(mode="json")


async def replace_meeting_preferences(
    db: AsyncSession,
    user_id: UUID,
    request: MeetingPreferencesUpdate,
    language: str | None,
    *,
    repository: MeetingPreferenceRepository | None = None,
    expected: MeetingPreferenceState | None = None,
    receipt: PreferenceWriteReceipt | None = None,
    check: MeetingPreferenceCheck | None = None,
) -> MeetingPreferencesResponse:
    repository = repository or MeetingPreferenceRepository(db)
    await lock_meeting_preference_owner(db, user_id)
    if check is not None:
        await check()
    row = await repository.get_for_user(user_id)
    before = preference_response(row)
    require_expected_preferences(before, expected)
    # Only the original resolver authorizes a default template. Deletion uses
    # the same owner lock, so it cannot delete between resolution and save.
    if request.default_template_ref is not None:
        await MeetingTemplateService(db).resolve(user_id, request.default_template_ref, language)
    payload = request.model_dump()
    payload["default_template_ref"] = canonical_template_reference(request.default_template_ref)
    payload["keep_audio_hours"] = min(
        request.keep_audio_hours, settings.meetings_audio_retention_hours_max
    )
    desired = MeetingPreferencesUpdate.model_validate(payload)
    changed = desired.model_dump(mode="json") != before.model_dump(
        mode="json", exclude={"keep_audio_hours_max"}
    )
    row = await _write_preferences_row(
        repository, row, user_id, desired, receipt is not None and not changed
    )
    if check is not None:
        await check()
    if (
        expected is not None
        and settings.meetings_audio_retention_hours_max != expected.keep_audio_hours_max
    ):
        raise ResourceConflictError("meeting_preferences", detail={"error_code": "STALE_STATE"})
    await _commit_preferences(db, desired, receipt, changed)
    return preference_response(row)
