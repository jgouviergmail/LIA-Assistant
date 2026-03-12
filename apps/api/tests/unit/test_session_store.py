"""
Unit tests for SessionStore (BFF Pattern session management).

Tests cover:
- Session creation with UUID generation
- Session retrieval and TTL refresh
- Session deletion (single and all user sessions)
- Session data serialization/deserialization (including UUID handling)
- Session updates and field validation
- Error handling for corrupted data
"""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from src.infrastructure.cache.session_store import SessionStore, UserSession


@pytest.mark.unit
class TestUserSession:
    """Test UserSession data structure."""

    def test_user_session_init_with_defaults(self):
        """Test UserSession initialization with default values (minimal session)."""
        session_id = str(uuid4())
        user_id = str(uuid4())

        session = UserSession(
            session_id=session_id,
            user_id=user_id,
        )

        assert session.session_id == session_id
        assert session.user_id == user_id
        assert session.remember_me is False
        assert isinstance(session.created_at, datetime)

    def test_user_session_init_with_all_fields(self):
        """Test UserSession initialization with all fields (minimal session)."""
        session_id = str(uuid4())
        user_id = str(uuid4())
        created_at = datetime.now(UTC)

        session = UserSession(
            session_id=session_id,
            user_id=user_id,
            remember_me=True,
            created_at=created_at,
        )

        assert session.session_id == session_id
        assert session.user_id == user_id
        assert session.remember_me is True
        assert session.created_at == created_at

    def test_to_dict_converts_uuid_to_string(self):
        """Test to_dict() converts UUID to string for JSON serialization (minimal session)."""
        session_id = str(uuid4())
        user_id = str(uuid4())  # UUID as string (from DB)

        session = UserSession(
            session_id=session_id,
            user_id=user_id,
            remember_me=True,
        )

        data = session.to_dict()

        # Verify UUID is converted to string
        assert isinstance(data["user_id"], str)
        assert data["user_id"] == user_id
        assert data["remember_me"] is True

        # Verify datetime is converted to ISO format
        assert isinstance(data["created_at"], str)

        # Verify JSON serializable
        json_str = json.dumps(data)
        assert isinstance(json_str, str)

    def test_to_dict_with_remember_me(self):
        """Test to_dict() with remember_me flag (minimal session)."""
        session_id = str(uuid4())
        user_id = str(uuid4())

        session = UserSession(
            session_id=session_id,
            user_id=user_id,
            remember_me=True,
        )

        data = session.to_dict()

        assert data["user_id"] == user_id
        assert data["remember_me"] is True
        assert "created_at" in data

    def test_from_dict_deserializes_correctly(self):
        """Test from_dict() deserializes session data correctly (minimal session)."""
        session_id = str(uuid4())
        user_id = str(uuid4())
        created_at = datetime.now(UTC)

        data = {
            "user_id": user_id,
            "remember_me": True,
            "created_at": created_at.isoformat(),
        }

        session = UserSession.from_dict(session_id, data)

        assert session.session_id == session_id
        assert session.user_id == user_id
        assert session.remember_me is True
        assert isinstance(session.created_at, datetime)

    def test_from_dict_with_optional_fields_missing(self):
        """Test from_dict() handles missing optional fields (minimal session)."""
        session_id = str(uuid4())
        user_id = str(uuid4())
        created_at = datetime.now(UTC)

        data = {
            "user_id": user_id,
            "created_at": created_at.isoformat(),
        }

        session = UserSession.from_dict(session_id, data)

        assert session.session_id == session_id
        assert session.user_id == user_id
        assert session.remember_me is False  # Default

    def test_roundtrip_to_dict_from_dict(self):
        """Test roundtrip serialization/deserialization (minimal session)."""
        session_id = str(uuid4())
        original = UserSession(
            session_id=session_id,
            user_id=str(uuid4()),
            remember_me=True,
        )

        # Serialize
        data = original.to_dict()

        # Deserialize
        restored = UserSession.from_dict(session_id, data)

        # Compare (excluding datetime precision)
        assert restored.session_id == original.session_id
        assert restored.user_id == original.user_id
        assert restored.remember_me == original.remember_me


