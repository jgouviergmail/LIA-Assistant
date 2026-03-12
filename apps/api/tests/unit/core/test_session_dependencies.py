"""
Unit tests for session-based authentication dependencies.

Phase: PHASE 4.1 - Coverage Baseline & Tests Unitaires
Session: 26
Created: 2025-11-21
Target: 31% → 80%+ coverage
Module: core/session_dependencies.py (58 statements)

Missing Lines to Cover:
- Line 92: raise_user_not_authenticated() - No cookie
- Line 101: raise_session_invalid() - Session not found in Redis
- Lines 110-118: Orphan session cleanup (user deleted)
- Line 162: raise_user_inactive() - Inactive user
- Line 189: raise_user_not_verified() - Unverified email
- Line 216: raise_admin_required() - Non-superuser
- Lines 242-247: Optional session - no cookie/no session
- Lines 253-267: Optional session - user found/orphan cleanup

Security-Critical Module:
- Session-based authentication (GDPR/OWASP compliant)
- BFF pattern with HTTP-only cookies
- No PII in Redis (minimal sessions)
- PostgreSQL as single source of truth
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from src.core.session_dependencies import (
    get_current_active_session,
    get_current_session,
    get_current_superuser_session,
    get_current_verified_session,
    get_optional_session,
    get_session_store,
)
from src.domains.auth.models import User
from src.infrastructure.cache.session_store import UserSession


class TestGetSessionStore:
    """Tests for get_session_store dependency."""

    @pytest.mark.asyncio
    @patch("src.core.session_dependencies.get_redis_session")
    async def test_get_session_store_returns_session_store(self, mock_get_redis_session):
        """Test that get_session_store returns SessionStore instance (Lines 53-54)."""
        # Mock Redis connection
        mock_redis = AsyncMock()
        mock_get_redis_session.return_value = mock_redis

        # Lines 53-54 executed: Get Redis + create SessionStore
        result = await get_session_store()

        # Verify SessionStore created with Redis
        assert result is not None
        assert hasattr(result, "get_session")
        assert hasattr(result, "delete_session")
        mock_get_redis_session.assert_called_once()


class TestGetCurrentSession:
    """Tests for get_current_session dependency (main authentication)."""

    @pytest.mark.asyncio
    async def test_get_current_session_no_cookie_raises_401(self):
        """Test authentication required when no cookie provided (Line 92)."""
        mock_session_store = AsyncMock()
        mock_db = AsyncMock()

        # Line 92 executed: raise_user_not_authenticated()
        with pytest.raises(Exception) as exc_info:
            await get_current_session(
                lia_session=None,
                session_store=mock_session_store,
                db=mock_db,
            )

        # Verify 401 Unauthorized
        assert exc_info.value.status_code == 401
        assert "authentication" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_get_current_session_invalid_session_raises_401(self):
        """Test session invalid when not found in Redis (Line 101)."""
        mock_session_store = AsyncMock()
        mock_session_store.get_session = AsyncMock(return_value=None)
        mock_db = AsyncMock()

        # Line 101 executed: raise_session_invalid()
        with pytest.raises(Exception) as exc_info:
            await get_current_session(
                lia_session="invalid_session_id",
                session_store=mock_session_store,
                db=mock_db,
            )

        # Verify 401 Unauthorized
        assert exc_info.value.status_code == 401
        assert "session" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    @patch("src.core.session_dependencies.UserRepository")
    async def test_get_current_session_orphan_session_cleanup(self, mock_user_repo_class):
        """Test orphan session cleanup when user deleted (Lines 110-118)."""
        # Mock session exists in Redis
        session_id = "session_123"
        user_id = str(uuid.uuid4())
        mock_session = UserSession(
            session_id=session_id,
            user_id=user_id,
            remember_me=False,
        )

        mock_session_store = AsyncMock()
        mock_session_store.get_session = AsyncMock(return_value=mock_session)
        mock_session_store.delete_session = AsyncMock()

        # Mock user NOT found in DB (orphan session)
        mock_user_repo = AsyncMock()
        mock_user_repo.get_user_minimal_for_session = AsyncMock(return_value=None)
        mock_user_repo_class.return_value = mock_user_repo

        mock_db = AsyncMock()

        # Lines 110-118 executed: Orphan session cleanup
        with pytest.raises(Exception) as exc_info:
            await get_current_session(
                lia_session=session_id,
                session_store=mock_session_store,
                db=mock_db,
            )

        # Verify session deleted
        mock_session_store.delete_session.assert_called_once_with(session_id)

        # Verify 401 raised
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch("src.core.session_dependencies.UserRepository")
    async def test_get_current_session_success_returns_user(self, mock_user_repo_class):
        """Test successful authentication returns User object (Lines 98-132)."""
        # Mock session exists in Redis
        session_id = "session_456"
        user_id = uuid.uuid4()
        mock_session = UserSession(
            session_id=session_id,
            user_id=str(user_id),
            remember_me=True,
        )

        mock_session_store = AsyncMock()
        mock_session_store.get_session = AsyncMock(return_value=mock_session)

        # Mock user found in DB
        mock_user = User(
            id=user_id,
            email="user@example.com",
            hashed_password="hashed_pw",
            is_active=True,
            is_verified=True,
            is_superuser=False,
        )

        mock_user_repo = AsyncMock()
        mock_user_repo.get_user_minimal_for_session = AsyncMock(return_value=mock_user)
        mock_user_repo_class.return_value = mock_user_repo

        mock_db = AsyncMock()

        # Lines 98-132 executed: Session validated + user fetched
        result = await get_current_session(
            lia_session=session_id,
            session_store=mock_session_store,
            db=mock_db,
        )

        # Verify User returned
        assert result == mock_user
        assert result.id == user_id
        assert result.email == "user@example.com"
        assert result.is_active is True

        # Verify repository called
        mock_user_repo.get_user_minimal_for_session.assert_called_once_with(user_id)


class TestGetCurrentActiveSession:
    """Tests for get_current_active_session dependency."""

    @pytest.mark.asyncio
    async def test_get_current_active_session_inactive_user_raises_403(self):
        """Test inactive user raises 403 Forbidden (Line 162)."""
        # Mock inactive user
        user_id = uuid.uuid4()
        mock_user = User(
            id=user_id,
            email="inactive@example.com",
            hashed_password="hashed_pw",
            is_active=False,  # INACTIVE
            is_verified=True,
            is_superuser=False,
        )

        # Line 162 executed: raise_user_inactive()
        with pytest.raises(Exception) as exc_info:
            await get_current_active_session(user=mock_user)

        # Verify 403 Forbidden
        assert exc_info.value.status_code == 403
        assert "inactive" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_get_current_active_session_active_user_returns_user(self):
        """Test active user returns User object (Lines 161-164)."""
        # Mock active user
        user_id = uuid.uuid4()
        mock_user = User(
            id=user_id,
            email="active@example.com",
            hashed_password="hashed_pw",
            is_active=True,  # ACTIVE
            is_verified=True,
            is_superuser=False,
        )

        # Lines 161-164 executed: User returned
        result = await get_current_active_session(user=mock_user)

        # Verify same user returned
        assert result == mock_user
        assert result.is_active is True


class TestGetCurrentVerifiedSession:
    """Tests for get_current_verified_session dependency."""

    @pytest.mark.asyncio
    async def test_get_current_verified_session_unverified_user_raises_403(self):
        """Test unverified user raises 403 Forbidden (Line 189)."""
        # Mock unverified user
        user_id = uuid.uuid4()
        mock_user = User(
            id=user_id,
            email="unverified@example.com",
            hashed_password="hashed_pw",
            is_active=True,
            is_verified=False,  # UNVERIFIED
            is_superuser=False,
        )

        # Line 189 executed: raise_user_not_verified()
        with pytest.raises(Exception) as exc_info:
            await get_current_verified_session(user=mock_user)

        # Verify 403 Forbidden
        assert exc_info.value.status_code == 403
        assert "verification" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_get_current_verified_session_verified_user_returns_user(self):
        """Test verified user returns User object (Lines 188-191)."""
        # Mock verified user
        user_id = uuid.uuid4()
        mock_user = User(
            id=user_id,
            email="verified@example.com",
            hashed_password="hashed_pw",
            is_active=True,
            is_verified=True,  # VERIFIED
            is_superuser=False,
        )

        # Lines 188-191 executed: User returned
        result = await get_current_verified_session(user=mock_user)

        # Verify same user returned
        assert result == mock_user
        assert result.is_verified is True


class TestGetCurrentSuperuserSession:
    """Tests for get_current_superuser_session dependency."""

    @pytest.mark.asyncio
    async def test_get_current_superuser_session_non_superuser_raises_403(self):
        """Test non-superuser raises 403 Forbidden (Line 216)."""
        # Mock regular user (not superuser)
        user_id = uuid.uuid4()
        mock_user = User(
            id=user_id,
            email="regular@example.com",
            hashed_password="hashed_pw",
            is_active=True,
            is_verified=True,
            is_superuser=False,  # NOT SUPERUSER
        )

        # Line 216 executed: raise_admin_required()
        with pytest.raises(Exception) as exc_info:
            await get_current_superuser_session(user=mock_user)

        # Verify 403 Forbidden
        assert exc_info.value.status_code == 403
        assert (
            "admin" in str(exc_info.value.detail).lower()
            or "superuser" in str(exc_info.value.detail).lower()
        )

    @pytest.mark.asyncio
    async def test_get_current_superuser_session_superuser_returns_user(self):
        """Test superuser returns User object (Lines 215-218)."""
        # Mock superuser
        user_id = uuid.uuid4()
        mock_user = User(
            id=user_id,
            email="admin@example.com",
            hashed_password="hashed_pw",
            is_active=True,
            is_verified=True,
            is_superuser=True,  # SUPERUSER
        )

        # Lines 215-218 executed: User returned
        result = await get_current_superuser_session(user=mock_user)

        # Verify same user returned
        assert result == mock_user
        assert result.is_superuser is True


class TestGetOptionalSession:
    """Tests for get_optional_session dependency (optional auth)."""

    @pytest.mark.asyncio
    async def test_get_optional_session_no_cookie_returns_none(self):
        """Test no cookie returns None (Line 243)."""
        mock_session_store = AsyncMock()
        mock_db = AsyncMock()

        # Line 243 executed: return None
        result = await get_optional_session(
            lia_session=None,
            session_store=mock_session_store,
            db=mock_db,
        )

        # Verify None returned (no exception)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_optional_session_invalid_session_returns_none(self):
        """Test invalid session returns None (Lines 245-247)."""
        mock_session_store = AsyncMock()
        mock_session_store.get_session = AsyncMock(return_value=None)
        mock_db = AsyncMock()

        # Lines 245-247 executed: return None
        result = await get_optional_session(
            lia_session="invalid_session",
            session_store=mock_session_store,
            db=mock_db,
        )

        # Verify None returned (no exception)
        assert result is None

    @pytest.mark.asyncio
    @patch("src.core.session_dependencies.UserRepository")
    async def test_get_optional_session_user_found_returns_user(self, mock_user_repo_class):
        """Test valid session with user returns User object (Lines 245-259)."""
        # Mock session exists in Redis
        session_id = "session_789"
        user_id = uuid.uuid4()
        mock_session = UserSession(
            session_id=session_id,
            user_id=str(user_id),
            remember_me=False,
        )

        mock_session_store = AsyncMock()
        mock_session_store.get_session = AsyncMock(return_value=mock_session)

        # Mock user found in DB
        mock_user = User(
            id=user_id,
            email="optional@example.com",
            hashed_password="hashed_pw",
            is_active=True,
            is_verified=True,
            is_superuser=False,
        )

        mock_user_repo = AsyncMock()
        mock_user_repo.get_user_minimal_for_session = AsyncMock(return_value=mock_user)
        mock_user_repo_class.return_value = mock_user_repo

        mock_db = AsyncMock()

        # Lines 245-259 executed: User found and returned
        result = await get_optional_session(
            lia_session=session_id,
            session_store=mock_session_store,
            db=mock_db,
        )

        # Verify User returned
        assert result == mock_user
        assert result.email == "optional@example.com"

    @pytest.mark.asyncio
    @patch("src.core.session_dependencies.UserRepository")
    async def test_get_optional_session_orphan_cleanup_returns_none(self, mock_user_repo_class):
        """Test orphan session cleanup returns None (Lines 260-267)."""
        # Mock session exists in Redis
        session_id = "session_orphan"
        user_id = str(uuid.uuid4())
        mock_session = UserSession(
            session_id=session_id,
            user_id=user_id,
            remember_me=False,
        )

        mock_session_store = AsyncMock()
        mock_session_store.get_session = AsyncMock(return_value=mock_session)
        mock_session_store.delete_session = AsyncMock()

        # Mock user NOT found in DB (orphan session)
        mock_user_repo = AsyncMock()
        mock_user_repo.get_user_minimal_for_session = AsyncMock(return_value=None)
        mock_user_repo_class.return_value = mock_user_repo

        mock_db = AsyncMock()

        # Lines 260-267 executed: Orphan session cleanup
        result = await get_optional_session(
            lia_session=session_id,
            session_store=mock_session_store,
            db=mock_db,
        )

        # Verify session deleted
        mock_session_store.delete_session.assert_called_once_with(session_id)

        # Verify None returned (no exception, unlike get_current_session)
        assert result is None
