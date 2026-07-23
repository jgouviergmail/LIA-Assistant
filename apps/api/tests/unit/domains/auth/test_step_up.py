"""Unit tests for step-up re-authentication (security program D1, Lot 3).

Covers the session-payload v3 round-trip, the freshness dependency and its
typed 403 contract (NEVER a plain 401 — the frontend hard-redirects 401s),
the verification endpoints, and the A8 password-disabling guard rails.
"""

import json
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.core.constants import STEP_UP_ERROR_CODE
from src.core.session_dependencies import require_recent_step_up
from src.domains.auth.schemas import StepUpPasswordRequest
from src.infrastructure.cache.session_store import SessionStore, UserSession
from src.infrastructure.database.registry import import_all_models

import_all_models()


def _session(step_up_at: datetime | None) -> UserSession:
    return UserSession(
        session_id=str(uuid.uuid4()),
        user_id=str(uuid.uuid4()),
        auth_methods=["password"],
        step_up_at=step_up_at,
    )


@pytest.mark.unit
class TestSessionPayloadV3:
    """step_up_at survives the Redis round-trip; legacy payloads default."""

    def test_roundtrip_preserves_step_up_at(self) -> None:
        """to_dict → from_dict keeps the step-up timestamp."""
        now = datetime.now(UTC)
        restored = UserSession.from_dict("sid", _session(step_up_at=now).to_dict())
        assert restored.step_up_at == now

    def test_legacy_payload_defaults_to_none(self) -> None:
        """Pre-v3 payloads (no step_up_at key) keep validating."""
        payload = {
            "user_id": str(uuid.uuid4()),
            "remember_me": False,
            "created_at": datetime.now(UTC).isoformat(),
        }
        restored = UserSession.from_dict("sid", payload)
        assert restored.step_up_at is None

    async def test_mark_step_up_preserves_ttl(self) -> None:
        """mark_step_up rewrites the payload with keepttl (never extends)."""
        redis = AsyncMock()
        session = _session(step_up_at=None)
        redis.get = AsyncMock(return_value=json.dumps(session.to_dict()))
        redis.set = AsyncMock()
        store = SessionStore(redis)

        updated = await store.mark_step_up(session.session_id)

        assert updated is True
        set_kwargs = redis.set.call_args.kwargs
        assert set_kwargs["keepttl"] is True

    async def test_mark_step_up_unknown_session(self) -> None:
        """A vanished session cannot be marked."""
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        store = SessionStore(redis)

        assert await store.mark_step_up("gone") is False


@pytest.mark.unit
class TestRequireRecentStepUp:
    """Freshness dependency: fresh passes, stale/absent → typed 403."""

    def _store_with(self, session: UserSession | None) -> MagicMock:
        store = MagicMock()
        store.get_session = AsyncMock(return_value=session)
        return store

    async def test_fresh_step_up_passes(self) -> None:
        """A step-up inside the window returns the user."""
        user = MagicMock()
        session = _session(step_up_at=datetime.now(UTC) - timedelta(seconds=10))

        result = await require_recent_step_up(
            lia_session=session.session_id,
            user=user,
            session_store=self._store_with(session),
        )
        assert result is user

    async def test_never_stepped_up_raises_typed_403(self) -> None:
        """No step-up on the session → 403 with the step-up contract."""
        session = _session(step_up_at=None)

        with pytest.raises(HTTPException) as exc_info:
            await require_recent_step_up(
                lia_session=session.session_id,
                user=MagicMock(),
                session_store=self._store_with(session),
            )

        assert exc_info.value.status_code == 403
        assert isinstance(exc_info.value.detail, dict)
        assert exc_info.value.detail["error"] == STEP_UP_ERROR_CODE

    async def test_expired_step_up_raises_typed_403(self) -> None:
        """A step-up older than the window is stale."""
        from src.core.config import settings

        stale = datetime.now(UTC) - timedelta(seconds=settings.step_up_window_seconds + 5)
        session = _session(step_up_at=stale)

        with pytest.raises(HTTPException) as exc_info:
            await require_recent_step_up(
                lia_session=session.session_id,
                user=MagicMock(),
                session_store=self._store_with(session),
            )
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["error"] == STEP_UP_ERROR_CODE  # type: ignore[index]


