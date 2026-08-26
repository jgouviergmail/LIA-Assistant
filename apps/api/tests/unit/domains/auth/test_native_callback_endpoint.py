"""`POST /auth/native/callback`: turning a handoff code into a real session.

The endpoint's NAME is a security decision, and one test says so out loud.
``forbid_federated_signin_in_demo`` classifies by path SHAPE —
``…/auth/<provider>/<login|callback>`` — so this path inherits the
demonstrator's refusal automatically. Anything called ``/auth/native/handoff``
would have slipped past it silently.

Beyond that: the code is worthless without the verifier, a code carrying an
unfinished second factor produces an MFA step rather than a session, and every
failure answers the same thing.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.auth.native_handoff import NativeHandoff
from src.domains.auth.schemas import NativeCallbackRequest
from src.domains.users.models import User
from src.infrastructure.database.registry import import_all_models

import_all_models()

pytestmark = pytest.mark.unit

ROUTER = "src.domains.auth.oauth_router"
_VERIFIER = "v" * 43
_CHALLENGE = "c" * 43


def _make_user(active: bool = True) -> User:
    now = datetime.now(UTC)
    return User(
        id=uuid.uuid4(),
        email="native@example.com",
        full_name="Native User",
        is_active=active,
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


def _fake_request() -> MagicMock:
    request = MagicMock()
    request.headers.get.return_value = "LIA/1.0 (Android)"
    request.client.host = "10.0.0.7"
    request.cookies.get.return_value = None
    return request


#: Distinguishes "caller did not care" from "the repository finds nobody".
_UNSET = object()


async def _call(
    *,
    handoff: NativeHandoff | None,
    user: User | None | object = _UNSET,
    response: Response | None = None,
):
    from src.domains.auth.oauth_router import native_callback

    user = _make_user() if user is _UNSET else user
    totp_service = MagicMock()
    totp_service.create_pending_token = AsyncMock(return_value="pending-tok")

    with (
        patch(f"{ROUTER}.consume_handoff", AsyncMock(return_value=handoff)) as consume,
        patch(f"{ROUTER}.TOTPService", return_value=totp_service),
        patch(f"{ROUTER}.notify_new_login_if_unknown", AsyncMock()),
        patch(
            f"{ROUTER}.UserRepository",
            return_value=MagicMock(get_user_minimal_for_session=AsyncMock(return_value=user)),
        ),
        patch(f"{ROUTER}.create_authenticated_session_with_cookie") as session_cookie,
        patch(f"{ROUTER}.settings") as fake_settings,
    ):
        fake_settings.mfa_pending_ttl_seconds = 300
        result = await native_callback(
            data=NativeCallbackRequest(code="handoff-code", verifier=_VERIFIER),
            response=response if response is not None else Response(),
            http_request=_fake_request(),
            db=AsyncMock(spec=AsyncSession),
            _rate_limit=None,
        )
    return result, session_cookie, consume, totp_service


class TestSuccess:
    """A valid code, no second factor owed."""

    async def test_creates_the_session_for_the_named_user(self) -> None:
        user = _make_user()
        handoff = NativeHandoff(user_id=str(user.id), challenge=_CHALLENGE, mfa_pending=False)
        result, session_cookie, _, _ = await _call(handoff=handoff, user=user)

        assert result.mfa_required is False
        assert result.user is not None
        assert result.user.email == "native@example.com"
        session_cookie.assert_awaited_once()
        assert session_cookie.await_args.kwargs["auth_methods"] == ["oauth_google", "native_app"]

    async def test_presents_the_verifier_to_the_handoff(self) -> None:
        user = _make_user()
        handoff = NativeHandoff(user_id=str(user.id), challenge=_CHALLENGE, mfa_pending=False)
        _, _, consume, _ = await _call(handoff=handoff, user=user)

        consume.assert_awaited_once_with("handoff-code", _VERIFIER)


class TestSecondFactorStillOwed:
    """A code minted for a TOTP-active account grants an MFA step, not a session."""

    async def test_answers_mfa_required_without_creating_a_session(self) -> None:
        user = _make_user()
        handoff = NativeHandoff(user_id=str(user.id), challenge=_CHALLENGE, mfa_pending=True)
        result, session_cookie, _, totp_service = await _call(handoff=handoff, user=user)

        assert result.mfa_required is True
        assert result.user is None
        session_cookie.assert_not_awaited()
        totp_service.create_pending_token.assert_awaited_once()

    async def test_the_pending_token_lands_in_a_cookie_not_in_the_body(self) -> None:
        """The WebView is the caller, so the cookie reaches the right jar."""
        user = _make_user()
        handoff = NativeHandoff(user_id=str(user.id), challenge=_CHALLENGE, mfa_pending=True)
        response = Response()
        result, _, _, _ = await _call(handoff=handoff, user=user, response=response)

        assert getattr(result, "mfa_token", None) is None
        cookie = response.headers["set-cookie"]
        assert "pending-tok" in cookie
        assert "HttpOnly" in cookie


class TestRefusals:
    """Everything that must answer the same thing."""

    async def test_an_unusable_code_is_rejected(self) -> None:
        with pytest.raises(HTTPException) as exc:
            await _call(handoff=None)

        assert exc.value.status_code == 401

    async def test_an_unknown_user_is_rejected(self) -> None:
        handoff = NativeHandoff(user_id=str(uuid.uuid4()), challenge=_CHALLENGE, mfa_pending=False)
        with pytest.raises(HTTPException) as exc:
            await _call(handoff=handoff, user=None)  # repository returns None

        assert exc.value.status_code == 401

    async def test_a_corrupt_user_id_is_refused_not_a_500(self) -> None:
        """A malformed payload must answer like any other bad code.

        Nothing we write produces this, but a corrupted Redis value would
        otherwise surface as an unhandled exception on an authentication
        endpoint — a 500 where a 401 belongs.
        """
        handoff = NativeHandoff(user_id="not-a-uuid", challenge=_CHALLENGE, mfa_pending=False)
        with pytest.raises(HTTPException) as exc:
            await _call(handoff=handoff)

        assert exc.value.status_code == 401

    async def test_a_deactivated_user_is_rejected(self) -> None:
        user = _make_user(active=False)
        handoff = NativeHandoff(user_id=str(user.id), challenge=_CHALLENGE, mfa_pending=False)
        with pytest.raises(HTTPException) as exc:
            await _call(handoff=handoff, user=user)

        assert exc.value.status_code == 401


class TestDemonstratorInheritsTheRefusal:
    """The path's shape is what closes it on a public demonstrator."""

    def test_the_route_is_classified_as_a_federated_sign_in(self) -> None:
        from src.core.demo_mode import is_federated_signin_path

        # Named `/auth/native/callback` on purpose: a name like
        # `/auth/native/handoff` would NOT match this shape, and the
        # demonstrator's refusal would have been bypassed in silence.
        assert is_federated_signin_path("/api/v1/auth/native/callback") is True
