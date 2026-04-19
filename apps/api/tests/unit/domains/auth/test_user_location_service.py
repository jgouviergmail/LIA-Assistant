"""Unit tests for domains/auth/user_location_service.py."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.auth.user_location_service import (
    EffectiveLocation,
    LastKnownLocation,
    NoLocationAvailableError,
    UpdateResult,
    UserLocationService,
)


def _make_user(
    *,
    opt_in: bool = True,
    home_lat: float | None = None,
    home_lon: float | None = None,
    last_known_payload: dict | None = None,
    last_known_updated_at: datetime | None = None,
) -> MagicMock:
    """Build a fake User with helpful defaults.

    ``home_lat``/``home_lon`` are encoded into the (fake) encrypted home
    field; ``last_known_payload`` is the decrypted payload we'll return
    via patched ``decrypt_data``.
    """
    user = MagicMock()
    user.id = uuid4()
    user.weather_use_last_known_location = opt_in

    # Home: store raw JSON as "encrypted" — we'll patch decrypt_data
    if home_lat is not None and home_lon is not None:
        user.home_location_encrypted = json.dumps(
            {"address": "Home", "lat": home_lat, "lon": home_lon, "place_id": "p1"}
        )
    else:
        user.home_location_encrypted = None

    if last_known_payload is not None:
        user.last_known_location_encrypted = json.dumps(last_known_payload)
    else:
        user.last_known_location_encrypted = None
    user.last_known_location_updated_at = last_known_updated_at
    return user


def _make_settings(
    *,
    ttl_hours: int = 24,
    min_distance_km: float = 50.0,
) -> SimpleNamespace:
    return SimpleNamespace(
        last_known_location_ttl_hours=ttl_hours,
        last_known_location_min_distance_km=min_distance_km,
    )


def _identity_crypto(target_module: str):
    """Patch encrypt_data/decrypt_data in a module to behave as identity."""
    return (
        patch(f"{target_module}.encrypt_data", side_effect=lambda s: s),
        patch(f"{target_module}.decrypt_data", side_effect=lambda s: s),
    )


@pytest.fixture
def db() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()  # sync method on AsyncSession
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


# =============================================================================
# update_last_known_location
# =============================================================================


@pytest.mark.unit
async def test_update_encrypts_and_persists(db: AsyncMock):
    user = _make_user(opt_in=True)
    module = "src.domains.auth.user_location_service"
    enc_patch, dec_patch = _identity_crypto(module)
    with enc_patch, dec_patch:
        result = await UserLocationService(db).update_last_known_location(
            user, lat=48.85, lon=2.35, accuracy=25.0
        )

    assert result == UpdateResult(updated=True, throttled=False, forbidden=False)
    payload = json.loads(user.last_known_location_encrypted)
    assert payload == {"lat": 48.85, "lon": 2.35, "accuracy": 25.0}
    assert user.last_known_location_updated_at is not None
    db.add.assert_called_once_with(user)
    db.commit.assert_awaited_once()


@pytest.mark.unit
async def test_update_forbidden_when_opt_out(db: AsyncMock):
    user = _make_user(opt_in=False)
    result = await UserLocationService(db).update_last_known_location(
        user, lat=48.85, lon=2.35, accuracy=None
    )

    assert result == UpdateResult(updated=False, throttled=False, forbidden=True)
    assert user.last_known_location_encrypted is None
    db.commit.assert_not_awaited()


@pytest.mark.unit
async def test_update_throttled_when_recent(db: AsyncMock):
    recent = datetime.now(UTC) - timedelta(minutes=5)
    user = _make_user(opt_in=True, last_known_updated_at=recent)
    module = "src.domains.auth.user_location_service"
    enc_patch, dec_patch = _identity_crypto(module)
    with enc_patch, dec_patch:
        result = await UserLocationService(db).update_last_known_location(
            user, lat=48.85, lon=2.35, accuracy=None
        )

    assert result == UpdateResult(updated=False, throttled=True, forbidden=False)
    db.commit.assert_not_awaited()


@pytest.mark.unit
async def test_update_accepts_after_throttle_window(db: AsyncMock):
    old = datetime.now(UTC) - timedelta(minutes=45)
    user = _make_user(opt_in=True, last_known_updated_at=old)
    module = "src.domains.auth.user_location_service"
    enc_patch, dec_patch = _identity_crypto(module)
    with enc_patch, dec_patch:
        result = await UserLocationService(db).update_last_known_location(
            user, lat=48.85, lon=2.35, accuracy=None
        )
    assert result.updated is True
    assert result.throttled is False


@pytest.mark.unit
async def test_update_without_accuracy_omits_field(db: AsyncMock):
    user = _make_user(opt_in=True)
    module = "src.domains.auth.user_location_service"
    enc_patch, dec_patch = _identity_crypto(module)
    with enc_patch, dec_patch:
        await UserLocationService(db).update_last_known_location(
            user, lat=48.85, lon=2.35, accuracy=None
        )
    payload = json.loads(user.last_known_location_encrypted)
    assert "accuracy" not in payload


# =============================================================================
# get_last_known_location
# =============================================================================


@pytest.mark.unit
async def test_get_last_known_returns_fresh_decrypted(db: AsyncMock):
    fresh = datetime.now(UTC) - timedelta(hours=2)
    user = _make_user(
        last_known_payload={"lat": 43.30, "lon": 5.40, "accuracy": 10.0},
        last_known_updated_at=fresh,
    )
    settings_ns = _make_settings(ttl_hours=24)
    module = "src.domains.auth.user_location_service"
    _, dec_patch = _identity_crypto(module)
    with dec_patch, patch(f"{module}.settings", settings_ns):
        result = await UserLocationService(db).get_last_known_location(user)

    assert isinstance(result, LastKnownLocation)
    assert result.lat == 43.30
    assert result.lon == 5.40
    assert result.accuracy == 10.0
    assert result.stale is False


@pytest.mark.unit
async def test_get_last_known_returns_none_when_empty(db: AsyncMock):
    user = _make_user()
    result = await UserLocationService(db).get_last_known_location(user)
    assert result is None


@pytest.mark.unit
async def test_get_last_known_marks_stale_when_past_ttl(db: AsyncMock):
    old = datetime.now(UTC) - timedelta(hours=48)
    user = _make_user(
        last_known_payload={"lat": 43.30, "lon": 5.40, "accuracy": None},
        last_known_updated_at=old,
    )
    settings_ns = _make_settings(ttl_hours=24)
    module = "src.domains.auth.user_location_service"
    _, dec_patch = _identity_crypto(module)
    with dec_patch, patch(f"{module}.settings", settings_ns):
        result = await UserLocationService(db).get_last_known_location(user)

    assert result is not None
    assert result.stale is True


# =============================================================================
# wipe_last_known_location
# =============================================================================


@pytest.mark.unit
async def test_wipe_clears_all_fields(db: AsyncMock):
    user = _make_user(
        last_known_payload={"lat": 43.30, "lon": 5.40},
        last_known_updated_at=datetime.now(UTC),
    )

    await UserLocationService(db).wipe_last_known_location(user)

    assert user.last_known_location_encrypted is None
    assert user.last_known_location_updated_at is None
    db.commit.assert_awaited_once()


@pytest.mark.unit
async def test_wipe_idempotent_when_already_empty(db: AsyncMock):
    user = _make_user()
    await UserLocationService(db).wipe_last_known_location(user)
    db.commit.assert_not_awaited()


# =============================================================================
# get_effective_location_for_proactive
# =============================================================================


@pytest.mark.unit
async def test_effective_prefers_last_known_when_eligible(db: AsyncMock):
    # Lyon home, Paris last-known (~390 km)
    fresh = datetime.now(UTC) - timedelta(hours=2)
    user = _make_user(
        opt_in=True,
        home_lat=45.75,
        home_lon=4.85,
        last_known_payload={"lat": 48.85, "lon": 2.35},
        last_known_updated_at=fresh,
    )
    settings_ns = _make_settings(ttl_hours=24, min_distance_km=50.0)
    module = "src.domains.auth.user_location_service"
    _, dec_patch = _identity_crypto(module)
    with dec_patch, patch(f"{module}.settings", settings_ns):
        result = await UserLocationService(db).get_effective_location_for_proactive(user)

    assert isinstance(result, EffectiveLocation)
    assert result.source == "last_known"
    assert result.lat == 48.85
    assert result.lon == 2.35


@pytest.mark.unit
async def test_effective_falls_back_home_when_opt_out(db: AsyncMock):
    user = _make_user(
        opt_in=False,
        home_lat=45.75,
        home_lon=4.85,
        last_known_payload={"lat": 48.85, "lon": 2.35},
        last_known_updated_at=datetime.now(UTC),
    )
    module = "src.domains.auth.user_location_service"
    _, dec_patch = _identity_crypto(module)
    with dec_patch:
        result = await UserLocationService(db).get_effective_location_for_proactive(user)

    assert result.source == "home"
    assert result.lat == 45.75


@pytest.mark.unit
async def test_effective_falls_back_home_when_stale(db: AsyncMock):
    old = datetime.now(UTC) - timedelta(hours=48)
    user = _make_user(
        opt_in=True,
        home_lat=45.75,
        home_lon=4.85,
        last_known_payload={"lat": 48.85, "lon": 2.35},
        last_known_updated_at=old,
    )
    settings_ns = _make_settings(ttl_hours=24)
    module = "src.domains.auth.user_location_service"
    _, dec_patch = _identity_crypto(module)
    with dec_patch, patch(f"{module}.settings", settings_ns):
        result = await UserLocationService(db).get_effective_location_for_proactive(user)

    assert result.source == "home"


@pytest.mark.unit
async def test_effective_falls_back_home_when_too_close(db: AsyncMock):
    # Same coords as home → distance 0 < min_distance_km
    fresh = datetime.now(UTC) - timedelta(hours=1)
    user = _make_user(
        opt_in=True,
        home_lat=45.75,
        home_lon=4.85,
        last_known_payload={"lat": 45.76, "lon": 4.86},
        last_known_updated_at=fresh,
    )
    settings_ns = _make_settings(ttl_hours=24, min_distance_km=50.0)
    module = "src.domains.auth.user_location_service"
    _, dec_patch = _identity_crypto(module)
    with dec_patch, patch(f"{module}.settings", settings_ns):
        result = await UserLocationService(db).get_effective_location_for_proactive(user)

    assert result.source == "home"


@pytest.mark.unit
async def test_effective_falls_back_home_when_no_last_known(db: AsyncMock):
    user = _make_user(opt_in=True, home_lat=45.75, home_lon=4.85)
    settings_ns = _make_settings()
    module = "src.domains.auth.user_location_service"
    _, dec_patch = _identity_crypto(module)
    with dec_patch, patch(f"{module}.settings", settings_ns):
        result = await UserLocationService(db).get_effective_location_for_proactive(user)
    assert result.source == "home"


@pytest.mark.unit
async def test_effective_raises_when_no_home(db: AsyncMock):
    user = _make_user(opt_in=True)  # no home set
    module = "src.domains.auth.user_location_service"
    _, dec_patch = _identity_crypto(module)
    with dec_patch:
        with pytest.raises(NoLocationAvailableError):
            await UserLocationService(db).get_effective_location_for_proactive(user)
