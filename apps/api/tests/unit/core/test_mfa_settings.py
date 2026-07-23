"""Unit tests for MFASettings (config module, security program D1).

Pins the .env inline-comment leakage guard: docker compose passes
``KEY=   # comment`` through as ``# comment`` when the value is empty, and a
polluted RP ID must refuse to boot instead of silently breaking every
WebAuthn ceremony.
"""

import pytest
from pydantic import ValidationError

from src.core.config.mfa import MFASettings


@pytest.mark.unit
class TestMFASettingsDefaults:
    """Defaults are the safe, disabled posture."""

    def test_defaults(self) -> None:
        """Flag off, empty RP derivations, sane numeric bounds."""
        settings = MFASettings(_env_file=None)
        assert settings.mfa_enabled is False
        assert settings.webauthn_rp_id == ""
        assert settings.webauthn_expected_origin == ""
        assert settings.webauthn_challenge_ttl_seconds == 300
        assert settings.mfa_max_passkeys_per_user == 10


@pytest.mark.unit
class TestLeakedCommentGuard:
    """A leaked .env inline comment must fail boot with a clear message."""

    def test_leaked_comment_rejected(self) -> None:
        """docker compose leakage shape: '# Relying Party ID (domain...)'."""
        with pytest.raises(ValidationError, match="leaked .env inline comment"):
            MFASettings(_env_file=None, webauthn_rp_id="# Relying Party ID (domain)")

    def test_whitespace_value_rejected(self) -> None:
        """An RP ID can never contain interior whitespace."""
        with pytest.raises(ValidationError, match="leaked .env inline comment"):
            MFASettings(_env_file=None, webauthn_expected_origin="https://a b")

    def test_surrounding_whitespace_is_stripped(self) -> None:
        """Plain padding is normalized, not rejected."""
        settings = MFASettings(_env_file=None, webauthn_rp_id="  lia.example.com  ")
        assert settings.webauthn_rp_id == "lia.example.com"
