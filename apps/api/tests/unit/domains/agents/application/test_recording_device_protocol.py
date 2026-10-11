"""Device reports are finite observations, never role or server completion proof."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.application_device_snapshot import RecordingDeviceSnapshot
from src.domains.agents.application.recording_device_schemas import (
    RecordingDeviceAck,
    RecordingDeviceIntent,
    RecordingDeviceRequest,
    recording_ack_matches,
    recording_action_allowed,
)

pytestmark = pytest.mark.unit


def test_device_snapshot_rejects_unknown_fields_and_incoherent_capture() -> None:
    base = {
        "actor_id": uuid4(),
        "observed_at": datetime.now(UTC),
        "supported": True,
        "phase": "idle",
        "meeting_id": None,
    }
    with pytest.raises(ValidationError):
        RecordingDeviceSnapshot.model_validate({**base, "session_cookie": "secret"})
    with pytest.raises(ValidationError):
        RecordingDeviceSnapshot.model_validate({**base, "phase": "recording"})
    snapshot = RecordingDeviceSnapshot.model_validate(base)
    assert snapshot.fresh_for(snapshot.actor_id, now=datetime.now(UTC))
    assert not snapshot.fresh_for(uuid4(), now=datetime.now(UTC))
    assert not snapshot.fresh_for(snapshot.actor_id, now=datetime.now(UTC) + timedelta(minutes=1))


@pytest.mark.parametrize(
    "action,phase,allowed",
    [
        ("start", "idle", True),
        ("start", "recording", False),
        ("resume", "interrupted", True),
        ("resume", "processing", False),
        ("stop", "recording", True),
        ("discard", "interrupted", True),
        ("discard", "processing", False),
        ("finalize_with_gaps", "interrupted", True),
    ],
)
def test_actions_cannot_bypass_original_lifecycle(action: str, phase: str, allowed: bool) -> None:
    snapshot = RecordingDeviceSnapshot.model_validate(
        {
            "actor_id": uuid4(),
            "observed_at": datetime.now(UTC),
            "supported": True,
            "phase": phase,
            "meeting_id": None if phase == "idle" else uuid4(),
        }
    )
    assert recording_action_allowed(RecordingDeviceRequest(action=action), snapshot) is allowed


def test_device_ack_does_not_accept_a_server_success_or_arbitrary_dispatch() -> None:
    with pytest.raises(ValidationError):
        RecordingDeviceRequest(action="javascript")
    with pytest.raises(ValidationError):
        RecordingDeviceAck.model_validate(
            {
                "claim_token": uuid4(),
                "result": "completed",
                "phase": "recording",
                "meeting_id": uuid4(),
                "committed": True,
            }
        )


def test_completion_must_match_the_claimed_action_and_original_meeting() -> None:
    original = uuid4()
    intent = RecordingDeviceIntent(action="stop", phase="recording", meeting_id=original)
    ack = RecordingDeviceAck(
        claim_token=uuid4(), result="completed", phase="processing", meeting_id=original
    )
    assert recording_ack_matches(intent, ack)
    assert not recording_ack_matches(intent, ack.model_copy(update={"meeting_id": uuid4()}))
    assert not recording_ack_matches(intent, ack.model_copy(update={"phase": "recording"}))
