"""Preference reads project current allowlisted fields without account secrets."""

from importlib import import_module
from types import ModuleType
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.exceptions import AuthorizationError
from src.domains.agents.application.schemas import PreferenceRead
from src.domains.users.models import User

pytestmark = pytest.mark.unit


def queries() -> ModuleType:
    try:
        return import_module("src.domains.agents.application.queries")
    except ModuleNotFoundError:
        pytest.fail("The current-authority preference query is missing")


async def test_read_returns_the_requested_current_account_value_and_no_secret() -> None:
    module = queries()
    user = User(
        id=uuid4(),
        is_active=True,
        is_superuser=False,
        deleted_at=None,
        font_size=17,
        hashed_password="planted-credential-must-not-leave",
    )
    db = AsyncMock()
    db.scalar.side_effect = ["true", user]
    with patch(
        "src.domains.agents.application.availability.settings.application_tools_enabled", True
    ):
        result = await module.read_preferences(db, user.id, PreferenceRead(fields=["font_size"]))
    assert result.values == {"font_size": 17}
    assert result.scope == "account"
    assert result.observed_at.tzinfo is not None
    assert "planted-credential" not in result.model_dump_json()
    db.commit.assert_not_awaited()


@pytest.mark.parametrize(
    "fields", [["hashed_password"], ["is_superuser"], ["font_size", "font_size"]]
)
def test_unknown_or_duplicate_field_selection_is_refused(fields: list[str]) -> None:
    with pytest.raises(ValidationError):
        PreferenceRead(fields=fields)


async def test_inactive_actor_cannot_read_a_previously_selected_projection() -> None:
    module = queries()
    user = User(id=uuid4(), is_active=False, is_superuser=False, deleted_at=None, font_size=17)
    db = AsyncMock()
    db.scalar.side_effect = ["true", user]
    with (
        patch(
            "src.domains.agents.application.availability.settings.application_tools_enabled", True
        ),
        pytest.raises(AuthorizationError),
    ):
        await module.read_preferences(db, user.id, PreferenceRead(fields=["font_size"]))
    db.commit.assert_not_awaited()
