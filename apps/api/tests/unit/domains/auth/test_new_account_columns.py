"""What a brand-new account starts with, on the sign-up doors (owner decision 2026-10-22).

A new account opens on a dashboard showing the weather card alone and with
occasional exchanges, whatever the operator's default says for the accounts
that never chose (ADR-311). Three doors create an account — an e-mail
registration and a first Google sign-in, pinned here, and the installer's
first account, pinned beside the installer's contract — and all of them must
hand the row the same columns: a default one door forgets is a default some
accounts never get.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.config import settings
from src.core.exchange_rhythm import ExchangeRhythm, effective_exchange_rhythm
from src.domains.auth.new_account_columns import new_account_columns
from src.domains.auth.schemas import UserRegisterRequest
from src.domains.briefing.preferences import sanitize_briefing_preferences

pytestmark = pytest.mark.unit

#: Every card but the weather — written by hand, never derived from the code under test.
_HIDDEN_ON_A_NEW_ACCOUNT = {
    "agenda",
    "mails",
    "birthdays",
    "reminders",
    "health",
    "sms",
    "for_you",
    "tasks",
    "documents",
    "workboard",
}


@pytest.fixture(autouse=True)
def _instance_serves_the_weather(monkeypatch: pytest.MonkeyPatch) -> None:
    """The platform key: Google Weather and the address geocoding both need it (ADR-307)."""
    monkeypatch.setattr(settings, "google_api_key", "platform-key")


def test_a_new_account_sees_the_weather_card_alone() -> None:
    grid = sanitize_briefing_preferences(new_account_columns()["briefing_preferences"])

    assert set(grid.hidden) == _HIDDEN_ON_A_NEW_ACCOUNT
    # The order is still the canonical one: the visible card opens the grid.
    assert grid.order[0] == "weather"


def test_a_deployment_that_cannot_serve_the_weather_starts_with_every_card(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No platform key (the public demonstrator, measured 2026-10-22): the weather
    # card could never be drawn, and a grid holding it alone would be empty.
    monkeypatch.setattr(settings, "google_api_key", "")

    grid = sanitize_briefing_preferences(new_account_columns()["briefing_preferences"])

    assert grid.hidden == []


def test_a_new_account_exchanges_occasionally_whatever_the_operator_default() -> None:
    stored = new_account_columns()["exchange_rhythm"]

    # Measured 2026-10-22: dev and production both set
    # REACT_CROSS_TURN_CACHE_ENABLED=true, so an account that never chose
    # follows it into frequent exchanges.
    with patch("src.core.exchange_rhythm.settings") as fake:
        fake.react_cross_turn_cache_enabled = True
        assert effective_exchange_rhythm(stored) is ExchangeRhythm.OCCASIONAL


def _settings() -> MagicMock:
    fake = MagicMock()
    fake.demo_mode_enabled = False
    fake.demo_daily_signup_limit = None
    fake.default_language = "fr"
    return fake


def _service() -> object:
    from src.domains.auth.service import AuthService

    service = AuthService(MagicMock())
    service.db = MagicMock()
    service.db.commit = AsyncMock()
    service.repository = MagicMock()
    service.repository.get_by_email = AsyncMock(return_value=None)
    service.repository.get_by_oauth_provider = AsyncMock(return_value=None)
    service.repository.create = AsyncMock(
        return_value=MagicMock(id=uuid4(), email="new@example.com", language="fr")
    )
    return service


def _provisioning() -> object:
    provisioning = MagicMock()
    provisioning.return_value.provision_new_user = AsyncMock()
    return patch(
        "src.domains.users.account_provisioning_service.AccountProvisioningService",
        provisioning,
    )


def _assert_new_account_columns(created: dict[str, object]) -> None:
    assert created["exchange_rhythm"] == "occasional"
    grid = created["briefing_preferences"]
    assert isinstance(grid, dict)
    assert set(grid["hidden"]) == _HIDDEN_ON_A_NEW_ACCOUNT


async def test_an_email_registration_creates_the_new_account_columns() -> None:
    from src.domains.auth.service import AuthService

    service = _service()
    request = UserRegisterRequest(
        email="new@example.com", password="Str0ng!Passw0rd#2026", full_name="New"
    )
    with (
        patch("src.domains.auth.service.settings", _settings()),
        _provisioning(),
        patch.object(AuthService, "_send_verification_email", new_callable=AsyncMock),
        patch("src.domains.auth.schemas.UserResponse.model_validate", lambda value: value),
    ):
        await service.register(request)

    _assert_new_account_columns(service.repository.create.await_args.args[0])


async def test_a_first_google_sign_in_creates_the_new_account_columns() -> None:
    from src.domains.auth.service import AuthService

    service = _service()
    with (
        _provisioning(),
        patch.object(AuthService, "_notify_admins_of_new_registration", new_callable=AsyncMock),
        patch.object(AuthService, "_send_pending_activation_notification", new_callable=AsyncMock),
    ):
        await service._find_or_create_google_user(
            {"id": "google-new", "email": "new@example.com", "name": "New"}
        )

    _assert_new_account_columns(service.repository.create.await_args.args[0])
