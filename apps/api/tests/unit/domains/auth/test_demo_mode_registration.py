"""Visitor accounts on a public demonstrator instance.

The instance runs the REAL registration journey — create, receive the mail,
click the link — because reproducing "close to the real thing" is the point
of the demonstrator, and because an email step is what stops scripted signups.
Exactly two things differ, both gated on ``DEMO_MODE_ENABLED``:

1. verifying the mail ACTIVATES the account, instead of queuing it for an
   administrator who is not watching a demo at 2am;
2. registration REQUIRES accepting the terms, and records what was accepted
   and when (a claim with no version cannot be defended later).

Everything else — password rules, rate limit, provisioning, usage limits —
stays the production path. A demo that runs different code proves nothing
about production.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.exceptions import BaseAPIException
from src.domains.auth.schemas import UserRegisterRequest

pytestmark = pytest.mark.unit


def _provisioning() -> object:
    """Patch the cross-domain provisioning so its coroutine is awaitable."""
    service = MagicMock()
    service.return_value.provision_new_user = AsyncMock()
    return patch(
        "src.domains.users.account_provisioning_service.AccountProvisioningService",
        service,
    )


@contextmanager
def _registration_context(*, demo: bool) -> Iterator[None]:
    """Everything ``register`` touches beyond its own logic, neutralized."""
    from src.domains.auth.service import AuthService

    with (
        patch("src.domains.auth.service.settings", _settings(demo=demo)),
        _provisioning(),
        patch.object(AuthService, "_send_verification_email", new_callable=AsyncMock),
        patch("src.domains.auth.schemas.UserResponse.model_validate", lambda value: value),
    ):
        yield


def _settings(*, demo: bool, terms_version: str = "2026-08-06") -> MagicMock:
    fake = MagicMock()
    fake.demo_mode_enabled = demo
    fake.demo_terms_version = terms_version
    fake.default_language = "fr"
    # Explicitly unlimited: this file is about the terms and the activation,
    # not about the daily signup ceiling, which has its own suite
    # (test_demo_signup_ceiling.py). Left as a MagicMock it would look like a
    # configured limit and send the ceiling to query a mock database.
    fake.demo_daily_signup_limit = None
    return fake


def _request(**overrides: object) -> UserRegisterRequest:
    payload: dict[str, object] = {
        "email": "visitor@example.com",
        "password": "Str0ng!Passw0rd#2026",
        "full_name": "Visitor",
    }
    payload.update(overrides)
    return UserRegisterRequest(**payload)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Terms acceptance
# ---------------------------------------------------------------------------


def test_the_registration_schema_carries_the_terms_acceptance() -> None:
    assert _request().terms_accepted is False
    assert _request(terms_accepted=True).terms_accepted is True


async def test_demo_mode_refuses_a_registration_without_accepted_terms() -> None:
    from src.domains.auth.service import AuthService

    service = AuthService(MagicMock())
    service.repository = MagicMock()
    service.repository.get_by_email = AsyncMock(return_value=None)

    with patch("src.domains.auth.service.settings", _settings(demo=True)):
        with pytest.raises(BaseAPIException) as excinfo:
            await service.register(_request(terms_accepted=False))
    assert excinfo.value.status_code == 400


async def test_outside_demo_mode_the_terms_flag_is_not_required() -> None:
    """The real instance keeps its own onboarding rules — unchanged."""
    service = _service_with_creation()
    with _registration_context(demo=False):
        await service.register(_request(terms_accepted=False))
    created = service.repository.create.await_args.args[0]
    assert created["email"] == "visitor@example.com"


async def test_accepting_the_terms_records_the_instant_and_the_version() -> None:
    service = _service_with_creation()
    with _registration_context(demo=True):
        await service.register(_request(terms_accepted=True))

    created = service.repository.create.await_args.args[0]
    # Without the version, nobody can say later WHICH terms were accepted.
    assert created["terms_version"] == "2026-08-06"
    assert isinstance(created["terms_accepted_at"], datetime)
    assert created["terms_accepted_at"].tzinfo is not None


async def test_the_account_is_still_created_inactive_and_unverified() -> None:
    service = _service_with_creation()
    with _registration_context(demo=True):
        await service.register(_request(terms_accepted=True))

    created = service.repository.create.await_args.args[0]
    # Demo mode does not skip the mail: an unverified address would let a
    # script open accounts in a loop.
    assert created["is_active"] is False
    assert created["is_verified"] is False


# ---------------------------------------------------------------------------
# Activation on verification
# ---------------------------------------------------------------------------


def _service_with_creation() -> object:
    from src.domains.auth.service import AuthService

    service = AuthService(MagicMock())
    service.db = MagicMock()
    service.db.commit = AsyncMock()
    service.repository = MagicMock()
    service.repository.get_by_email = AsyncMock(return_value=None)
    service.repository.create = AsyncMock(
        return_value=MagicMock(id=uuid4(), email="visitor@example.com", language="fr")
    )
    return service


def _verifiable_user() -> MagicMock:
    return MagicMock(
        id=uuid4(),
        email="visitor@example.com",
        full_name="Visitor",
        language="fr",
        is_verified=False,
        is_active=False,
    )


async def _verify(demo: bool) -> MagicMock:
    from src.domains.auth.service import AuthService

    user = _verifiable_user()
    service = AuthService(MagicMock())
    service.db = MagicMock()
    service.db.commit = AsyncMock()
    service.repository = MagicMock()
    service.repository.get_by_email = AsyncMock(return_value=user)

    with (
        patch("src.domains.auth.service.settings", _settings(demo=demo)),
        patch(
            "src.domains.auth.service.verify_single_use_token",
            AsyncMock(return_value=({"sub": user.email}, None)),
        ),
        patch("src.domains.auth.schemas.UserResponse.model_validate", lambda value: value),
        patch.object(
            AuthService, "_notify_admins_of_new_registration", new_callable=AsyncMock
        ) as notify,
        patch.object(
            AuthService, "_send_pending_activation_notification", new_callable=AsyncMock
        ) as pending,
    ):
        await service.verify_email("token")
    user._notify = notify
    user._pending = pending
    return user


async def test_demo_mode_activates_the_account_on_verification() -> None:
    user = await _verify(demo=True)
    assert user.is_verified is True
    # Nobody is watching a demo at 2am: waiting for an admin would make the
    # whole journey a dead end.
    assert user.is_active is True


async def test_demo_mode_does_not_pester_admins_for_every_visitor() -> None:
    user = await _verify(demo=True)
    user._notify.assert_not_awaited()
    # And the visitor is not told to wait for an activation that already
    # happened.
    user._pending.assert_not_awaited()


async def test_the_real_instance_keeps_admin_approval() -> None:
    user = await _verify(demo=False)
    assert user.is_verified is True
    # Unchanged production behaviour: verified, still inactive, admin notified.
    assert user.is_active is False
    user._notify.assert_awaited_once()
    user._pending.assert_awaited_once()


def test_demo_mode_is_off_by_default() -> None:
    from src.core.config.demo import DemoSettings

    fresh = DemoSettings()
    # A deployment property, never a runtime toggle: an instance either IS a
    # demonstrator or it is not. Defaulting it on would auto-approve accounts
    # on a private instance.
    assert fresh.demo_mode_enabled is False


def test_the_terms_version_is_configurable_and_non_empty_by_default() -> None:
    from src.core.config.demo import DemoSettings

    assert DemoSettings().demo_terms_version
