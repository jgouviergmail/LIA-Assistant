"""Finite original-recorder commands and explicitly device-reported results."""

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, JsonValue

from src.core.application_device_snapshot import RecordingDeviceSnapshot, RecordingPhase
from src.domains.agents.application.draft_models import ApplicationActionDraftContent

RecordingAction = Literal["start", "stop", "resume", "finalize_with_gaps", "discard"]


class RecordingDeviceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    action: RecordingAction


class RecordingDeviceIntent(RecordingDeviceRequest):
    phase: RecordingPhase
    meeting_id: UUID | None


class RecordingDevicePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    device_recording: RecordingDeviceIntent


class RecordingDeviceField(StrEnum):
    RECORDING = "device_recording"


class RecordingDeviceClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    command_id: UUID
    claim_token: UUID
    expires_at: AwareDatetime
    intent: RecordingDeviceIntent


class RecordingDeviceAck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    claim_token: UUID
    result: Literal["completed", "refused", "unknown"]
    phase: RecordingPhase
    meeting_id: UUID | None


_PHASES: dict[RecordingAction, frozenset[RecordingPhase]] = {
    "start": frozenset({"idle", "error"}),
    "stop": frozenset({"recording", "offline"}),
    "resume": frozenset({"interrupted"}),
    "finalize_with_gaps": frozenset({"interrupted"}),
    "discard": frozenset({"recording", "offline", "interrupted", "error"}),
}


def recording_action_allowed(
    request: RecordingDeviceRequest, snapshot: RecordingDeviceSnapshot
) -> bool:
    return (
        snapshot.supported
        and snapshot.phase in _PHASES[request.action]
        and (
            snapshot.meeting_id is None
            if request.action == "start"
            else snapshot.meeting_id is not None
        )
    )


def recording_ack_matches(intent: RecordingDeviceIntent, ack: RecordingDeviceAck) -> bool:
    if ack.result != "completed":
        return True
    if intent.action == "discard":
        return ack.phase == "idle" and ack.meeting_id is None
    if intent.action == "start":
        return ack.phase in {"recording", "offline"} and ack.meeting_id is not None
    phases = {"recording", "offline"} if intent.action == "resume" else {"processing"}
    return ack.phase in phases and ack.meeting_id == intent.meeting_id


def recording_states(
    intent: RecordingDeviceIntent,
) -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    return {
        "device_recording": {
            "phase": intent.phase,
            "meeting_id": str(intent.meeting_id) if intent.meeting_id else None,
        }
    }, {
        "device_recording": {
            "action": intent.action,
            "device_reported": True,
            "processing_completed": False,
        }
    }


def canonical_recording_device(draft: ApplicationActionDraftContent) -> bool:
    intent = RecordingDevicePatch.model_validate(draft.intent).device_recording
    before, after = recording_states(intent)
    return (
        draft.operation_id == "meeting_device.control"
        and draft.before == before
        and draft.after == after
    )
