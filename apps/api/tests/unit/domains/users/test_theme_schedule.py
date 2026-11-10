"""Strict profile contract for the account's civil-time display schedule."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ValidationError as InvalidInput
from src.domains.users.models import User
from src.domains.users.schemas import UserUpdate
from src.domains.users.service import UserService

pytestmark = pytest.mark.unit


def test_automatic_mode_and_custom_hours_survive_a_patch() -> None:
    """An overnight light interval is legal, and omitted preferences stay absent."""
    payload = {"theme": "auto", "theme_light_start_minute": 1200, "theme_dark_start_minute": 420}
    assert UserUpdate.model_validate(payload).model_dump(exclude_unset=True) == payload


@pytest.mark.parametrize("field", ["theme_light_start_minute", "theme_dark_start_minute"])
@pytest.mark.parametrize("value", [None, True, "420", 420.5, -1, 1440])
def test_refuses_invalid_civil_minute(field: str, value: object) -> None:
    """Malformed clients cannot store an ambiguous or coerced schedule."""
    with pytest.raises(ValidationError):
        UserUpdate.model_validate({field: value})


def test_refuses_equal_boundaries() -> None:
    """Equal boundaries mean neither a clear day nor a clear night."""
    with pytest.raises(ValidationError):
        UserUpdate.model_validate({"theme_light_start_minute": 420, "theme_dark_start_minute": 420})


def test_partial_patch_preserves_omission() -> None:
    """The service must merge the other boundary from the locked account."""
    assert UserUpdate.model_validate({"theme_dark_start_minute": 420}).model_dump(
        exclude_unset=True
    ) == {"theme_dark_start_minute": 420}


async def test_partial_patch_checks_the_locked_current_boundary_before_writing() -> None:
    """Two independently valid partial writes cannot create an empty interval."""
    db = AsyncMock(spec=AsyncSession)
    service = UserService(db)
    owner = User(id=uuid4(), theme_light_start_minute=420, theme_dark_start_minute=1200)
    service.repository.get_by_id = AsyncMock(return_value=owner)
    service.repository.get_by_id_for_preference_update = AsyncMock(return_value=owner)
    service.repository.update = AsyncMock(return_value=owner)
    with pytest.raises(InvalidInput):
        await service.update_user(owner.id, UserUpdate(theme_dark_start_minute=420))
    service.repository.get_by_id_for_preference_update.assert_awaited_once_with(owner.id)
    service.repository.update.assert_not_awaited()
    db.commit.assert_not_awaited()
