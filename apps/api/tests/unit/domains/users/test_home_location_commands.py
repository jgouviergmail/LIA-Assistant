"""Home writes preserve approval snapshots and clear both encrypted stores atomically."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.core.security.utils import encrypt_data
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.users.schemas import HomeLocationData, HomeLocationUpdate
from src.domains.users.service import UserService

pytestmark = pytest.mark.unit


def actor() -> User:
    return User(
        id=uuid4(),
        is_active=True,
        deleted_at=None,
        home_location_encrypted=encrypt_data(
            HomeLocationData(
                address="Original address",
                lat=48,
                lon=2,
            ).model_dump_json()
        ),
        last_known_location_encrypted=encrypt_data('{"lat":49,"lon":3,"accuracy":10}'),
        last_known_location_updated_at=datetime.now(UTC),
    )


async def test_clear_uses_one_commit_for_home_and_remembered_position() -> None:
    user = actor()
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = user
    db.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=user))
    saved = []

    async def commit() -> None:
        saved.append(
            (
                user.home_location_encrypted,
                user.last_known_location_encrypted,
                user.last_known_location_updated_at,
            )
        )

    db.commit.side_effect = commit
    assert await UserService(db).clear_home_location(user.id)
    assert saved == [(None, None, None)]


async def test_clear_repairs_orphan_remembered_position_even_without_home() -> None:
    user = actor()
    user.home_location_encrypted = None
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = user
    db.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=user))
    assert not await UserService(db).clear_home_location(user.id)
    assert user.last_known_location_encrypted is None
    db.commit.assert_awaited_once()


async def test_confirmed_clear_refuses_a_newer_location() -> None:
    user = actor()
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = user
    receipt = PreferenceWriteReceipt()
    with pytest.raises(ResourceConflictError):
        await UserService(db).clear_home_location(
            user.id,
            expected_locations={"home_location": None, "last_known_location": None},
            receipt=receipt,
        )
    assert not receipt.committed
    assert user.home_location_encrypted is not None
    db.commit.assert_not_awaited()


async def test_confirmed_set_never_geocodes_its_frozen_coordinates(monkeypatch) -> None:
    user = actor()
    db = AsyncMock(spec=AsyncSession)
    db.scalar.return_value = user
    geocode = AsyncMock(side_effect=AssertionError("approved resolution must not run again"))
    monkeypatch.setattr("src.domains.users.geocoding.resolve_home_coordinates", geocode)
    monkeypatch.setattr(
        "src.domains.connectors.service.ConnectorService.is_places_enabled",
        AsyncMock(return_value=True),
    )
    receipt = PreferenceWriteReceipt()
    result = await UserService(db).set_home_location(
        user.id,
        HomeLocationUpdate(address="New address", lat=0, lon=12),
        resolved=True,
        expected_locations={
            "home_location": {
                "address": "Original address",
                "lat": 48.0,
                "lon": 2.0,
                "place_id": None,
            }
        },
        receipt=receipt,
    )
    assert result.lat == 0 and result.lon == 12
    assert receipt.committed
    geocode.assert_not_awaited()
    db.commit.assert_awaited_once()


async def test_corrupt_stored_home_is_not_reported_as_an_empty_native_setting() -> None:
    from src.domains.users.home_location_commands import read_home_location

    user = actor()
    user.home_location_encrypted = "invalid-ciphertext"
    with pytest.raises(ValueError, match="unavailable"):
        read_home_location(user)
