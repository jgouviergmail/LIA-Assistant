"""The display-mode endpoint accepts each supported preference and rejects unknown values."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ValidationError
from src.domains.auth.router import update_display_mode_preference
from src.domains.auth.schemas import DisplayModePreferenceRequest
from src.domains.users.models import User

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("mode", ["cards", "html", "html_cards", "markdown"])
async def test_supported_display_preference_is_persisted_and_returned(mode: str) -> None:
    user = User(id=uuid4(), response_display_mode="cards")
    db = MagicMock(spec=AsyncSession)

    response = await update_display_mode_preference(
        DisplayModePreferenceRequest(response_display_mode=mode), user, db
    )

    assert user.response_display_mode == mode
    assert response.response_display_mode == mode
    assert response.model_dump()["response_display_mode"] == mode
    db.add.assert_called_once_with(user)
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(user)


@pytest.mark.parametrize("mode", ["", "HTML_CARDS", "unknown"])
async def test_unknown_display_preference_is_rejected_without_persisting(mode: str) -> None:
    user = User(id=uuid4(), response_display_mode="cards")
    db = MagicMock(spec=AsyncSession)

    with pytest.raises(ValidationError, match="Invalid display mode"):
        await update_display_mode_preference(
            DisplayModePreferenceRequest(response_display_mode=mode), user, db
        )

    assert user.response_display_mode == "cards"
    db.add.assert_not_called()
    db.commit.assert_not_awaited()
