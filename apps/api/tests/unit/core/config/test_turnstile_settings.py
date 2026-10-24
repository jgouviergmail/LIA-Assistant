"""The Turnstile bot check refuses to boot half-configured (ADR-364).

A check switched on without its keys would refuse every sign-up and every reset
request (siteverify answers « missing secret ») while letting every sign-in
through unverified — a failure nobody could tell from an attack. The mistake is
moved to boot, where it is made. Off, nothing is required: the keys are the
operator's own widget, never a default.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from src.core.config.security import SecuritySettings
from src.core.constants import (
    TURNSTILE_VERIFY_TIMEOUT_SECONDS_DEFAULT,
    TURNSTILE_VERIFY_TIMEOUT_SECONDS_MAX,
)

pytestmark = pytest.mark.unit


def _settings(**overrides: object) -> SecuritySettings:
    values: dict[str, object] = {
        "secret_key": "test-secret-test-secret-test-secret-test-secret",
        "fernet_key": Fernet.generate_key().decode(),
        **overrides,
    }
    return SecuritySettings(**values)  # type: ignore[arg-type]


def test_the_check_is_off_by_default_and_needs_no_key() -> None:
    settings = _settings()

    assert settings.turnstile_enabled is False
    assert settings.turnstile_site_key == ""
    assert settings.turnstile_secret_key == ""
    assert settings.turnstile_verify_timeout_seconds == TURNSTILE_VERIFY_TIMEOUT_SECONDS_DEFAULT


def test_a_fully_configured_check_boots() -> None:
    settings = _settings(
        turnstile_enabled=True,
        turnstile_site_key="1x00000000000000000000AA",
        turnstile_secret_key="1x0000000000000000000000000000000AA",
    )

    assert settings.turnstile_enabled is True


@pytest.mark.parametrize(
    "missing",
    [
        {"turnstile_secret_key": "1x0000000000000000000000000000000AA"},
        {"turnstile_site_key": "1x00000000000000000000AA"},
        {"turnstile_site_key": "  ", "turnstile_secret_key": "1x0000000000000000000000000000000AA"},
    ],
    ids=["no-site-key", "no-secret-key", "blank-site-key"],
)
def test_a_check_without_both_keys_refuses_to_boot(missing: dict[str, object]) -> None:
    with pytest.raises(ValidationError, match="TURNSTILE_SITE_KEY and TURNSTILE_SECRET_KEY"):
        _settings(turnstile_enabled=True, **missing)


@pytest.mark.parametrize("timeout", [0, TURNSTILE_VERIFY_TIMEOUT_SECONDS_MAX + 1])
def test_the_verify_timeout_is_bounded(timeout: float) -> None:
    with pytest.raises(ValidationError):
        _settings(turnstile_verify_timeout_seconds=timeout)
