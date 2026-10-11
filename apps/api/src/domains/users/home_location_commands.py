"""Home-location owner: prepare outside locks, compare and write under one lock."""

from collections.abc import Mapping
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError, raise_permission_denied, raise_user_not_found
from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.users.repository import UserRepository
from src.domains.users.schemas import HomeLocationData, HomeLocationResponse, HomeLocationUpdate


class SavedCoordinates(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    accuracy: float | None = Field(default=None, ge=0)


def read_home_location(user: User) -> HomeLocationData | None:
    if not user.home_location_encrypted:
        return None
    try:
        return HomeLocationData.model_validate_json(decrypt_data(user.home_location_encrypted))
    except ValueError:
        raise ValueError("Saved home location is unavailable") from None


def location_values(user: User, fields: set[str]) -> dict[str, JsonValue]:
    values: dict[str, JsonValue] = {}
    if not fields <= {"home_location", "last_known_location"}:
        raise ValueError("Unknown location field")
    if "home_location" in fields:
        home = read_home_location(user)
        values["home_location"] = home.model_dump(mode="json") if home else None
    if "last_known_location" in fields:
        if user.last_known_location_encrypted is None:
            if user.last_known_location_updated_at is not None:
                raise ValueError("Saved last-known location is unavailable")
            values["last_known_location"] = None
        else:
            if user.last_known_location_updated_at is None:
                raise ValueError("Saved last-known location is unavailable")
            try:
                coordinates = SavedCoordinates.model_validate_json(
                    decrypt_data(user.last_known_location_encrypted)
                )
            except ValueError:
                raise ValueError("Saved last-known location is unavailable") from None
            values["last_known_location"] = {
                **coordinates.model_dump(mode="json"),
                "updated_at": user.last_known_location_updated_at.isoformat(),
            }
    return values


async def require_places(db: AsyncSession, user_id: UUID) -> None:
    from src.domains.connectors.service import ConnectorService

    if not await ConnectorService(db).is_places_enabled(user_id):
        raise_permission_denied(
            action="set home location",
            resource_type="home_location",
            details="Google Places connector must be enabled to set home location",
        )


async def resolve_home_location(
    db: AsyncSession, user_id: UUID, location: HomeLocationUpdate
) -> HomeLocationData:
    from src.domains.users.geocoding import resolve_home_coordinates

    user = await db.scalar(
        select(User)
        .where(
            User.id == user_id,
            User.is_active,
            User.deleted_at.is_(None),
        )
        .execution_options(populate_existing=True)
    )
    if user is None:
        raise_user_not_found(user_id)
    await require_places(db, user_id)
    lat, lon, place_id = await resolve_home_coordinates(
        user_id=user_id, user=user, location=location
    )
    return HomeLocationData(address=location.address, lat=lat, lon=lon, place_id=place_id)


def _check_expected(user: User, expected: Mapping[str, JsonValue], fields: set[str]) -> None:
    if set(expected) != fields:
        raise ValueError("Expected state must cover exactly the affected locations")
    if location_values(user, fields) != dict(expected):
        raise ResourceConflictError("locations", detail={"error_code": "STALE_STATE"})


async def set_home_location(
    db: AsyncSession,
    user_id: UUID,
    location: HomeLocationUpdate,
    *,
    resolved: bool = False,
    expected: Mapping[str, JsonValue] | None = None,
    receipt: PreferenceWriteReceipt | None = None,
) -> HomeLocationResponse:
    # Network work completes before the fresh write lock. Approval uses the exact resolution.
    data = (
        HomeLocationData.model_validate(location.model_dump())
        if resolved
        else await resolve_home_location(db, user_id, location)
    )
    await require_places(db, user_id)
    user = await UserRepository(db).get_by_id_for_preference_update(user_id)
    if user is None:
        raise_user_not_found(user_id)
    if expected is not None:
        _check_expected(user, expected, {"home_location"})
        if location_values(user, {"home_location"}) == {
            "home_location": data.model_dump(mode="json")
        }:
            if receipt is not None:
                receipt.committed = receipt.no_op = True
            return HomeLocationResponse.model_validate(data.model_dump())
    user.home_location_encrypted = encrypt_data(data.model_dump_json())
    await db.commit()
    if receipt is not None:
        receipt.committed = True
    return HomeLocationResponse.model_validate(data.model_dump())


async def clear_home_location(
    db: AsyncSession,
    user_id: UUID,
    *,
    expected: Mapping[str, JsonValue] | None = None,
    receipt: PreferenceWriteReceipt | None = None,
) -> bool:
    user = await UserRepository(db).get_by_id_for_preference_update(user_id)
    if user is None:
        raise_user_not_found(user_id)
    if expected is not None:
        _check_expected(user, expected, {"home_location", "last_known_location"})
    had_home = user.home_location_encrypted is not None
    if (
        not had_home
        and user.last_known_location_encrypted is None
        and user.last_known_location_updated_at is None
    ):
        if receipt is not None:
            receipt.committed = receipt.no_op = True
        return False
    user.home_location_encrypted = None
    user.last_known_location_encrypted = None
    user.last_known_location_updated_at = None
    await db.commit()
    if receipt is not None:
        receipt.committed = True
    return had_home
