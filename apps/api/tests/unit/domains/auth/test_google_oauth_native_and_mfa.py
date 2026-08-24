"""Google sign-in: the second factor is now enforced, and a native shell can sign in.

Two changes meet on the same endpoint, and the tests keep them apart.

**The second factor.** The password path has always refused a session to a
TOTP-active account and handed back a pending token instead. The Google callback
did not — measured 2026-08-24 — so anyone who enabled TOTP could walk past it by
signing in with Google. A redirect cannot answer with JSON, so the pending token
travels in an httpOnly cookie: putting a single-use credential in a URL would
leave it in history, referrers and logs.

**The native shell.** OAuth is refused inside a WebView, so the app sends the
user to the system browser — where the session cookie would land, uselessly. The
callback instead mints a handoff code and returns through a deep link. The code
names a user; it is not a session, and it is worthless without the verifier the
WebView kept.

The web path must be untouched by either change, which several tests assert
directly rather than by omission.
"""

from __future__ import annotations

import base64
import hashlib
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.auth.schemas import UserResponse
from src.domains.users.models import User
from src.infrastructure.database.registry import import_all_models

import_all_models()

pytestmark = pytest.mark.unit

ROUTER = "src.domains.auth.oauth_router"

_VERIFIER = "v" * 43
_CHALLENGE = (
    base64.urlsafe_b64encode(hashlib.sha256(_VERIFIER.encode("ascii")).digest())
    .decode("ascii")
    .rstrip("=")
)


