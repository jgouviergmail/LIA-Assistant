"""Unit tests for the two-step login glue (security program D1, Lot 2).

Covers the /auth/login branch that returns a pending token instead of a
session when TOTP is active, and the /auth/mfa/verify endpoint that turns a
pending token + code into a BFF session.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.auth.schemas import MFAVerifyRequest, UserLoginRequest, UserResponse
from src.domains.auth.totp_service import PendingLogin
from src.domains.users.models import User
from src.infrastructure.database.registry import import_all_models

import_all_models()


def _make_user(user_id: uuid.UUID | None = None) -> User:
    now = datetime.now(UTC)
    return User(
        id=user_id or uuid.uuid4(),
        email="two-step@example.com",
        full_name="Two Step",
        is_active=True,
        is_verified=True,
        is_superuser=False,
        language="fr",
        timezone="Europe/Paris",
        execution_mode="pipeline",
        memory_enabled=True,
        voice_enabled=False,
        theme="system",
        color_theme="default",
        image_generation_enabled=True,
        image_generation_default_quality="low",
        image_generation_default_size="portrait",
        image_generation_output_format="png",
        login_notifications_enabled=True,
        created_at=now,
        updated_at=now,
    )


def _user_response(user: User) -> UserResponse:
    return UserResponse.model_validate(user)


def _fake_request() -> MagicMock:
    """Request stand-in: UA header + client host for bounded metadata."""
    request = MagicMock()
    request.headers.get.return_value = "Mozilla/5.0 (Windows) Chrome/126"
    request.client.host = "10.0.0.7"
    request.cookies.get.return_value = None
    return request


@pytest.mark.unit
class TestLoginTwoStep:
    """/auth/login returns a pending token (no cookie) when TOTP is active."""

    async def test_totp_active_returns_pending_token_without_session(self) -> None:
        """TOTP-active account: mfa_required response, session NOT created."""
        from src.domains.auth.router import login

        user = _make_user()
        user_response = _user_response(user)

        auth_service = MagicMock()
        auth_service.login = AsyncMock(return_value=user_response)
        auth_service.repository.get_by_email = AsyncMock(return_value=user)
        totp_service = MagicMock()
        totp_service.has_confirmed_totp = AsyncMock(return_value=True)
        totp_service.create_pending_token = AsyncMock(return_value="pending-tok")

        with (
            patch("src.domains.auth.router.AuthService", return_value=auth_service),
            patch("src.domains.auth.router.settings") as mock_settings,
            patch("src.domains.auth.router.TOTPService", return_value=totp_service),
            patch(
                "src.domains.auth.router.create_authenticated_session_with_cookie"
            ) as mock_cookie,
        ):
            mock_settings.mfa_enabled = True
            result = await login(
                data=UserLoginRequest(
                    email="two-step@example.com", password="pw", remember_me=True
                ),
                response=Response(),
                http_request=_fake_request(),
                db=AsyncMock(spec=AsyncSession),
                _rate_limit=None,
                lia_session=None,
            )

        assert result.mfa_required is True
        assert result.mfa_token == "pending-tok"
        assert result.user is None
        mock_cookie.assert_not_awaited()
        totp_service.create_pending_token.assert_awaited_once_with(
            user.id, remember_me=True, known_device=False, fcm_token_id=None
        )

    async def test_totp_inactive_creates_session_normally(self) -> None:
        """No TOTP: the classic single-step login (cookie + user)."""
        from src.domains.auth.router import login

        user = _make_user()
        user_response = _user_response(user)

        auth_service = MagicMock()
        auth_service.login = AsyncMock(return_value=user_response)
        auth_service.repository.get_by_email = AsyncMock(return_value=user)
        totp_service = MagicMock()
        totp_service.has_confirmed_totp = AsyncMock(return_value=False)

        with (
            patch("src.domains.auth.router.AuthService", return_value=auth_service),
            patch("src.domains.auth.router.settings") as mock_settings,
            patch("src.domains.auth.router.TOTPService", return_value=totp_service),
            patch(
                "src.domains.auth.router.create_authenticated_session_with_cookie",
                new_callable=AsyncMock,
            ) as mock_cookie,
            # login_notifications_enabled=True would otherwise run the A4
            # notification query against the mocked session (F028 leak).
            patch(
                "src.domains.auth.router.notify_new_login_if_unknown",
                new_callable=AsyncMock,
            ),
        ):
            mock_settings.mfa_enabled = True
            result = await login(
                data=UserLoginRequest(
                    email="two-step@example.com", password="pw", remember_me=False
                ),
                response=Response(),
                http_request=_fake_request(),
                db=AsyncMock(spec=AsyncSession),
                _rate_limit=None,
                lia_session=None,
            )

        assert result.mfa_required is False
        assert result.user is user_response
        assert mock_cookie.await_args.kwargs["auth_methods"] == ["password"]


@pytest.mark.unit
class TestMFAVerify:
    """/auth/mfa/verify: pending token + code → session."""

    async def test_happy_path_creates_session_with_totp_methods(self) -> None:
        """Valid token + code: cookie set with password+totp method tags."""
        from src.domains.auth.totp_router import mfa_verify

        user = _make_user()
        totp_service = MagicMock()
        totp_service.consume_pending_token = AsyncMock(
            return_value=PendingLogin(user_id=str(user.id), remember_me=True)
        )
        totp_service.verify_for_login = AsyncMock()
        user_repo = MagicMock()
        user_repo.get_user_minimal_for_session = AsyncMock(return_value=user)

        with (
            patch("src.domains.auth.totp_router.TOTPService", return_value=totp_service),
            patch("src.domains.auth.totp_router.UserRepository", return_value=user_repo),
            patch(
                "src.domains.auth.totp_router.create_authenticated_session_with_cookie",
                new_callable=AsyncMock,
            ) as mock_cookie,
            patch(
                "src.domains.auth.totp_router.notify_new_login_if_unknown",
                new_callable=AsyncMock,
            ),
        ):
            result = await mfa_verify(
                data=MFAVerifyRequest(mfa_token="tok", code="123456"),
                response=Response(),
                http_request=_fake_request(),
                db=AsyncMock(spec=AsyncSession),
                _rate_limit=None,
            )

        assert result.user is not None
        kwargs = mock_cookie.await_args.kwargs
        assert kwargs["auth_methods"] == ["password", "totp"]
        assert kwargs["remember_me"] is True
        totp_service.verify_for_login.assert_awaited_once_with(user.id, "123456")

    async def test_expired_or_replayed_token_rejects_401(self) -> None:
        """Unknown/expired/replayed pending token → generic 401."""
        from src.domains.auth.totp_router import mfa_verify

        totp_service = MagicMock()
        totp_service.consume_pending_token = AsyncMock(return_value=None)

        with patch("src.domains.auth.totp_router.TOTPService", return_value=totp_service):
            with pytest.raises(Exception) as exc_info:
                await mfa_verify(
                    data=MFAVerifyRequest(mfa_token="gone", code="123456"),
                    response=Response(),
                    http_request=_fake_request(),
                    db=AsyncMock(spec=AsyncSession),
                    _rate_limit=None,
                )
        assert exc_info.value.status_code == 401  # type: ignore[union-attr]

    async def test_invalid_code_propagates_401_without_session(self) -> None:
        """A bad code never creates a session (and the token stays consumed)."""
        from src.core.exceptions import raise_invalid_credentials
        from src.domains.auth.totp_router import mfa_verify

        totp_service = MagicMock()
        totp_service.consume_pending_token = AsyncMock(
            return_value=PendingLogin(user_id=str(uuid.uuid4()), remember_me=False)
        )
        totp_service.verify_for_login = AsyncMock(
            side_effect=lambda *_: raise_invalid_credentials()
        )

        with (
            patch("src.domains.auth.totp_router.TOTPService", return_value=totp_service),
            patch(
                "src.domains.auth.totp_router.create_authenticated_session_with_cookie",
                new_callable=AsyncMock,
            ) as mock_cookie,
        ):
            with pytest.raises(Exception) as exc_info:
                await mfa_verify(
                    data=MFAVerifyRequest(mfa_token="tok", code="000000"),
                    response=Response(),
                    http_request=_fake_request(),
                    db=AsyncMock(spec=AsyncSession),
                    _rate_limit=None,
                )

        assert exc_info.value.status_code == 401  # type: ignore[union-attr]
        mock_cookie.assert_not_awaited()
