"""Observe one addressed recorder and prepare a finite original-controller proposal."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_device_snapshot import RecordingDeviceSnapshot
from src.core.application_origin import ApplicationOrigin
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.meeting_preferences import require_meeting_preferences
from src.domains.agents.application.recording_device_schemas import (
    RecordingDeviceIntent,
    RecordingDevicePatch,
    RecordingDeviceRequest,
    recording_action_allowed,
    recording_states,
)
from src.domains.agents.application.recording_device_spec import RECORDING_DEVICE_OPERATION


async def read_recording_device(
    db: AsyncSession, actor_id: UUID, origin: ApplicationOrigin | None
) -> RecordingDeviceSnapshot:
    await require_meeting_preferences(db, actor_id)
    if origin is None or origin.device_id is None or origin.recording_snapshot is None:
        raise CommandRejected("DEVICE_UNAVAILABLE")
    await origin.require_session(actor_id, expected_binding=origin.binding_id)
    snapshot = origin.recording_snapshot
    if not snapshot.fresh_for(actor_id, now=datetime.now(UTC)):
        raise CommandRejected("STALE_STATE")
    await require_meeting_preferences(db, actor_id)
    return snapshot


async def prepare_recording_device(
    db: AsyncSession,
    actor_id: UUID,
    request: RecordingDeviceRequest,
    origin: ApplicationOrigin | None,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    snapshot = await read_recording_device(db, actor_id, origin)
    if not recording_action_allowed(request, snapshot):
        raise CommandRejected("CONSTRAINT_VIOLATION")
    intent = RecordingDeviceIntent(
        action=request.action, phase=snapshot.phase, meeting_id=snapshot.meeting_id
    )
    return build_action_content(
        actor_id,
        RECORDING_DEVICE_OPERATION,
        RecordingDevicePatch(device_recording=intent),
        *recording_states(intent),
        command_id=command_id,
    )
