"""Unit tests for the per-user rate limiter dependency (security program D1).

Complements the per-IP limiter contract pinned in
``tests/unit/core/test_router_service_error_contract.py``: the per-user
variant keys the sliding window on the authenticated account so IP rotation
cannot reset a targeted account's budget.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from src.domains.auth.dependencies import create_user_rate_limiter
from src.domains.users.models import User


def _make_user() -> User:
    now = datetime.now(UTC)
    return User(
        id=uuid.uuid4(),
        email="limited@example.com",
        is_active=True,
        is_verified=True,
        is_superuser=False,
        language="fr",
        timezone="Europe/Paris",
        created_at=now,
        updated_at=now,
    )


@pytest.mark.unit
class TestCreateUserRateLimiter:
    """Sliding window keyed on the user id, fail-open on infrastructure errors."""

    async def test_allows_within_window_and_keys_on_user_id(self) -> None:
        """The Redis key embeds the user id, not the client IP."""
        user = _make_user()
        limiter = AsyncMock()
        limiter.acquire = AsyncMock(return_value=True)
        dependency = create_user_rate_limiter("webauthn_enroll", max_calls=5)

        with patch("src.domains.auth.dependencies.get_rate_limiter", return_value=limiter):
            await dependency(user)

        kwargs = limiter.acquire.call_args.kwargs
        assert kwargs["key"] == f"auth:webauthn_enroll:user:{user.id}"
        assert kwargs["max_calls"] == 5

    async def test_exceeded_window_raises_429_with_retry_after(self) -> None:
        """Window exhausted → typed 429 with Retry-After header."""
        limiter = AsyncMock()
        limiter.acquire = AsyncMock(return_value=False)
        dependency = create_user_rate_limiter("webauthn_enroll", max_calls=5)

        with patch("src.domains.auth.dependencies.get_rate_limiter", return_value=limiter):
            with pytest.raises(HTTPException) as exc_info:
                await dependency(_make_user())

        assert exc_info.value.status_code == 429
        assert exc_info.value.headers is not None
        assert exc_info.value.headers.get("Retry-After") == "60"

    async def test_infrastructure_error_fails_open(self) -> None:
        """Redis down → request proceeds (fail-open, matching the IP variant)."""
        dependency = create_user_rate_limiter("webauthn_enroll", max_calls=5)

        with patch(
            "src.domains.auth.dependencies.get_rate_limiter",
            side_effect=Exception("Redis down"),
        ):
            await dependency(_make_user())
