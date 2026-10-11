"""Future settings are complete, bounded proposals, never recording instructions."""

from typing import get_args
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.meeting_preference_schemas import MeetingPreferenceInput
from src.domains.agents.application.meeting_preferences import prepare_meeting_preferences
from src.domains.meetings.models import MeetingSttEnginePreference
from src.domains.meetings.schemas import MeetingPreferencesResponse, MeetingPreferencesUpdate
from src.infrastructure.meeting_preferences import MeetingPreferenceState, MeetingPreferenceValues

pytestmark = pytest.mark.unit


def test_new_original_preference_fields_or_engine_values_require_native_coverage() -> None:
    assert (
        set(MeetingPreferenceInput.model_fields)
        == set(MeetingPreferenceValues.model_fields)
        == set(MeetingPreferencesUpdate.model_fields)
    )
    assert set(MeetingPreferenceState.model_fields) == set(MeetingPreferencesResponse.model_fields)
    assert set(get_args(MeetingPreferenceValues.model_fields["stt_engine"].annotation)) == {
        item.value for item in MeetingSttEnginePreference
    }


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"auto_email": "false"},
        {"auto_email": None},
        {"keep_audio_hours": -1},
        {"keep_audio_hours": True},
        {"keep_audio_hours_max": 99},
        {"language": "fr-FR"},
        {"stt_engine": "invented"},
    ],
)
def test_malformed_or_administrator_settings_are_refused(payload: object) -> None:
    with pytest.raises(ValidationError):
        MeetingPreferenceInput.model_validate(payload)


async def test_sparse_change_preserves_settings_and_displays_enforced_retention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.domains.agents.application import meeting_preferences as owner

    state = MeetingPreferenceState(
        stt_engine="local",
        language="fr",
        auto_email=True,
        keep_audio_hours=3,
        default_template_ref="builtin:standard",
        keep_audio_hours_max=24,
    )
    monkeypatch.setattr(owner, "read_meeting_preferences", AsyncMock(return_value=state))
    db = AsyncMock(spec=AsyncSession)
    proposal = await prepare_meeting_preferences(
        db, uuid4(), MeetingPreferenceInput(keep_audio_hours=999)
    )
    assert proposal.after["meeting_preferences"] == {
        "stt_engine": "local",
        "language": "fr",
        "auto_email": True,
        "keep_audio_hours": 24,
        "default_template_ref": "builtin:standard",
    }
    db.commit.assert_not_awaited()


def test_read_write_and_effect_registries_cover_both_operations() -> None:
    from src.core.application_tools import APPLICATION_TOOL_NAMES
    from src.domains.agents.application.catalogue_registration import APPLICATION_MANIFESTS
    from src.domains.agents.application.management_editors import MANAGEMENT_EDITORS
    from src.domains.agents.application.native_operations import NATIVE_OPERATIONS

    assert {"get_lia_meeting_preferences_tool", "update_lia_meeting_preferences_tool"} <= set(
        APPLICATION_TOOL_NAMES
    )
    assert {"get_lia_meeting_preferences_tool", "update_lia_meeting_preferences_tool"} <= {
        item.name for item in APPLICATION_MANIFESTS
    }
    assert {"meeting_preferences.read", "meeting_preferences.update"} <= {
        item.operation_id for item in NATIVE_OPERATIONS
    }
    assert "meeting_preferences.update" in MANAGEMENT_EDITORS


async def test_uncertain_commit_never_claims_a_saved_preference() -> None:
    from sqlalchemy.exc import OperationalError

    from src.domains.meetings.preference_commands import _commit_preferences
    from src.domains.users.preference_cas import PreferenceWriteReceipt
    from src.infrastructure.meeting_preferences import MeetingPreferenceCompletionUnknown

    db = AsyncMock(spec=AsyncSession)
    db.commit.side_effect = OperationalError("COMMIT", {}, Exception("lost acknowledgment"))
    receipt = PreferenceWriteReceipt()
    values = MeetingPreferencesUpdate(
        stt_engine="auto", language="auto", auto_email=False, keep_audio_hours=0
    )
    with pytest.raises(MeetingPreferenceCompletionUnknown):
        await _commit_preferences(db, values, receipt, True)
    assert not receipt.committed
    assert not receipt.values


async def test_editor_exposes_request_without_readonly_ceiling_or_state_witness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.domains.agents.application import meeting_preferences as owner
    from src.domains.agents.application.management_editor_inputs import management_editor_request
    from src.domains.agents.application.meeting_preference_schemas import MeetingPreferencePatch

    state = MeetingPreferenceState(
        stt_engine="auto",
        language="fr",
        auto_email=False,
        keep_audio_hours=0,
        default_template_ref=None,
        keep_audio_hours_max=24,
    )
    monkeypatch.setattr(owner, "read_meeting_preferences", AsyncMock(return_value=state))
    proposal = await prepare_meeting_preferences(
        AsyncMock(spec=AsyncSession), uuid4(), MeetingPreferenceInput(default_template_ref=None)
    )
    model, exposed = management_editor_request(MeetingPreferencePatch, proposal.intent)
    assert model is MeetingPreferenceInput and exposed == {"default_template_ref": None}
