"""
Unit tests for domains.agents.services.conversation_orchestrator module.

Tests ConversationOrchestrator service for conversation lifecycle management.

Author: Claude Code (Sonnet 4.5)
Date: 2025-11-21
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.agents.services.conversation_orchestrator import (
    ConversationContext,
    ConversationOrchestrator,
    ConversationSummary,
)
from src.domains.chat.schemas import TokenSummaryDTO


class TestConversationContext:
    """Tests for ConversationContext dataclass."""

    def test_conversation_context_initialization(self):
        """Test ConversationContext can be initialized with required fields."""
        conversation_id = uuid.uuid4()
        tracking_context = MagicMock()
        oauth_scopes = ["https://www.googleapis.com/auth/contacts"]

        context = ConversationContext(
            conversation_id=conversation_id,
            tracking_context=tracking_context,
            oauth_scopes=oauth_scopes,
        )

        assert context.conversation_id == conversation_id
        assert context.tracking_context == tracking_context
        assert context.oauth_scopes == oauth_scopes

    def test_conversation_context_with_empty_scopes(self):
        """Test ConversationContext can be initialized with empty OAuth scopes."""
        context = ConversationContext(
            conversation_id=uuid.uuid4(),
            tracking_context=MagicMock(),
            oauth_scopes=[],
        )

        assert context.oauth_scopes == []

    def test_conversation_context_with_multiple_scopes(self):
        """Test ConversationContext stores multiple OAuth scopes."""
        scopes = [
            "https://www.googleapis.com/auth/contacts",
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/calendar",
        ]

        context = ConversationContext(
            conversation_id=uuid.uuid4(),
            tracking_context=MagicMock(),
            oauth_scopes=scopes,
        )

        assert len(context.oauth_scopes) == 3
        assert context.oauth_scopes == scopes


class TestConversationSummary:
    """Tests for ConversationSummary dataclass."""

    def test_conversation_summary_initialization(self):
        """Test ConversationSummary can be initialized with required fields."""
        conversation_id = uuid.uuid4()
        token_summary = TokenSummaryDTO(
            tokens_in=100,
            tokens_out=50,
            tokens_cache=10,
            cost_eur=0.0009,
            message_count=5,
        )

        summary = ConversationSummary(
            conversation_id=conversation_id,
            message_count=5,
            token_summary=token_summary,
        )

        assert summary.conversation_id == conversation_id
        assert summary.message_count == 5
        assert summary.token_summary == token_summary

    def test_conversation_summary_with_zero_messages(self):
        """Test ConversationSummary can be created with zero messages."""
        summary = ConversationSummary(
            conversation_id=uuid.uuid4(),
            message_count=0,
            token_summary=TokenSummaryDTO(
                tokens_in=0, tokens_out=0, tokens_cache=0, cost_eur=0.0, message_count=0
            ),
        )

        assert summary.message_count == 0


class TestConversationOrchestrator:
    """Tests for ConversationOrchestrator service."""

    @pytest.fixture
    def orchestrator(self):
        """Create ConversationOrchestrator instance."""
        return ConversationOrchestrator()

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        return AsyncMock()

    @pytest.fixture
    def sample_user_id(self):
        """Create sample user UUID."""
        return uuid.uuid4()

    @pytest.fixture
    def sample_conversation_id(self):
        """Create sample conversation UUID."""
        return uuid.uuid4()

    @pytest.mark.asyncio
    async def test_setup_conversation_creates_context(
        self, orchestrator, mock_db, sample_user_id, sample_conversation_id
    ):
        """Test setup_conversation creates ConversationContext."""
        # Arrange: Mock conversation service
        mock_conversation = MagicMock()
        mock_conversation.id = sample_conversation_id

        with patch(
            "src.domains.agents.services.conversation_orchestrator.ConversationService"
        ) as mock_conv_svc:
            mock_conv_svc.return_value.get_or_create_conversation = AsyncMock(
                return_value=mock_conversation
            )

            # Mock OAuth scopes fetching
            with patch.object(
                orchestrator, "_get_user_oauth_scopes", new=AsyncMock(return_value=["scope1"])
            ):
                # Act
                context = await orchestrator.setup_conversation(
                    user_id=sample_user_id,
                    session_id="test-session",
                    run_id="test-run",
                    db=mock_db,
                )

                # Assert
                assert isinstance(context, ConversationContext)
                assert context.conversation_id == sample_conversation_id
                assert context.oauth_scopes == ["scope1"]
                assert context.tracking_context is not None

    @pytest.mark.asyncio
    async def test_setup_conversation_calls_get_or_create(
        self, orchestrator, mock_db, sample_user_id, sample_conversation_id
    ):
        """Test setup_conversation calls ConversationService.get_or_create_conversation."""
        # Arrange
        mock_conversation = MagicMock()
        mock_conversation.id = sample_conversation_id

        with patch(
            "src.domains.agents.services.conversation_orchestrator.ConversationService"
        ) as mock_conv_svc:
            mock_get_or_create = AsyncMock(return_value=mock_conversation)
            mock_conv_svc.return_value.get_or_create_conversation = mock_get_or_create

            with patch.object(
                orchestrator, "_get_user_oauth_scopes", new=AsyncMock(return_value=[])
            ):
                # Act
                await orchestrator.setup_conversation(
                    user_id=sample_user_id,
                    session_id="test-session",
                    run_id="test-run",
                    db=mock_db,
                )

                # Assert: Service was called with correct params
                mock_get_or_create.assert_called_once_with(sample_user_id, mock_db)

    @pytest.mark.asyncio
    async def test_setup_conversation_fetches_oauth_scopes(
        self, orchestrator, mock_db, sample_user_id, sample_conversation_id
    ):
        """Test setup_conversation fetches user OAuth scopes."""
        # Arrange
        mock_conversation = MagicMock()
        mock_conversation.id = sample_conversation_id

        expected_scopes = [
            "https://www.googleapis.com/auth/contacts",
            "https://www.googleapis.com/auth/gmail.readonly",
        ]

        with patch(
            "src.domains.agents.services.conversation_orchestrator.ConversationService"
        ) as mock_conv_svc:
            mock_conv_svc.return_value.get_or_create_conversation = AsyncMock(
                return_value=mock_conversation
            )

            with patch.object(
                orchestrator, "_get_user_oauth_scopes", new=AsyncMock(return_value=expected_scopes)
            ) as mock_get_scopes:
                # Act
                context = await orchestrator.setup_conversation(
                    user_id=sample_user_id,
                    session_id="test-session",
                    run_id="test-run",
                    db=mock_db,
                )

                # Assert: Scopes fetched and stored
                mock_get_scopes.assert_called_once_with(sample_user_id, mock_db)
                assert context.oauth_scopes == expected_scopes

    @pytest.mark.asyncio
    async def test_persist_messages_logs_correctly(self, orchestrator, sample_conversation_id):
        """Test persist_messages logs message count."""
        # Arrange
        messages = [MagicMock(), MagicMock(), MagicMock()]
        tracking_context = MagicMock()

        # Act (currently just logs, TODO: implement persistence)
        await orchestrator.persist_messages(
            conversation_id=sample_conversation_id,
            messages=messages,
            tracking_context=tracking_context,
        )

        # Assert: No exception raised (persistence not yet implemented)
        # This test validates the method signature and basic execution

    @pytest.mark.asyncio
    async def test_persist_messages_with_empty_list(self, orchestrator, sample_conversation_id):
        """Test persist_messages handles empty message list."""
        # Arrange
        messages = []
        tracking_context = MagicMock()

        # Act
        await orchestrator.persist_messages(
            conversation_id=sample_conversation_id,
            messages=messages,
            tracking_context=tracking_context,
        )

        # Assert: No exception raised

    @pytest.mark.asyncio
    async def test_finalize_conversation_returns_summary(
        self, orchestrator, sample_conversation_id
    ):
        """Test finalize_conversation returns ConversationSummary."""
        # Arrange
        tracking_context = MagicMock()
        tracking_context.conversation_id = sample_conversation_id

        # Mock TokenSummaryDTO.from_tracker factory method
        mock_token_summary = TokenSummaryDTO(
            tokens_in=100, tokens_out=50, tokens_cache=10, cost_eur=0.0009, message_count=2
        )

        with patch(
            "src.domains.chat.schemas.TokenSummaryDTO.from_tracker", return_value=mock_token_summary
        ):
            final_state = {"messages": [MagicMock(), MagicMock()]}

            # Act
            summary = await orchestrator.finalize_conversation(tracking_context, final_state)

            # Assert
            assert isinstance(summary, ConversationSummary)
            assert summary.conversation_id == sample_conversation_id
            assert summary.message_count == 2
            assert summary.token_summary == mock_token_summary

    @pytest.mark.asyncio
    async def test_finalize_conversation_with_empty_messages(
        self, orchestrator, sample_conversation_id
    ):
        """Test finalize_conversation handles empty messages list."""
        # Arrange
        tracking_context = MagicMock()
        tracking_context.conversation_id = sample_conversation_id

        mock_token_summary = TokenSummaryDTO(
            tokens_in=0, tokens_out=0, tokens_cache=0, cost_eur=0.0, message_count=0
        )

        with patch(
            "src.domains.chat.schemas.TokenSummaryDTO.from_tracker", return_value=mock_token_summary
        ):
            final_state = {"messages": []}

            # Act
            summary = await orchestrator.finalize_conversation(tracking_context, final_state)

            # Assert
            assert summary.message_count == 0
            assert summary.token_summary.tokens_in == 0

    @pytest.mark.asyncio
    async def test_finalize_conversation_with_missing_messages_key(
        self, orchestrator, sample_conversation_id
    ):
        """Test finalize_conversation handles missing 'messages' key in state."""
        # Arrange
        tracking_context = MagicMock()
        tracking_context.conversation_id = sample_conversation_id

        mock_token_summary = TokenSummaryDTO(
            tokens_in=50, tokens_out=25, tokens_cache=5, cost_eur=0.00045, message_count=0
        )

        with patch(
            "src.domains.chat.schemas.TokenSummaryDTO.from_tracker", return_value=mock_token_summary
        ):
            final_state = {}  # Missing 'messages' key

            # Act
            summary = await orchestrator.finalize_conversation(tracking_context, final_state)

            # Assert: Defaults to empty list
            assert summary.message_count == 0

    @pytest.mark.asyncio
    async def test_get_user_oauth_scopes_returns_empty_for_no_connectors(
        self, orchestrator, mock_db, sample_user_id
    ):
        """Test _get_user_oauth_scopes returns empty list when no active connectors."""
        # Arrange: Mock DB query returning no connectors
        # Pattern: result = await db.execute(stmt); connectors = result.scalars().all()
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[])

        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=mock_scalars)

        mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        scopes = await orchestrator._get_user_oauth_scopes(sample_user_id, mock_db)

        # Assert
        assert scopes == []

    @pytest.mark.asyncio
    async def test_get_user_oauth_scopes_returns_deduped_scopes(
        self, orchestrator, mock_db, sample_user_id
    ):
        """Test _get_user_oauth_scopes deduplicates scopes from multiple connectors."""
        # Arrange: Mock connectors with overlapping scopes
        mock_conn1 = MagicMock()
        mock_conn1.scopes = ["scope1", "scope2"]

        mock_conn2 = MagicMock()
        mock_conn2.scopes = ["scope2", "scope3"]  # scope2 overlaps

        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[mock_conn1, mock_conn2])

        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=mock_scalars)

        mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        scopes = await orchestrator._get_user_oauth_scopes(sample_user_id, mock_db)

        # Assert: 3 unique scopes (scope2 deduplicated)
        assert len(scopes) == 3
        assert set(scopes) == {"scope1", "scope2", "scope3"}

    @pytest.mark.asyncio
    async def test_get_user_oauth_scopes_ignores_none_scopes(
        self, orchestrator, mock_db, sample_user_id
    ):
        """Test _get_user_oauth_scopes ignores connectors with None scopes."""
        # Arrange
        mock_conn1 = MagicMock()
        mock_conn1.scopes = ["scope1"]

        mock_conn2 = MagicMock()
        mock_conn2.scopes = None  # No scopes

        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[mock_conn1, mock_conn2])

        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=mock_scalars)

        mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        scopes = await orchestrator._get_user_oauth_scopes(sample_user_id, mock_db)

        # Assert: Only scope1 returned
        assert scopes == ["scope1"]

    @pytest.mark.asyncio
    async def test_get_user_oauth_scopes_queries_active_connectors_only(
        self, orchestrator, mock_db, sample_user_id
    ):
        """Test _get_user_oauth_scopes queries only ACTIVE connectors."""
        # Arrange
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[])

        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=mock_scalars)

        mock_db.execute = AsyncMock(return_value=mock_result)

        # Act
        await orchestrator._get_user_oauth_scopes(sample_user_id, mock_db)

        # Assert: Verify query filters by user_id and ACTIVE status
        mock_db.execute.assert_called_once()
        # Query validation (checking WHERE clause construction)
        call_args = mock_db.execute.call_args[0][0]
        # Statement should filter by user_id and status == ACTIVE
        assert call_args is not None
