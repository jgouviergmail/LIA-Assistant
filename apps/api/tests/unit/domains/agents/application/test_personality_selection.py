"""Selection must agree with the public active catalogue, before any write."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.exceptions import ResourceNotFoundError
from src.domains.users.models import User
from src.domains.users.schemas import UserUpdate
from src.domains.users.service import UserService

pytestmark = pytest.mark.unit


async def test_unknown_or_inactive_personality_is_not_a_valid_preference() -> None:
    actor = User(id=uuid4(), personality_id=None, is_active=True, deleted_at=None)
    db = AsyncMock()
    db.scalar.side_effect = [actor, None]
    service = UserService(db)
    service.repository.update = AsyncMock()
    with pytest.raises(ResourceNotFoundError):
        await service.update_user(
            actor.id,
            UserUpdate(personality_id=uuid4()),
            expected_preferences={"personality_id": None},
        )
    service.repository.update.assert_not_awaited()
    db.commit.assert_not_awaited()
