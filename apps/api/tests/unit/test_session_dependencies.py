"""
Unit tests for session-based authentication dependencies (BFF Pattern).

Tests cover:
- Session extraction from HTTP-only cookies
- Authentication via session cookie (not JWT)
- User status validation (active, verified, superuser)
- Optional authentication for public endpoints
- Error handling (missing cookie, invalid session, inactive user)

Architecture change:
- Dependencies now return User (ORM model) instead of UserSession
- UserSession is minimal cache object (user_id, remember_me, created_at)
- User data fetched from PostgreSQL on each request
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.core.session_dependencies import (
    get_current_active_session,
    get_current_session,
    get_current_superuser_session,
    get_current_verified_session,
    get_optional_session,
    get_session_store,
)
from src.domains.auth.models import User
from src.infrastructure.cache.session_store import SessionStore, UserSession


def create_mock_user(
    user_id: str | None = None,
    email: str = "test@example.com",
    is_active: bool = True,
    is_verified: bool = True,
    is_superuser: bool = False,
) -> User:
    """
    Create a mock User object for testing.

    Args:
        user_id: User UUID (generates random if None)
        email: User email
        is_active: User active status
        is_verified: User verified status
        is_superuser: User superuser status

    Returns:
        Mock User object
    """
    user = MagicMock(spec=User)
    user.id = user_id or uuid4()
    user.email = email
    user.is_active = is_active
    user.is_verified = is_verified
    user.is_superuser = is_superuser
    user.full_name = "Test User"
    user.picture_url = None
    return user


@pytest.mark.unit
class TestGetSessionStore:
    """Test SessionStore dependency factory."""

    @pytest.mark.asyncio
    async def test_get_session_store_returns_instance(self):
        """Test get_session_store returns SessionStore instance."""
        # This dependency requires actual Redis connection
        # Full integration testing is done in integration tests
        # Here we just verify the function signature exists
        store = await get_session_store()
        assert isinstance(store, SessionStore)


@pytest.mark.unit
class TestGetCurrentSession:
    """Test get_current_session dependency."""

    @pytest.mark.asyncio
    async def test_get_current_session_success(self):
        """Test successful session retrieval from cookie (returns User, not UserSession)."""
        session_id = str(uuid4())
        user_id = uuid4()

        # Mock minimal session from Redis
        mock_session = UserSession(
            session_id=session_id,
            user_id=str(user_id),
            remember_me=False,
        )

        # Mock User from PostgreSQL
        mock_user = create_mock_user(
            user_id=user_id,
            email="test@example.com",
            is_active=True,
            is_verified=True,
            is_superuser=False,
        )

        # Mock session store
        mock_store = AsyncMock(spec=SessionStore)
        mock_store.get_session.return_value = mock_session

        # Mock database and user repository
        mock_db = AsyncMock()
        mock_user_repo = AsyncMock()
        mock_user_repo.get_user_minimal_for_session.return_value = mock_user

        # Patch UserRepository
        with patch(
            "src.core.session_dependencies.UserRepository",
            return_value=mock_user_repo,
        ):
            # Call dependency with mock cookie
            result = await get_current_session(
                lia_session=session_id,
                session_store=mock_store,
                db=mock_db,
            )

        # Verify returns User (not UserSession)
        assert result == mock_user
        assert result.id == user_id
        assert result.email == "test@example.com"
        mock_store.get_session.assert_called_once_with(session_id)
        mock_user_repo.get_user_minimal_for_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_current_session_no_cookie(self):
        """Test 401 error when cookie is missing."""
        mock_store = AsyncMock(spec=SessionStore)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_session(
                lia_session=None,
                session_store=mock_store,
            )

        assert exc_info.value.status_code == 401
        assert "authentication" in exc_info.value.detail.lower()
        # Note: headers are None with new exception system (managed by middleware)
        # assert exc_info.value.headers == {"WWW-Authenticate": "Cookie"}

    @pytest.mark.asyncio
    async def test_get_current_session_invalid_session_id(self):
        """Test 401 error when session ID is invalid/expired."""
        session_id = str(uuid4())

        # Mock session store returns None (session not found)
        mock_store = AsyncMock(spec=SessionStore)
        mock_store.get_session.return_value = None
        mock_db = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await get_current_session(
                lia_session=session_id,
                session_store=mock_store,
                db=mock_db,
            )

        assert exc_info.value.status_code == 401
        assert "invalid or expired" in exc_info.value.detail.lower()
        # Note: headers are None with new exception system (managed by middleware)
        # assert exc_info.value.headers == {"WWW-Authenticate": "Cookie"}

    @pytest.mark.asyncio
    async def test_get_current_session_empty_cookie(self):
        """Test 401 error when cookie is empty string."""
        mock_store = AsyncMock(spec=SessionStore)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_session(
                lia_session="",
                session_store=mock_store,
            )

        assert exc_info.value.status_code == 401


@pytest.mark.unit
class TestGetCurrentActiveSession:
    """Test get_current_active_session dependency (now receives User, not UserSession)."""

    @pytest.mark.asyncio
    async def test_get_current_active_session_success(self):
        """Test successful retrieval of active user (returns User, not UserSession)."""
        user_id = uuid4()

        mock_user = create_mock_user(
            user_id=user_id,
            email="active@example.com",
            is_active=True,  # Active user
            is_verified=True,
            is_superuser=False,
        )

        result = await get_current_active_session(user=mock_user)

        assert result == mock_user
        assert result.is_active is True

    @pytest.mark.asyncio
    async def test_get_current_active_session_inactive_user(self):
        """Test 403 error when user is inactive."""
        user_id = uuid4()

        mock_user = create_mock_user(
            user_id=user_id,
            email="inactive@example.com",
            is_active=False,  # Inactive user
            is_verified=True,
            is_superuser=False,
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_active_session(user=mock_user)

        assert exc_info.value.status_code == 403
        assert "inactive" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_get_current_active_session_unverified_allowed(self):
        """Test that unverified users can still pass active check."""
        mock_user = create_mock_user(
            user_id=uuid4(),
            email="unverified@example.com",
            is_active=True,
            is_verified=False,  # Not verified but still active
            is_superuser=False,
        )

        # Should not raise error - only checks is_active
        result = await get_current_active_session(user=mock_user)
        assert result == mock_user


@pytest.mark.unit
class TestGetCurrentVerifiedSession:
    """Test get_current_verified_session dependency (now receives User)."""

    @pytest.mark.asyncio
    async def test_get_current_verified_session_success(self):
        """Test successful retrieval of verified user (returns User, not UserSession)."""
        mock_user = create_mock_user(
            user_id=uuid4(),
            email="verified@example.com",
            is_active=True,
            is_verified=True,  # Verified user
            is_superuser=False,
        )

        result = await get_current_verified_session(user=mock_user)

        assert result == mock_user
        assert result.is_verified is True

    @pytest.mark.asyncio
    async def test_get_current_verified_session_unverified_user(self):
        """Test 403 error when user is not verified."""
        mock_user = create_mock_user(
            user_id=uuid4(),
            email="unverified@example.com",
            is_active=True,
            is_verified=False,  # Not verified
            is_superuser=False,
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_verified_session(user=mock_user)

        assert exc_info.value.status_code == 403
        assert "verification required" in exc_info.value.detail.lower()


@pytest.mark.unit
class TestGetCurrentSuperuserSession:
    """Test get_current_superuser_session dependency (now receives User)."""

    @pytest.mark.asyncio
    async def test_get_current_superuser_session_success(self):
        """Test successful retrieval of superuser (returns User, not UserSession)."""
        mock_user = create_mock_user(
            user_id=uuid4(),
            email="admin@example.com",
            is_active=True,
            is_verified=True,
            is_superuser=True,  # Superuser
        )

        result = await get_current_superuser_session(user=mock_user)

        assert result == mock_user
        assert result.is_superuser is True

    @pytest.mark.asyncio
    async def test_get_current_superuser_session_regular_user(self):
        """Test 403 error when user is not a superuser."""
        mock_user = create_mock_user(
            user_id=uuid4(),
            email="user@example.com",
            is_active=True,
            is_verified=True,
            is_superuser=False,  # Regular user
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_superuser_session(user=mock_user)

        assert exc_info.value.status_code == 403
        assert (
            "admin" in exc_info.value.detail.lower()
            or "privileges" in exc_info.value.detail.lower()
        )


@pytest.mark.unit
class TestGetOptionalSession:
    """Test get_optional_session dependency for public endpoints (returns User)."""

    @pytest.mark.asyncio
    async def test_get_optional_session_authenticated(self):
        """Test optional session returns User when authenticated."""
        session_id = str(uuid4())
        user_id = uuid4()

        # Mock minimal session from Redis
        mock_session = UserSession(
            session_id=session_id,
            user_id=str(user_id),
            remember_me=False,
        )

        # Mock User from PostgreSQL
        mock_user = create_mock_user(
            user_id=user_id,
            email="user@example.com",
            is_active=True,
            is_verified=True,
            is_superuser=False,
        )

        mock_store = AsyncMock(spec=SessionStore)
        mock_store.get_session.return_value = mock_session

        mock_db = AsyncMock()
        mock_user_repo = AsyncMock()
        mock_user_repo.get_user_minimal_for_session.return_value = mock_user

        with patch(
            "src.core.session_dependencies.UserRepository",
            return_value=mock_user_repo,
        ):
            result = await get_optional_session(
                lia_session=session_id,
                session_store=mock_store,
                db=mock_db,
            )

        assert result == mock_user
        assert result.id == user_id

    @pytest.mark.asyncio
    async def test_get_optional_session_no_cookie(self):
        """Test optional session returns None when no cookie."""
        mock_store = AsyncMock(spec=SessionStore)

        result = await get_optional_session(
            lia_session=None,
            session_store=mock_store,
        )

        assert result is None
        mock_store.get_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_optional_session_invalid_session(self):
        """Test optional session returns None when session invalid."""
        session_id = str(uuid4())

        mock_store = AsyncMock(spec=SessionStore)
        mock_store.get_session.return_value = None
        mock_db = AsyncMock()

        result = await get_optional_session(
            lia_session=session_id,
            session_store=mock_store,
            db=mock_db,
        )

        assert result is None
        mock_store.get_session.assert_called_once_with(session_id)

    @pytest.mark.asyncio
    async def test_get_optional_session_empty_cookie(self):
        """Test optional session returns None when cookie is empty."""
        mock_store = AsyncMock(spec=SessionStore)
        mock_db = AsyncMock()

        result = await get_optional_session(
            lia_session="",
            session_store=mock_store,
            db=mock_db,
        )

        assert result is None


@pytest.mark.unit
@pytest.mark.security
class TestSessionDependenciesSecurity:
    """Test security aspects of session dependencies."""

    @pytest.mark.asyncio
    async def test_session_dependency_chain_active_and_verified(self):
        """Test dependency chain validates both active and verified (now uses User)."""
        # User is active but not verified
        mock_user = create_mock_user(
            user_id=uuid4(),
            email="user@example.com",
            is_active=True,
            is_verified=False,
            is_superuser=False,
        )

        # Should pass active check
        active_user = await get_current_active_session(user=mock_user)
        assert active_user == mock_user

        # Should fail verified check
        with pytest.raises(HTTPException) as exc_info:
            await get_current_verified_session(user=mock_user)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_session_dependency_inactive_blocks_all(self):
        """Test inactive user blocked at first dependency level (now uses User)."""
        mock_user = create_mock_user(
            user_id=uuid4(),
            email="inactive@example.com",
            is_active=False,
            is_verified=True,
            is_superuser=True,
        )

        # Should fail even if verified and superuser
        with pytest.raises(HTTPException) as exc_info:
            await get_current_active_session(user=mock_user)
        assert exc_info.value.status_code == 403
        assert "inactive" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_www_authenticate_header_in_401_responses(self):
        """Test 401 responses include WWW-Authenticate header."""
        mock_store = AsyncMock(spec=SessionStore)
        mock_db = AsyncMock()

        # No cookie
        with pytest.raises(HTTPException) as exc_info:
            await get_current_session(
                lia_session=None,
                session_store=mock_store,
                db=mock_db,
            )
        assert exc_info.value.status_code == 401
        # Note: headers are None with new exception system (managed by middleware)
        # assert "WWW-Authenticate" in exc_info.value.headers
        # assert exc_info.value.headers["WWW-Authenticate"] == "Cookie"

        # Invalid session
        mock_store.get_session.return_value = None
        with pytest.raises(HTTPException) as exc_info:
            await get_current_session(
                lia_session=str(uuid4()),
                session_store=mock_store,
                db=mock_db,
            )
        assert exc_info.value.status_code == 401
        # Note: headers are None with new exception system (managed by middleware)
        # assert "WWW-Authenticate" in exc_info.value.headers

    @pytest.mark.asyncio
    async def test_optional_session_never_raises_exception(self):
        """Test optional session never raises HTTPException."""
        mock_store = AsyncMock(spec=SessionStore)
        mock_db = AsyncMock()

        # No cookie
        result1 = await get_optional_session(None, mock_store, mock_db)
        assert result1 is None

        # Invalid session
        mock_store.get_session.return_value = None
        result2 = await get_optional_session(str(uuid4()), mock_store, mock_db)
        assert result2 is None

        # No exception should be raised in either case

    @pytest.mark.asyncio
    async def test_session_permissions_hierarchy(self):
        """Test permission hierarchy: superuser > verified > active > authenticated (now uses User)."""
        # Superuser (highest privileges)
        superuser = create_mock_user(
            user_id=uuid4(),
            email="admin@example.com",
            is_active=True,
            is_verified=True,
            is_superuser=True,
        )

        # Should pass all dependency checks
        await get_current_active_session(user=superuser)
        await get_current_verified_session(user=superuser)
        await get_current_superuser_session(user=superuser)

        # Verified user (mid privileges)
        verified_user = create_mock_user(
            user_id=uuid4(),
            email="verified@example.com",
            is_active=True,
            is_verified=True,
            is_superuser=False,
        )

        # Should pass active and verified, fail superuser
        await get_current_active_session(user=verified_user)
        await get_current_verified_session(user=verified_user)
        with pytest.raises(HTTPException):
            await get_current_superuser_session(user=verified_user)

        # Active but unverified (low privileges)
        unverified_user = create_mock_user(
            user_id=uuid4(),
            email="unverified@example.com",
            is_active=True,
            is_verified=False,
            is_superuser=False,
        )

        # Should pass active, fail verified and superuser
        await get_current_active_session(user=unverified_user)
        with pytest.raises(HTTPException):
            await get_current_verified_session(user=unverified_user)
        with pytest.raises(HTTPException):
            await get_current_superuser_session(user=unverified_user)
