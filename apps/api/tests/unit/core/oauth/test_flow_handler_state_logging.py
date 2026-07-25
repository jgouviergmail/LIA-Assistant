"""The OAuth state token must never be handed to the logging stack (SEC-012).

The state is a single-use CSRF credential. ``pii_filter`` fingerprints it before
rendering, but that net sits at the *end* of the structlog pipeline: anything
that bypasses structlog — a stdlib logger, a third-party handler, a future
renderer — would emit whatever was passed in. These tests assert the value never
enters the call in the first place, and that correlation is preserved through a
non-reversible fingerprint.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from structlog.testing import capture_logs

from src.core.oauth.exceptions import OAuthStateValidationError
from src.core.oauth.flow_handler import OAuthFlowHandler
from src.infrastructure.observability.pii_filter import fingerprint_secret

# A high-entropy value shaped like a real state token (secrets.token_urlsafe(32)).
_STATE = "Zx8QpLmv3NrTfKe1Ab9YsWc7Hd2Gj5Uo0Vi4Rt6Bn"


@pytest.fixture
def handler() -> OAuthFlowHandler:
    """Build a handler with a stub provider and a mocked session service."""
    provider = MagicMock()
    provider.provider_name = "google"
    provider.scopes = ["openid", "email"]

    session_service = MagicMock()
    session_service.get_oauth_state = AsyncMock(return_value=None)

    return OAuthFlowHandler(provider=provider, session_service=session_service)


def _flatten(logs: list[dict]) -> str:
    """Render captured log events as one string for absence assertions."""
    return repr(logs)


class TestStateNeverReachesTheLogger:
    """Absence assertions on the state token."""

    @pytest.mark.asyncio
    async def test_invalid_state_logs_fingerprint_not_value(self, handler):
        """A rejected callback logs ``state_fp``, never the raw state."""
        with capture_logs() as logs:
            with pytest.raises(OAuthStateValidationError):
                await handler._validate_state_and_get_verifier(_STATE)

        flat = _flatten(logs)
        assert _STATE not in flat, "the raw state token reached the logging stack"
        assert (
            fingerprint_secret(_STATE) in flat
        ), "correlation must survive: the fingerprint has to be logged instead"

    @pytest.mark.asyncio
    async def test_provider_mismatch_logs_fingerprint_not_value(self, handler):
        """A cross-provider callback also logs only the fingerprint."""
        handler.session_service.get_oauth_state = AsyncMock(
            return_value={"provider": "microsoft", "code_verifier": "v" * 43}
        )

        with capture_logs() as logs:
            with pytest.raises(OAuthStateValidationError):
                await handler._validate_state_and_get_verifier(_STATE)

        flat = _flatten(logs)
        assert _STATE not in flat
        assert fingerprint_secret(_STATE) in flat

    @pytest.mark.asyncio
    async def test_missing_code_verifier_logs_fingerprint_not_value(self, handler):
        """A state without PKCE verifier is refused without echoing the state."""
        handler.session_service.get_oauth_state = AsyncMock(return_value={"provider": "google"})

        with capture_logs() as logs:
            with pytest.raises(OAuthStateValidationError):
                await handler._validate_state_and_get_verifier(_STATE)

        flat = _flatten(logs)
        assert _STATE not in flat
        assert fingerprint_secret(_STATE) in flat


class TestFingerprintProperties:
    """The fingerprint must be usable for correlation, and only for that."""

    def test_fingerprint_is_stable_and_non_reversible(self):
        """Same input → same tag; the tag does not contain the secret."""
        first = fingerprint_secret(_STATE)
        assert first == fingerprint_secret(_STATE)
        assert _STATE not in first
        assert first.startswith("fp_")

    def test_distinct_states_get_distinct_fingerprints(self):
        """Two flows are distinguishable in the logs."""
        assert fingerprint_secret(_STATE) != fingerprint_secret(_STATE[:-1] + "X")
