"""`/auth/mfa/verify` accepts its pending token from a cookie.

The password login answers with JSON and hands the pending token to the client,
which passes it back in the body. A provider sign-in ends in a REDIRECT and
cannot do that — so the token travels in an httpOnly cookie instead, and this
endpoint learned to read it from there.

The body keeps priority, so the password path is untouched; and the cookie is
cleared on every terminal outcome, so a spent or rejected token never lingers
in a browser waiting to be replayed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.auth.schemas import MFAVerifyRequest
from src.domains.auth.totp_service import PendingLogin
from src.domains.users.models import User
from src.infrastructure.database.registry import import_all_models

import_all_models()

pytestmark = pytest.mark.unit

MODULE = "src.domains.auth.totp_router"


def _make_user() -> User:
    now = datetime.now(UTC)
    return User(
        id=uuid.uuid4(),
        email="mfa@example.com",
        full_name="MFA User",
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


async def _verify(
    *,
    body_token: str | None,
    cookie_token: str | None,
    response: Response | None = None,
):
    from src.domains.auth.totp_router import mfa_verify

    user = _make_user()
    service = MagicMock()
    service.consume_pending_token = AsyncMock(
        return_value=PendingLogin(user_id=str(user.id), remember_me=False)
    )
    service.verify_for_login = AsyncMock()

    request = MagicMock()
    request.headers.get.return_value = "Mozilla/5.0"
    request.client.host = "10.0.0.7"

    with (
        patch(f"{MODULE}.TOTPService", return_value=service),
        patch(
            f"{MODULE}.UserRepository",
            return_value=MagicMock(get_user_minimal_for_session=AsyncMock(return_value=user)),
        ),
        patch(f"{MODULE}.create_authenticated_session_with_cookie", AsyncMock()),
        patch(f"{MODULE}.notify_new_login_if_unknown", AsyncMock()),
    ):
        result = await mfa_verify(
            data=MFAVerifyRequest(mfa_token=body_token, code="123456"),
            response=response if response is not None else Response(),
            http_request=request,
            db=AsyncMock(spec=AsyncSession),
            _rate_limit=None,
            mfa_pending_cookie=cookie_token,
        )
    return result, service


class TestTokenSource:
    """Where the pending token is read from."""

    async def test_the_body_is_used_when_present(self) -> None:
        _, service = await _verify(body_token="from-body", cookie_token=None)

        service.consume_pending_token.assert_awaited_once_with("from-body")

    async def test_the_cookie_is_used_when_the_body_has_none(self) -> None:
        _, service = await _verify(body_token=None, cookie_token="from-cookie")

        service.consume_pending_token.assert_awaited_once_with("from-cookie")

    async def test_the_body_wins_over_the_cookie(self) -> None:
        """The password path must keep behaving exactly as it did."""
        _, service = await _verify(body_token="from-body", cookie_token="from-cookie")

        service.consume_pending_token.assert_awaited_once_with("from-body")

    async def test_neither_source_is_rejected_without_touching_the_service(self) -> None:
        with pytest.raises(HTTPException) as exc:
            await _verify(body_token=None, cookie_token=None)

        assert exc.value.status_code == 401


class TestCookieHygiene:
    """A pending cookie never survives the step it was minted for."""

    async def test_success_clears_the_cookie(self) -> None:
        response = Response()
        await _verify(body_token=None, cookie_token="from-cookie", response=response)

        assert 'lia_mfa_pending=""' in response.headers["set-cookie"]

    async def test_a_rejected_token_also_clears_the_cookie(self) -> None:
        """Otherwise a dead cookie is presented on every later attempt."""
        from src.domains.auth.totp_router import mfa_verify

        service = MagicMock()
        service.consume_pending_token = AsyncMock(return_value=None)
        response = Response()

        with patch(f"{MODULE}.TOTPService", return_value=service):
            with pytest.raises(HTTPException):
                await mfa_verify(
                    data=MFAVerifyRequest(mfa_token=None, code="123456"),
                    response=response,
                    http_request=MagicMock(),
                    db=AsyncMock(spec=AsyncSession),
                    _rate_limit=None,
                    mfa_pending_cookie="stale",
                )

        assert 'lia_mfa_pending=""' in response.headers["set-cookie"]


class TestSchema:
    """The request contract stays backward compatible."""

    def test_mfa_token_is_optional(self) -> None:
        request = MFAVerifyRequest(code="123456")

        assert request.mfa_token is None

    def test_a_body_token_still_validates(self) -> None:
        request = MFAVerifyRequest(mfa_token="tok", code="123456")

        assert request.mfa_token == "tok"
