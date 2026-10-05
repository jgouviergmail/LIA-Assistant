"""Reject ambiguous commands before a paid session or preference write."""

import pytest
from pydantic import ValidationError

from src.domains.avatars.schemas import AvatarSessionRequest, AvatarSettingsRequest

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {"enabled": "true"},
        {"enabled": None},
        {"enabled": True, "api_key": "never-accepted"},
        {"enabled": True, "face_id": "bad-id"},
    ],
)
def test_settings_refuse_ambiguous_or_secret_fields(payload):
    with pytest.raises(ValidationError):
        AvatarSettingsRequest.model_validate(payload)


def test_radio_cannot_mint_an_avatar_session():
    with pytest.raises(ValidationError):
        AvatarSessionRequest.model_validate(
            {"owner_id": "00000000-0000-4000-8000-000000000001", "source": "radio"}
        )
