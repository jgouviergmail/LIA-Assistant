"""The shared UI service checks the approved snapshot at its write boundary."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.core.exceptions import ResourceConflictError
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.users.schemas import UserUpdate
from src.domains.users.service import UserService

pytestmark = pytest.mark.unit


async def test_already_applied_preferences_are_verified_without_a_new_write() -> None:
    user = User(id=uuid4(), font_size=17, is_active=True, deleted_at=None)
    db = AsyncMock()
    db.scalar.return_value = user
    service = UserService(db)
    service.repository.update = AsyncMock()
    receipt = PreferenceWriteReceipt()
    with patch.object(service, "_build_user_profile") as project:
        await service.update_user(
            user.id,
            UserUpdate(font_size=17),
            expected_preferences={"font_size": 17},
            receipt=receipt,
        )
    service.repository.update.assert_not_awaited()
    db.commit.assert_not_awaited()
    project.assert_called_once_with(user)
    assert receipt.committed and receipt.no_op


async def test_changed_preference_cannot_be_overwritten_by_an_old_approval() -> None:
    user = User(id=uuid4(), font_size=18, is_active=True, deleted_at=None)
    db = AsyncMock()
    db.scalar.return_value = user
    service = UserService(db)
    service.repository.update = AsyncMock()
    with pytest.raises(ResourceConflictError):
        await service.update_user(
            user.id, UserUpdate(font_size=17), expected_preferences={"font_size": 16}
        )
    service.repository.update.assert_not_awaited()
    db.commit.assert_not_awaited()


async def test_partial_expected_snapshot_cannot_authorize_additional_fields() -> None:
    user = User(id=uuid4(), font_size=16, is_active=True, deleted_at=None)
    db = AsyncMock()
    db.scalar.return_value = user
    service = UserService(db)
    service.repository.update = AsyncMock()
    with pytest.raises(ValueError):
        await service.update_user(
            user.id, UserUpdate(font_size=17, theme="dark"), expected_preferences={"font_size": 16}
        )
    service.repository.update.assert_not_awaited()
    db.commit.assert_not_awaited()