@pytest.mark.unit
class TestStepUpStatus:
    """GET /auth/step-up/status: methods reflect what the account can use."""

    async def test_oauth_only_account_gets_oauth_method(self) -> None:
        """No password, no MFA factor → the identity provider IS the method.

        This is the anti-deadlock guarantee: an OAuth-only account must
        always see at least one way to satisfy a step-up challenge.
        """
        from src.domains.auth.step_up_router import step_up_status

        user = MagicMock()
        user.hashed_password = None
        user.oauth_provider = "google"

        with patch("src.domains.auth.step_up_router.settings") as mock_settings:
            mock_settings.mfa_enabled = False
            result = await step_up_status(
                user=user,
                db=AsyncMock(),
                store=MagicMock(),
                lia_session=None,
            )

        assert result.methods == ["oauth_google"]
        assert result.password_set is False

    async def test_password_account_without_provider(self) -> None:
        """Classic password account: password only (MFA off)."""
        from src.domains.auth.step_up_router import step_up_status

        user = MagicMock()
        user.hashed_password = "hashed"
        user.oauth_provider = None

        with patch("src.domains.auth.step_up_router.settings") as mock_settings:
            mock_settings.mfa_enabled = False
            result = await step_up_status(
                user=user,
                db=AsyncMock(),
                store=MagicMock(),
                lia_session=None,
            )

        assert result.methods == ["password"]
        assert result.password_set is True


@pytest.mark.unit
class TestStepUpPasswordEndpoint:
    """POST /auth/step-up/password: verify + mark, generic 401 on mismatch."""

    async def test_valid_password_marks_session(self) -> None:
        """Correct password → session marked, horizon returned."""
        from src.domains.auth.step_up_router import step_up_password

        user = MagicMock()
        user.hashed_password = "hashed"
        store = MagicMock()
        store.mark_step_up = AsyncMock(return_value=True)

        with patch("src.domains.auth.step_up_router.verify_password", return_value=True):
            result = await step_up_password(
                data=StepUpPasswordRequest(password="pw"),
                user=user,
                store=store,
                lia_session="sid",
                _rate_limit=None,
            )

        store.mark_step_up.assert_awaited_once_with("sid")
        assert result.step_up_valid_until > datetime.now(UTC)

    async def test_wrong_password_rejects_401(self) -> None:
        """Wrong password → generic 401, session untouched."""
        from src.domains.auth.step_up_router import step_up_password

        user = MagicMock()
        user.hashed_password = "hashed"
        store = MagicMock()
        store.mark_step_up = AsyncMock()

        with patch("src.domains.auth.step_up_router.verify_password", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                await step_up_password(
                    data=StepUpPasswordRequest(password="wrong"),
                    user=user,
                    store=store,
                    lia_session="sid",
                    _rate_limit=None,
                )

        assert exc_info.value.status_code == 401
        store.mark_step_up.assert_not_awaited()

    async def test_passwordless_account_rejects_401(self) -> None:
        """A password-less (OAuth/passkey-only) account cannot use this path."""
        from src.domains.auth.step_up_router import step_up_password

        user = MagicMock()
        user.hashed_password = None

        with pytest.raises(HTTPException) as exc_info:
            await step_up_password(
                data=StepUpPasswordRequest(password="anything"),
                user=user,
                store=MagicMock(),
                lia_session="sid",
                _rate_limit=None,
            )
        assert exc_info.value.status_code == 401


@pytest.mark.unit
class TestDisablePassword:
    """POST /auth/password/disable — A8 guard rails."""

    async def test_requires_two_passkeys(self) -> None:
        """< 2 passkeys → 400, password untouched."""
        from src.domains.auth.step_up_router import disable_password

        user = MagicMock()
        user.hashed_password = "hashed"
        service = MagicMock()
        service.list_credentials = AsyncMock(return_value=[MagicMock()])  # only one

        with (
            patch("src.domains.auth.step_up_router.settings") as mock_settings,
            patch("src.domains.auth.step_up_router.WebAuthnService", return_value=service),
        ):
            mock_settings.mfa_enabled = True
            with pytest.raises(HTTPException) as exc_info:
                await disable_password(
                    user=user,
                    db=AsyncMock(),
                    _rate_limit=None,
                )

        assert exc_info.value.status_code == 400
        assert user.hashed_password == "hashed"

    async def test_disables_with_two_passkeys(self) -> None:
        """≥ 2 passkeys + fresh step-up → password scrubbed."""
        from src.domains.auth.step_up_router import disable_password

        user = MagicMock()
        user.hashed_password = "hashed"
        user.id = uuid.uuid4()
        db = AsyncMock()
        db.add = MagicMock()
        service = MagicMock()
        service.list_credentials = AsyncMock(return_value=[MagicMock(), MagicMock()])

        with (
            patch("src.domains.auth.step_up_router.settings") as mock_settings,
            patch("src.domains.auth.step_up_router.WebAuthnService", return_value=service),
        ):
            mock_settings.mfa_enabled = True
            await disable_password(user=user, db=db, _rate_limit=None)

        assert user.hashed_password is None
        db.commit.assert_awaited()

    async def test_already_disabled_rejects(self) -> None:
        """Idempotence guard: nothing to disable → 400."""
        from src.domains.auth.step_up_router import disable_password

        user = MagicMock()
        user.hashed_password = None

        with pytest.raises(HTTPException) as exc_info:
            await disable_password(user=user, db=AsyncMock(), _rate_limit=None)
        assert exc_info.value.status_code == 400