@pytest.mark.unit
class TestSessionStore:
    """Test SessionStore Redis operations."""

    @pytest.mark.asyncio
    async def test_create_session(self):
        """Test session creation with Redis storage (minimal session)."""
        mock_redis = AsyncMock()
        store = SessionStore(mock_redis)

        user_id = str(uuid4())

        session = await store.create_session(
            user_id=user_id,
            remember_me=False,
        )

        # Verify session created with UUID
        assert isinstance(session.session_id, str)
        assert len(session.session_id) == 36  # UUID length with hyphens
        assert session.user_id == user_id
        assert session.remember_me is False

        # Verify Redis setex was called
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == f"session:{session.session_id}"  # key
        assert isinstance(call_args[0][1], int)  # TTL
        assert isinstance(call_args[0][2], str)  # JSON data

        # Verify JSON data is valid
        stored_data = json.loads(call_args[0][2])
        assert stored_data["user_id"] == user_id
        assert stored_data["remember_me"] is False

    @pytest.mark.asyncio
    async def test_create_session_with_remember_me(self):
        """Test session creation with remember_me flag (minimal session)."""
        mock_redis = AsyncMock()
        store = SessionStore(mock_redis)

        user_id = str(uuid4())

        session = await store.create_session(
            user_id=user_id,
            remember_me=True,
        )

        assert session.remember_me is True

        # Verify stored data contains remember_me
        stored_json = mock_redis.setex.call_args[0][2]
        stored_data = json.loads(stored_json)
        assert stored_data["remember_me"] is True

    @pytest.mark.asyncio
    async def test_get_session_success(self):
        """Test retrieving existing session from Redis (minimal session)."""
        mock_redis = AsyncMock()
        store = SessionStore(mock_redis)

        session_id = str(uuid4())
        user_id = str(uuid4())
        session_data = {
            "user_id": user_id,
            "remember_me": False,
            "created_at": datetime.now(UTC).isoformat(),
        }

        mock_redis.get.return_value = json.dumps(session_data)

        session = await store.get_session(session_id)

        assert session is not None
        assert session.session_id == session_id
        assert session.user_id == user_id
        assert session.remember_me is False

        # Verify Redis get was called
        mock_redis.get.assert_called_once_with(f"session:{session_id}")

    @pytest.mark.asyncio
    async def test_get_session_not_found(self):
        """Test retrieving non-existent session returns None."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        store = SessionStore(mock_redis)

        session_id = str(uuid4())
        session = await store.get_session(session_id)

        assert session is None
        mock_redis.get.assert_called_once_with(f"session:{session_id}")

    @pytest.mark.asyncio
    async def test_get_session_corrupted_data(self):
        """Test retrieving session with corrupted JSON data."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = "invalid-json-data"
        store = SessionStore(mock_redis)

        session_id = str(uuid4())
        session = await store.get_session(session_id)

        # Should return None and delete corrupted session
        assert session is None
        mock_redis.delete.assert_called_once_with(f"session:{session_id}")

    @pytest.mark.asyncio
    async def test_get_session_preserves_created_at(self):
        """Test get_session preserves created_at timestamp (minimal session)."""
        mock_redis = AsyncMock()
        store = SessionStore(mock_redis)

        session_id = str(uuid4())
        old_timestamp = datetime.now(UTC) - timedelta(hours=1)
        session_data = {
            "user_id": str(uuid4()),
            "remember_me": True,
            "created_at": old_timestamp.isoformat(),
        }

        mock_redis.get.return_value = json.dumps(session_data)

        session = await store.get_session(session_id)

        # Verify created_at was preserved
        assert session is not None
        assert abs((session.created_at - old_timestamp).total_seconds()) < 1

    @pytest.mark.asyncio
    async def test_delete_session_success(self):
        """Test deleting existing session (with deindexing)."""
        mock_redis = AsyncMock()
        store = SessionStore(mock_redis)

        user_id = str(uuid4())
        session_id = str(uuid4())

        # Mock get_session to return session with user_id
        session_data = {
            "user_id": user_id,
            "remember_me": False,
            "created_at": datetime.now(UTC).isoformat(),
        }
        mock_redis.get.return_value = json.dumps(session_data)
        mock_redis.delete.return_value = 1  # Redis returns count of deleted keys
        mock_redis.srem.return_value = 1  # Deindexing successful

        result = await store.delete_session(session_id)

        assert result is True
        mock_redis.delete.assert_called_once_with(f"session:{session_id}")
        # Verify deindexing was called
        mock_redis.srem.assert_called_once_with(f"user:{user_id}:sessions", session_id)

    @pytest.mark.asyncio
    async def test_delete_session_not_found(self):
        """Test deleting non-existent session (no deindexing attempted)."""
        mock_redis = AsyncMock()
        store = SessionStore(mock_redis)

        session_id = str(uuid4())

        # Mock get_session to return None (session not found)
        mock_redis.get.return_value = None
        mock_redis.delete.return_value = 0  # No keys deleted

        result = await store.delete_session(session_id)

        assert result is False
        # Verify deindexing was NOT attempted (no session found)
        mock_redis.srem.assert_not_called()

    # ========================================================================
    # REMOVED: test_delete_all_user_sessions (obsolete)
    # ========================================================================
    # This test used old O(N) scan implementation (pre-indexing).
    # Now fully covered by TestSessionStoreIndexing class which tests
    # the new O(1) index-based implementation.
    # ========================================================================

    @pytest.mark.asyncio
    async def test_refresh_session_success(self):
        """Test refreshing session TTL (minimal session)."""
        mock_redis = AsyncMock()
        store = SessionStore(mock_redis)

        session_id = str(uuid4())
        user_id = str(uuid4())
        session_data = {
            "user_id": user_id,
            "remember_me": True,
            "created_at": datetime.now(UTC).isoformat(),
        }

        mock_redis.get.return_value = json.dumps(session_data)

        result = await store.refresh_session(session_id)

        assert result is True
        mock_redis.get.assert_called_once_with(f"session:{session_id}")
        mock_redis.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_session_not_found(self):
        """Test refreshing non-existent session (minimal session)."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None  # Session does not exist
        store = SessionStore(mock_redis)

        session_id = str(uuid4())
        result = await store.refresh_session(session_id)

        assert result is False
        mock_redis.expire.assert_not_called()


@pytest.mark.unit
@pytest.mark.security
class TestSessionStoreSecurity:
    """Test security aspects of SessionStore."""

    @pytest.mark.asyncio
    async def test_session_id_is_uuid_v4(self):
        """Test session IDs are valid UUID v4 (minimal session)."""
        mock_redis = AsyncMock()
        store = SessionStore(mock_redis)

        session = await store.create_session(
            user_id=str(uuid4()),
            remember_me=False,
        )

        # Verify it's a valid UUID
        try:
            session_uuid = UUID(session.session_id, version=4)
            assert str(session_uuid) == session.session_id
        except ValueError:
            pytest.fail("Session ID is not a valid UUID v4")

    @pytest.mark.asyncio
    async def test_session_ids_are_unique(self):
        """Test that multiple sessions generate unique IDs (minimal session)."""
        mock_redis = AsyncMock()
        store = SessionStore(mock_redis)

        user_id = str(uuid4())
        sessions = []

        for _ in range(10):
            session = await store.create_session(
                user_id=user_id,
                remember_me=False,
            )
            sessions.append(session.session_id)

        # All session IDs should be unique
        assert len(sessions) == len(set(sessions))

    @pytest.mark.asyncio
    async def test_corrupted_session_data_is_deleted(self):
        """Test that corrupted session data triggers deletion."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = "corrupted-json-{invalid"
        store = SessionStore(mock_redis)

        session_id = str(uuid4())
        session = await store.get_session(session_id)

        # Should return None
        assert session is None

        # Should delete corrupted data
        mock_redis.delete.assert_called_once_with(f"session:{session_id}")


@pytest.mark.unit
class TestSessionStoreIndexing:
    """
    Test Redis indexing for user sessions (Phase 2.5).

    Tests the user:{user_id}:sessions SET index for O(1) bulk deletion performance.
    """

    @pytest.mark.asyncio
    async def test_create_session_adds_to_user_index(self):
        """Test that creating a session adds it to the user's session index."""
        mock_redis = AsyncMock()
        store = SessionStore(mock_redis)

        user_id = str(uuid4())
        session = await store.create_session(user_id=user_id, remember_me=False)

        # Verify session was created
        mock_redis.setex.assert_called_once()

        # Verify session was added to user index
        user_sessions_key = f"user:{user_id}:sessions"
        mock_redis.sadd.assert_called_once_with(user_sessions_key, session.session_id)

        # Verify index TTL was set
        mock_redis.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_session_sets_index_ttl(self):
        """Test that user index TTL is set to max session TTL."""
        mock_redis = AsyncMock()
        store = SessionStore(mock_redis)

        user_id = str(uuid4())
        await store.create_session(user_id=user_id, remember_me=False)

        # Verify index TTL matches max possible session TTL (remember_me case)
        from src.core.config import settings

        user_sessions_key = f"user:{user_id}:sessions"
        mock_redis.expire.assert_called_once_with(
            user_sessions_key, settings.session_cookie_max_age_remember
        )

    @pytest.mark.asyncio
    async def test_delete_session_removes_from_index(self):
        """Test that deleting a session removes it from user index."""
        mock_redis = AsyncMock()
        store = SessionStore(mock_redis)

        user_id = str(uuid4())
        session_id = str(uuid4())

        # Mock get_session to return session data
        session_data = {
            "user_id": user_id,
            "remember_me": False,
            "created_at": datetime.now(UTC).isoformat(),
        }
        mock_redis.get.return_value = json.dumps(session_data)
        mock_redis.delete.return_value = 1  # Session deleted successfully

        result = await store.delete_session(session_id)

        assert result is True

        # Verify session was removed from user index
        user_sessions_key = f"user:{user_id}:sessions"
        mock_redis.srem.assert_called_once_with(user_sessions_key, session_id)

    @pytest.mark.asyncio
    async def test_delete_session_handles_missing_session_gracefully(self):
        """Test delete_session when session doesn't exist (no index update)."""
        mock_redis = AsyncMock()
        store = SessionStore(mock_redis)

        session_id = str(uuid4())

        # Mock get_session to return None (session not found)
        mock_redis.get.return_value = None
        mock_redis.delete.return_value = 0  # No session deleted

        result = await store.delete_session(session_id)

        assert result is False

        # Verify index removal was NOT attempted (no session data)
        mock_redis.srem.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_all_user_sessions_uses_index(self):
        """Test delete_all_user_sessions uses index for O(1) lookup."""
        from unittest.mock import Mock

        mock_redis = AsyncMock()
        store = SessionStore(mock_redis)

        user_id = str(uuid4())
        session_ids = [str(uuid4()), str(uuid4()), str(uuid4())]

        # Mock index lookup (SMEMBERS)
        mock_redis.smembers.return_value = [sid.encode() for sid in session_ids]

        # Mock pipeline - pipeline() is NOT async (it's sync method), but execute() IS async
        mock_pipeline = Mock()
        mock_pipeline.delete = Mock(return_value=mock_pipeline)  # Chainable
        mock_pipeline.execute = AsyncMock(return_value=[1, 1, 1, 1])  # 3 sessions + 1 index deleted

        # CRITICAL: Make pipeline() a synchronous Mock, not AsyncMock
        mock_redis.pipeline = Mock(return_value=mock_pipeline)

        count = await store.delete_all_user_sessions(user_id)

        # Verify index was queried (O(1) lookup)
        user_sessions_key = f"user:{user_id}:sessions"
        mock_redis.smembers.assert_called_once_with(user_sessions_key)

        # Verify pipeline was used for batch deletion
        mock_redis.pipeline.assert_called_once()
        assert mock_pipeline.delete.call_count == 4  # 3 sessions + 1 index

        # Verify count matches successful deletions
        assert count == 3

    @pytest.mark.asyncio
    async def test_delete_all_user_sessions_empty_index(self):
        """Test delete_all_user_sessions when user has no sessions."""
        mock_redis = AsyncMock()
        store = SessionStore(mock_redis)

        user_id = str(uuid4())

        # Mock empty index
        mock_redis.smembers.return_value = set()

        count = await store.delete_all_user_sessions(user_id)

        # Should return 0 without attempting deletions
        assert count == 0
        mock_redis.pipeline.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_all_user_sessions_partial_deletions(self):
        """Test delete_all_user_sessions counts only successful deletions."""
        from unittest.mock import Mock

        mock_redis = AsyncMock()
        store = SessionStore(mock_redis)

        user_id = str(uuid4())
        session_ids = [str(uuid4()), str(uuid4()), str(uuid4())]

        # Mock index lookup
        mock_redis.smembers.return_value = [sid.encode() for sid in session_ids]

        # Mock pipeline execution (only 2 out of 3 sessions deleted successfully)
        mock_pipeline = Mock()
        mock_pipeline.delete = Mock(return_value=mock_pipeline)  # Chainable
        mock_pipeline.execute = AsyncMock(
            return_value=[1, 0, 1, 1]
        )  # session1: ok, session2: not found, session3: ok, index: ok

        # CRITICAL: Make pipeline() a synchronous Mock, not AsyncMock
        mock_redis.pipeline = Mock(return_value=mock_pipeline)

        count = await store.delete_all_user_sessions(user_id)

        # Should count only successful deletions (2 out of 3)
        assert count == 2

    @pytest.mark.asyncio
    async def test_multiple_users_sessions_isolated(self):
        """Test that user session indexes are isolated (no cross-contamination)."""
        mock_redis = AsyncMock()
        store = SessionStore(mock_redis)

        user1_id = str(uuid4())
        user2_id = str(uuid4())

        # Create sessions for user1
        session1 = await store.create_session(user1_id, remember_me=False)
        session2 = await store.create_session(user1_id, remember_me=False)

        # Create sessions for user2
        session3 = await store.create_session(user2_id, remember_me=False)

        # Verify each user has their own index key
        user1_key = f"user:{user1_id}:sessions"
        user2_key = f"user:{user2_id}:sessions"

        # User1 should have 2 sessions indexed
        assert mock_redis.sadd.call_count == 3  # Total 3 calls

        # Check calls contain correct user keys
        sadd_calls = [call[0] for call in mock_redis.sadd.call_args_list]
        assert (user1_key, session1.session_id) in sadd_calls
        assert (user1_key, session2.session_id) in sadd_calls
        assert (user2_key, session3.session_id) in sadd_calls
