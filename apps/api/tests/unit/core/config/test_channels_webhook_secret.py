"""Webhook mode must not start without a real secret (SEC-024).

``TELEGRAM_WEBHOOK_URL`` set means Telegram POSTs updates to a public URL, and
the ``X-Telegram-Bot-Api-Secret-Token`` header is the only thing separating
Telegram from anyone else who found it. Since the handler now refuses requests
when no secret is configured, a missing secret is no longer a hole — it is a
silent outage (every update dropped, the channel simply looking "quiet"). Boot
validation surfaces that immediately.

Length is deliberately not a boot condition: an existing deployment may carry a
shorter secret, and refusing to start would turn hardening into downtime.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.core.config.channels import ChannelsSettings

_REAL_SECRET = "b8f1d2c3a49e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8"
_WEBHOOK_URL = "https://lia.example.com/api/v1/channels/telegram/webhook"


def _settings(**overrides: object) -> ChannelsSettings:
    """Build ChannelsSettings without reading the developer's .env file.

    ``_env_file=None`` keeps the case under test isolated: otherwise a local
    ``.env`` carrying a real secret would mask the missing-secret scenarios.
    """
    return ChannelsSettings(_env_file=None, **overrides)  # type: ignore[call-arg]


class TestWebhookModeRequiresSecret:
    """Boot must fail when webhook mode is active without a usable secret."""

    @pytest.mark.parametrize(
        "secret",
        [None, "", "   ", "CHANGE_ME_WEBHOOK_SECRET"],
        ids=["absent", "empty", "blank", "placeholder"],
    )
    def test_webhook_mode_without_real_secret_is_refused(self, secret):
        """Absent, blank or template-placeholder secrets all refuse to boot."""
        with pytest.raises(ValidationError, match="TELEGRAM_WEBHOOK_SECRET"):
            _settings(
                channels_enabled=True,
                telegram_webhook_url=_WEBHOOK_URL,
                telegram_webhook_secret=secret,
            )

    def test_webhook_mode_with_real_secret_boots(self):
        """Control: a real secret boots — the guard is not blocking everything."""
        settings = _settings(
            channels_enabled=True,
            telegram_webhook_url=_WEBHOOK_URL,
            telegram_webhook_secret=_REAL_SECRET,
        )
        assert settings.telegram_webhook_secret == _REAL_SECRET

    def test_short_secret_still_boots(self):
        """A weak-but-real secret must NOT block startup.

        Strength is an operational recommendation. Making length a boot
        condition would take down a deployment whose secret predates this
        check — hardening must not become an outage.
        """
        settings = _settings(
            channels_enabled=True,
            telegram_webhook_url=_WEBHOOK_URL,
            telegram_webhook_secret="short",
        )
        assert settings.telegram_webhook_secret == "short"


class TestNonWebhookModesAreUnaffected:
    """Polling and disabled-channel deployments keep starting as before."""

    def test_polling_mode_needs_no_secret(self):
        """No webhook URL → long polling → Telegram never calls the endpoint."""
        settings = _settings(channels_enabled=True, telegram_webhook_url=None)
        assert settings.telegram_webhook_secret is None

    def test_channels_disabled_needs_no_secret(self):
        """Channels off → the route is not even mounted."""
        settings = _settings(
            channels_enabled=False,
            telegram_webhook_url=_WEBHOOK_URL,
            telegram_webhook_secret=None,
        )
        assert settings.channels_enabled is False

    def test_default_settings_boot(self):
        """`.env.min.prod` ships neither key: defaults must remain bootable.

        `channels_enabled` defaults to True while `telegram_webhook_url` is
        None, i.e. polling — the guard must not fire on that combination, or the
        minimal production template would stop starting.
        """
        settings = _settings()
        assert settings.telegram_webhook_url is None
