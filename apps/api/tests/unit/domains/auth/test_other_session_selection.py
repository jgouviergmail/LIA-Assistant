"""A frozen revocation snapshot cannot select itself, repeat targets or hide invalid ids."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.domains.auth.session_bulk_schemas import OtherDeviceSessionsSelection
from src.domains.auth.session_queries import ListedDeviceSession

pytestmark = pytest.mark.unit


def session(identity: str, current: bool | None = False) -> ListedDeviceSession:
    return ListedDeviceSession(
        id=identity,
        current=current,
        ua_family=None,
        os_family=None,
        ip_trunc=None,
        auth_methods=[],
        created_at=datetime.now(UTC),
        last_seen_at=None,
        device_name=None,
    )


@pytest.mark.parametrize(
    "fault", ["self", "duplicate", "unknown_current", "current", "id", "naive"]
)
def test_invalid_frozen_fleet_is_refused(fault: str) -> None:
    current_id = "a" * 16
    target = session("b" * 16)
    if fault == "self":
        target.id = current_id
    elif fault == "unknown_current":
        target.current = None
    elif fault == "current":
        target.current = True
    elif fault == "id":
        target.id = "not-an-owned-display-id"
    elif fault == "naive":
        target.created_at = target.created_at.replace(tzinfo=None)
    targets = (target, target) if fault == "duplicate" else (target,)
    with pytest.raises(ValidationError):
        OtherDeviceSessionsSelection(current_display_id=current_id, sessions=targets)


def test_other_session_snapshot_round_trips_without_authentication_material() -> None:
    selection = OtherDeviceSessionsSelection(
        current_display_id="a" * 16, sessions=(session("b" * 16),)
    )
    encoded = selection.model_dump_json()
    assert OtherDeviceSessionsSelection.model_validate_json(encoded) == selection
    assert "step_up_at" not in encoded and "session_id" not in encoded
