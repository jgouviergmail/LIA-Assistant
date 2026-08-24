"""
The relay refuses to boot half-configured.

A relay missing its signing key still accepts registrations and still answers
wake calls — and fails every single push. From a self-hoster's side that reads
as "the relay is down"; from a user's side as "notifications do not work".
Neither can diagnose it, and nothing anywhere says the operator forgot an
environment variable. So the failure is moved to boot, where the mistake is.

The other property pinned here is the absence of a default relay URL. A default
would enrol every self-hosted deployment into telling a third party when its
users are woken, by inheritance rather than by decision.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from src.core.config.push_relay import PushRelaySettings

pytestmark = pytest.mark.unit


def _complete(**overrides: object) -> dict[str, object]:
    return {
        "push_relay_enabled": True,
        "push_relay_seal_key": Fernet.generate_key().decode(),
        "apns_key_path": "/run/secrets/apns.p8",
        "apns_key_id": "ABCDE12345",
        "apns_team_id": "TEAM123456",
        "apns_topic": "com.lia.assistant",
        **overrides,
    }


class TestOperatingARelay:
    def test_a_fully_configured_relay_boots(self) -> None:
        settings = PushRelaySettings(**_complete())  # type: ignore[arg-type]

        assert settings.push_relay_enabled is True

    @pytest.mark.parametrize(
        ("field", "variable"),
        [
            ("push_relay_seal_key", "PUSH_RELAY_SEAL_KEY"),
            ("apns_key_path", "APNS_KEY_PATH"),
            ("apns_key_id", "APNS_KEY_ID"),
            ("apns_team_id", "APNS_TEAM_ID"),
            ("apns_topic", "APNS_TOPIC"),
        ],
    )
    def test_each_missing_credential_names_itself(self, field: str, variable: str) -> None:
        with pytest.raises(ValidationError) as exc_info:
            PushRelaySettings(**_complete(**{field: None}))  # type: ignore[arg-type]

        # The operator must read WHICH variable is missing, not that something
        # somewhere is invalid.
        assert variable in str(exc_info.value)

    def test_a_disabled_relay_needs_no_credentials(self) -> None:
        settings = PushRelaySettings(push_relay_enabled=False)

        # Which is every deployment but one.
        assert settings.push_relay_enabled is False
        assert settings.apns_key_id is None


class TestUsingARelay:
    def test_no_relay_is_the_default(self) -> None:
        settings = PushRelaySettings()

        # Silently pointing a self-hosted deployment at someone else's relay
        # would be a privacy decision taken by a constant.
        assert settings.push_relay_url is None

    def test_pointing_at_a_relay_needs_nothing_else(self) -> None:
        settings = PushRelaySettings(push_relay_url="https://lia.example.com")

        # A caller is not an operator: it holds no key and signs nothing.
        assert settings.push_relay_url == "https://lia.example.com"
        assert settings.push_relay_enabled is False