def _make_user() -> User:
    now = datetime.now(UTC)
    return User(
        id=uuid.uuid4(),
        email="oauth@example.com",
        full_name="OAuth User",
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


def _fake_request() -> MagicMock:
    request = MagicMock()
    request.headers.get.return_value = "Mozilla/5.0 (Windows) Chrome/126"
    request.client.host = "10.0.0.7"
    request.cookies.get.return_value = None
    return request


class _CallbackHarness:
    """Everything the callback touches, mocked once."""

    def __init__(self, *, totp_active: bool, native_challenge: str | None) -> None:
        self.user = _make_user()
        self.user_response = UserResponse.model_validate(self.user)

        self.auth_service = MagicMock()
        self.auth_service.handle_google_callback = AsyncMock(return_value=self.user_response)

        self.totp_service = MagicMock()
        self.totp_service.has_confirmed_totp = AsyncMock(return_value=totp_active)
        self.totp_service.create_pending_token = AsyncMock(return_value="pending-tok")

        self.native_challenge = native_challenge
        self.issue_handoff = AsyncMock(return_value="handoff-code")

    def patches(self) -> list:
        return [
            patch(f"{ROUTER}.AuthService", return_value=self.auth_service),
            patch(f"{ROUTER}.TOTPService", return_value=self.totp_service),
            patch(f"{ROUTER}.peek_native_challenge", AsyncMock(return_value=self.native_challenge)),
            patch(f"{ROUTER}.issue_handoff", self.issue_handoff),
            patch(f"{ROUTER}.notify_new_login_if_unknown", AsyncMock()),
            patch(
                f"{ROUTER}.UserRepository",
                return_value=MagicMock(
                    get_user_minimal_for_session=AsyncMock(return_value=self.user)
                ),
            ),
        ]


async def _run_callback(harness: _CallbackHarness) -> tuple[Response, MagicMock]:
    from src.domains.auth.oauth_router import google_callback

    with (
        patch(f"{ROUTER}.settings") as fake_settings,
        patch(f"{ROUTER}.create_authenticated_session_with_cookie") as session_cookie,
    ):
        fake_settings.mfa_enabled = True
        fake_settings.frontend_url = "https://lia.example.com"
        stack = harness.patches()
        for patcher in stack:
            patcher.start()
        try:
            result = await google_callback(
                code="auth-code",
                state="state-token",
                http_request=_fake_request(),
                db=AsyncMock(spec=AsyncSession),
            )
        finally:
            for patcher in stack:
                patcher.stop()
    return result, session_cookie


class TestWebPathUnchanged:
    """The browser flow must behave exactly as it did before."""

    async def test_no_totp_creates_the_session_and_lands_on_the_dashboard(self) -> None:
        harness = _CallbackHarness(totp_active=False, native_challenge=None)
        result, session_cookie = await _run_callback(harness)

        assert result.status_code == 302
        assert result.headers["location"] == "https://lia.example.com/dashboard"
        session_cookie.assert_awaited_once()
        harness.totp_service.create_pending_token.assert_not_awaited()
        harness.issue_handoff.assert_not_awaited()


class TestSecondFactorEnforced:
    """A TOTP-active account no longer walks past its second factor."""

    async def test_totp_active_refuses_the_session_and_asks_for_the_code(self) -> None:
        harness = _CallbackHarness(totp_active=True, native_challenge=None)
        result, session_cookie = await _run_callback(harness)

        session_cookie.assert_not_awaited()
        assert result.headers["location"] == "https://lia.example.com/login?mfa=1"

    async def test_the_pending_token_travels_in_a_cookie_never_in_the_url(self) -> None:
        harness = _CallbackHarness(totp_active=True, native_challenge=None)
        result, _ = await _run_callback(harness)

        assert "pending-tok" not in result.headers["location"]
        cookie = result.headers["set-cookie"]
        assert "pending-tok" in cookie
        assert "HttpOnly" in cookie

    async def test_the_pending_token_is_minted_for_that_user(self) -> None:
        harness = _CallbackHarness(totp_active=True, native_challenge=None)
        await _run_callback(harness)

        harness.totp_service.create_pending_token.assert_awaited_once()
        assert harness.totp_service.create_pending_token.await_args.args[0] == harness.user.id


class TestNativeShell:
    """The deep-link return, and what it does and does not carry."""

    async def test_native_flow_returns_a_deep_link_with_a_code(self) -> None:
        harness = _CallbackHarness(totp_active=False, native_challenge=_CHALLENGE)
        result, session_cookie = await _run_callback(harness)

        assert result.headers["location"].startswith("lia://auth-callback?code=")
        # The browser must not end up holding the session: that is the whole
        # reason the handoff exists.
        session_cookie.assert_not_awaited()

    async def test_the_handoff_carries_the_challenge_and_the_mfa_state(self) -> None:
        harness = _CallbackHarness(totp_active=True, native_challenge=_CHALLENGE)
        await _run_callback(harness)

        harness.issue_handoff.assert_awaited_once_with(
            user_id=str(harness.user.id), challenge=_CHALLENGE, mfa_pending=True
        )

    async def test_native_flow_never_mints_a_pending_token_in_the_browser(self) -> None:
        """The MFA step happens in the app, against the app's own cookie jar."""
        harness = _CallbackHarness(totp_active=True, native_challenge=_CHALLENGE)
        result, _ = await _run_callback(harness)

        harness.totp_service.create_pending_token.assert_not_awaited()
        assert "set-cookie" not in {key.lower() for key in result.headers}


class TestLoginInitiation:
    """`/auth/google/login` only changes when a challenge is supplied."""

    async def test_without_a_challenge_the_call_is_unchanged(self) -> None:
        from src.domains.auth.oauth_router import google_login

        service = MagicMock()
        service.initiate_google_oauth = AsyncMock(return_value=("https://accounts", "state"))
        with patch(f"{ROUTER}.AuthService", return_value=service):
            result = await google_login(db=AsyncMock(spec=AsyncSession), native_challenge=None)

        assert result["authorization_url"] == "https://accounts"
        service.initiate_google_oauth.assert_awaited_once_with(metadata=None)

    async def test_a_valid_challenge_reaches_the_server_side_state(self) -> None:
        from src.domains.auth.oauth_router import google_login

        service = MagicMock()
        service.initiate_google_oauth = AsyncMock(return_value=("https://accounts", "state"))
        with patch(f"{ROUTER}.AuthService", return_value=service):
            await google_login(db=AsyncMock(spec=AsyncSession), native_challenge=_CHALLENGE)

        service.initiate_google_oauth.assert_awaited_once_with(
            metadata={"native_challenge": _CHALLENGE}
        )

    async def test_a_malformed_challenge_is_refused_at_the_door(self) -> None:
        """Storing it would mint a code guaranteed to fail minutes later."""
        from fastapi import HTTPException

        from src.domains.auth.oauth_router import google_login

        service = MagicMock()
        service.initiate_google_oauth = AsyncMock()
        with patch(f"{ROUTER}.AuthService", return_value=service):
            with pytest.raises(HTTPException) as exc:
                await google_login(db=AsyncMock(spec=AsyncSession), native_challenge="too-short")

        assert exc.value.status_code == 400
        service.initiate_google_oauth.assert_not_awaited()


class TestFailuresNeverStrandTheUser:
    """Whatever goes wrong, the user must land somewhere they can act.

    Before this, a native flow that failed re-raised: the traveller was left in
    the system browser looking at an API error, with no way back into the app
    that had sent them there.
    """

    @staticmethod
    async def _failing_callback(native_challenge: str | None):
        from src.domains.auth.oauth_router import google_callback

        auth_service = MagicMock()
        auth_service.handle_google_callback = AsyncMock(side_effect=RuntimeError("state mismatch"))

        with (
            patch(f"{ROUTER}.settings") as fake_settings,
            patch(f"{ROUTER}.AuthService", return_value=auth_service),
            patch(f"{ROUTER}.peek_native_challenge", AsyncMock(return_value=native_challenge)),
        ):
            fake_settings.mfa_enabled = True
            fake_settings.frontend_url = "https://lia.example.com"
            fake_settings.native_app_scheme = "lia"
            return await google_callback(
                http_request=_fake_request(),
                code="auth-code",
                state="state-token",
                db=AsyncMock(spec=AsyncSession),
            )

    async def test_a_native_failure_returns_through_the_deep_link(self) -> None:
        result = await self._failing_callback(_CHALLENGE)

        assert result.status_code == 302
        assert result.headers["location"].startswith("lia://auth-callback?error=")

    async def test_a_web_failure_lands_on_the_page_built_for_it(self) -> None:
        result = await self._failing_callback(None)

        assert result.status_code == 302
        assert result.headers["location"].startswith(
            "https://lia.example.com/oauth-callback?error="
        )

    async def test_a_refused_consent_never_reaches_the_exchange(self) -> None:
        """Google answers ?error=access_denied with no code at all."""
        from src.domains.auth.oauth_router import google_callback

        auth_service = MagicMock()
        auth_service.handle_google_callback = AsyncMock()

        with (
            patch(f"{ROUTER}.settings") as fake_settings,
            patch(f"{ROUTER}.AuthService", return_value=auth_service),
            patch(f"{ROUTER}.peek_native_challenge", AsyncMock(return_value=_CHALLENGE)),
        ):
            fake_settings.frontend_url = "https://lia.example.com"
            fake_settings.native_app_scheme = "lia"
            result = await google_callback(
                http_request=_fake_request(),
                code=None,
                state="state-token",
                error="access_denied",
                db=AsyncMock(spec=AsyncSession),
            )

        assert result.headers["location"] == "lia://auth-callback?error=access_denied"
        auth_service.handle_google_callback.assert_not_awaited()

    async def test_a_callback_with_no_state_is_refused_without_crashing(self) -> None:
        from src.domains.auth.oauth_router import google_callback

        with (
            patch(f"{ROUTER}.settings") as fake_settings,
            patch(f"{ROUTER}.peek_native_challenge", AsyncMock(return_value=None)) as peek,
        ):
            fake_settings.frontend_url = "https://lia.example.com"
            result = await google_callback(
                http_request=_fake_request(),
                code="auth-code",
                state=None,
                db=AsyncMock(spec=AsyncSession),
            )

        assert result.status_code == 302
        peek.assert_not_awaited()


class TestProviderErrorIsBounded:
    """A provider error is attacker-controlled input; it must not travel raw.

    `error` arrives in the query string, so anything can be put there. Feeding
    it straight into a Prometheus label lets a stranger create unbounded series
    — a metric explosion no rate limit catches — and reflecting it into the
    redirect hands them an echo. Only the known OAuth 2.0 codes pass through.
    """

    @staticmethod
    async def _refused(error: str, native: bool = False):
        from src.domains.auth.oauth_router import google_callback

        with (
            patch(f"{ROUTER}.settings") as fake_settings,
            patch(
                f"{ROUTER}.peek_native_challenge",
                AsyncMock(return_value=_CHALLENGE if native else None),
            ),
            patch(f"{ROUTER}.oauth_callback_errors_total") as errors,
        ):
            fake_settings.frontend_url = "https://lia.example.com"
            fake_settings.native_app_scheme = "lia"
            result = await google_callback(
                http_request=_fake_request(),
                code=None,
                state="state-token",
                error=error,
                db=AsyncMock(spec=AsyncSession),
            )
        return result, errors

    async def test_a_known_code_passes_through(self) -> None:
        result, errors = await self._refused("access_denied")

        assert errors.labels.call_args.kwargs["error_type"] == "access_denied"
        assert "access_denied" in result.headers["location"]

    async def test_an_unknown_value_collapses_to_one_label(self) -> None:
        result, errors = await self._refused("' OR 1=1 -- " + "x" * 500)

        assert errors.labels.call_args.kwargs["error_type"] == "provider_error"
        assert "provider_error" in result.headers["location"]

    async def test_the_raw_value_never_reaches_the_redirect(self) -> None:
        result, _ = await self._refused("javascript:alert(1)")

        assert "javascript" not in result.headers["location"]

    async def test_the_bound_holds_on_the_deep_link_too(self) -> None:
        result, _ = await self._refused("x" * 400, native=True)

        assert result.headers["location"] == "lia://auth-callback?error=provider_error"
