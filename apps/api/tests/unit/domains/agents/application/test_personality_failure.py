"""A failed dependency must not be silently mistaken for the source default."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import OperationalError

from src.core.exceptions import ResourceNotFoundError
from src.domains.personalities.service import PersonalityService

pytestmark = pytest.mark.unit


async def test_personality_database_failure_is_not_a_missing_choice() -> None:
    source = PersonalityService(AsyncMock())
    failure = OperationalError("read", {}, RuntimeError("unavailable"))
    source.get_by_id = AsyncMock(side_effect=failure)
    source.get_default = AsyncMock(return_value=None)
    with pytest.raises(OperationalError):
        await source.get_user_personality(uuid4(), "fr")
    source.get_default.assert_not_awaited()


async def test_removed_choice_keeps_the_source_default_fallback() -> None:
    source = PersonalityService(AsyncMock())
    source.get_by_id = AsyncMock(side_effect=ResourceNotFoundError("personality", uuid4()))
    source.get_default = AsyncMock(return_value=None)
    assert await source.get_user_personality(uuid4(), "fr") is None
    source.get_default.assert_awaited_once()
