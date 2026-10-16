"""Selection must agree with the public active catalogue, before any write."""

from unittest.mock import AsyncMock, MagicMock, patch
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


@pytest.mark.parametrize("explicit_default", [False, True])
async def test_personality_write_commits_psyche_sync_even_for_default(
    explicit_default: bool,
) -> None:
    """The preference response must only leave after its trait sync commits."""
    actor = User(
        id=uuid4(),
        personality_id=uuid4(),
        is_active=True,
        deleted_at=None,
        timezone="Europe/Paris",
        language="fr",
    )
    choice = None if explicit_default else uuid4()
    db = AsyncMock()
    db.scalar.return_value = choice
    service = UserService(db)
    service.repository.get_by_id = AsyncMock(return_value=actor)
    service.repository.update = AsyncMock(return_value=actor)
    service._build_user_profile = MagicMock()
    events: list[str] = []

    async def commit() -> None:
        events.append("commit")

    async def sync(user_id: object) -> None:
        assert user_id == actor.id
        events.append("sync")

    db.commit.side_effect = commit
    with patch(
        "src.domains.psyche.service.PsycheService.sync_traits_from_personality",
        new=AsyncMock(side_effect=sync),
    ) as synchronize:
        await service.update_user(actor.id, UserUpdate(personality_id=choice))

    synchronize.assert_awaited_once_with(actor.id)
    assert events == ["commit", "sync", "commit"]


async def test_other_profile_write_does_not_sync_personality_traits() -> None:
    actor = User(
        id=uuid4(),
        personality_id=uuid4(),
        is_active=True,
        deleted_at=None,
        timezone="Europe/Paris",
        language="fr",
    )
    db = AsyncMock()
    service = UserService(db)
    service.repository.get_by_id = AsyncMock(return_value=actor)
    service.repository.update = AsyncMock(return_value=actor)
    service._build_user_profile = MagicMock()
    with patch(
        "src.domains.psyche.service.PsycheService.sync_traits_from_personality",
        new=AsyncMock(),
    ) as synchronize:
        await service.update_user(actor.id, UserUpdate(full_name="Another name"))

    synchronize.assert_not_awaited()
    db.commit.assert_awaited_once()
