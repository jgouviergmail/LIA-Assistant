"""Unit tests for the public /auth/features capability endpoint."""

from unittest.mock import patch

import pytest

from src.domains.auth.router import auth_features


@pytest.mark.unit
class TestAuthFeatures:
    """The endpoint mirrors the MFA feature flag, nothing more."""

    async def test_reports_mfa_disabled(self) -> None:
        """Default posture: mfa_enabled=False."""
        with patch("src.domains.auth.router.settings") as mock_settings:
            mock_settings.mfa_enabled = False
            response = await auth_features()
        assert response.mfa_enabled is False

    async def test_reports_mfa_enabled(self) -> None:
        """Flag on → capability advertised."""
        with patch("src.domains.auth.router.settings") as mock_settings:
            mock_settings.mfa_enabled = True
            response = await auth_features()
        assert response.mfa_enabled is True
