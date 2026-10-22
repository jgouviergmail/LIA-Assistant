"""Location is coarse and consented; weather never opens an unpermitted location."""

from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.security.utils import encrypt_data
from src.domains.connectors.discussion_weather import WeatherDiscussionSource
from src.domains.shared.discussion_sources import SourceKey
from src.domains.users.discussion_location import LocationDiscussionSource
from src.domains.users.models import User
from tests.integration.domains.proactive_discussions.test_memory_portrait_sources import (
    read_request,
)

pytestmark = pytest.mark.integration


async def test_location_never_exposes_street_or_coordinates_and_does_not_claim_home_is_current(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
) -> None:
    async with AsyncSession(async_engine) as db:
        user = await db.get(User, discussion_owner)
        assert user is not None
        user.home_location_encrypted = encrypt_data(
            '{"address":"42 Secret Street, Fictional City","lat":48.123456,"lon":2.123456}'
        )
        user.use_last_known_location = False
        await db.commit()
    result = await LocationDiscussionSource().read(
        read_request(discussion_owner, SourceKey.LOCATION)
    )
    assert result.total == 1 and result.items[0].assertion == "reported"
    text = result.model_dump_json()
    assert "Secret Street" not in text and "48.123456" not in text and "2.123456" not in text
    assert "configured_home" in text and result.items[0].occurred_at is None


async def test_weather_refuses_before_opening_location_when_location_source_is_off(
    discussion_owner: UUID,
) -> None:
    result = await WeatherDiscussionSource().read(read_request(discussion_owner, SourceKey.WEATHER))
    assert result.status == "disabled" and not result.items and result.reason == "consent"
