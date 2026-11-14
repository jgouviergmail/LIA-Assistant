"""The browser's selected discussion is a versioned server-side Live contract."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.domains.live.schemas import LiveSessionStartRequest
from src.domains.live.session_store import LiveSessionRecord

pytestmark = pytest.mark.unit


def test_live_start_keeps_the_explicit_business_selection() -> None:
    identity = uuid4()
    request = LiveSessionStartRequest.model_validate(
        {"mode": "direct", "conversation_id": str(identity), "conversation_revision": 4}
    )
    wire = request.model_dump(mode="json")
    assert wire["conversation_id"] == str(identity)
    assert wire["conversation_revision"] == 4


@pytest.mark.parametrize(
    "selection",
    [
        {"conversation_id": str(uuid4())},
        {"conversation_revision": 0},
        {"conversation_id": str(uuid4()), "conversation_revision": True},
        {"conversation_id": str(uuid4()), "conversation_revision": -1},
    ],
)
def test_live_start_never_reinterprets_a_partial_or_invalid_selection(
    selection: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        LiveSessionStartRequest.model_validate(selection)


def test_the_lia_target_survives_serialization_sleep_wake_and_vendor_ids() -> None:
    now = datetime.now(UTC)
    record = LiveSessionRecord(
        session_id=uuid4().hex,
        user_id=uuid4(),
        provider="gemini",
        model="fictional-model",
        run_id="live_session_fixture",
        started_at=now,
        expires_at=now + timedelta(minutes=10),
        token=uuid4().hex,
        lia_conversation_id=uuid4(),
        lia_conversation_revision=3,
        lia_activity_id=uuid4(),
    )
    assert LiveSessionRecord.from_json(record.to_json()) == record
    asleep = record.entering_standby(now + timedelta(seconds=3), conversation_id="vendor-id")
    awake = LiveSessionRecord.from_json(asleep.to_json()).waking(now + timedelta(seconds=10))
    assert awake.lia_conversation_id == record.lia_conversation_id
    assert awake.lia_conversation_revision == record.lia_conversation_revision
    assert awake.lia_activity_id == record.lia_activity_id
    assert awake.provider_conversation_ids == ("vendor-id",)
    assert LiveSessionRecord.from_json(replace(awake, extensions=1).to_json()) == replace(
        awake, extensions=1
    )
