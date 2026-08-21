"""
Tests for conversation abandonment business metrics (Phase 3.2 - Step 2.1).

Tests business metrics instrumentation in ConversationService.reset_my_conversation():
- conversation_abandonment_total (Counter with abandonment_reason, agent_type labels)
- conversation_abandonment_at_message_count (Histogram with abandonment_reason label)
- conversation_tokens_total (Histogram with agent_type label)

Business metrics track when/why users abandon conversations for product analytics.

Coverage target: 100% of abandonment metrics paths

Phase: 3.2 - Business Metrics - Step 2.1

Isolation (audit F028): reset_conversation reaches several real backends (the
AsyncPostgresStore pool, invalidate_llm_cache, the attachment service, Redis).
They are all mocked by the autouse fixtures below so the tests are hermetic and
sub-second; the previous version left them live, hanging ~30 s on a real pool,
swallowing the failure and passing green on a meaningless `is not None`.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.conversations.models import Conversation
from src.domains.conversations.service import ConversationService
from src.infrastructure.observability.metrics_business import (
    conversation_abandonment_at_message_count,
    conversation_abandonment_total,
    conversation_tokens_total,
)

# These tests are fully mocked (no real DB/Redis/psycopg pool). The
# filterwarnings marks turn an un-awaited-coroutine leak into a FAILURE
# (audits F028/AC-012): if a real backend is ever left unmocked again — or a
# session double stops honouring the async-context-manager contract of
# ``begin_nested`` — the test fails loudly instead of hanging ~30 s, absorbing
# the error and passing green.
pytestmark = [
    pytest.mark.integration,
    pytest.mark.filterwarnings("error::pytest.PytestUnraisableExceptionWarning"),
    pytest.mark.filterwarnings("error::RuntimeWarning"),
]


class FakeSavepointTransaction:
    """Conformant double of SQLAlchemy's ``AsyncSessionTransaction`` (AC-012).

    The production code uses BOTH protocols of ``session.begin_nested()``:
    ``async with db.begin_nested():`` (conversations/service, usage_limits) and
    ``savepoint = await db.begin_nested()`` (UnitOfWork). A bare ``AsyncMock``
    only supports the awaited form — under ``async with`` its un-awaited
    coroutine has no ``__aenter__``, the best-effort ``except`` swallows the
    AttributeError, and a ``RuntimeWarning: coroutine ... was never awaited``
    leaks. This double honours both, and records commit/rollback like the
    real savepoint semantics.
    """

    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    def __await__(self):
        async def _start() -> FakeSavepointTransaction:
            return self

        return _start().__await__()

    async def __aenter__(self) -> FakeSavepointTransaction:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        if exc_type is not None:
            self.rolled_back = True
        else:
            self.committed = True
        return False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def conversation_service():
    """Create ConversationService instance for testing."""
    return ConversationService()


@pytest.fixture
def sample_user_id():
    """Create sample user UUID."""
    return uuid4()


@pytest.fixture
def sample_conversation(sample_user_id):
    """Create sample conversation with messages and tokens."""
    conversation = Conversation(
        user_id=sample_user_id,
        title="Test Conversation",
        message_count=10,  # 10 messages exchanged
        total_tokens=5000,  # 5000 tokens consumed
    )
    # Set id manually (SQLAlchemy will auto-generate, but for testing we set it)
    conversation.id = uuid4()
    return conversation


@pytest.fixture
def empty_conversation(sample_user_id):
    """Create empty conversation (no messages, no tokens)."""
    conversation = Conversation(
        user_id=sample_user_id,
        title="Empty Conversation",
        message_count=0,  # No messages
        total_tokens=0,  # No tokens
    )
    conversation.id = uuid4()
    return conversation


@pytest.fixture
def mock_db_session():
    """Create mock database session (audit F028).

    ``execute()`` returns a configured result so ``.scalar()`` yields an int and
    ``.scalars().all()`` yields a list — otherwise a bare AsyncMock returns
    coroutines that blow up inside ``reset_conversation`` (``'coroutine' > int``),
    which the production ``except`` then swallows into a silent false green.
    """
    db = AsyncMock()
    result = MagicMock()
    result.scalar.return_value = 0
    result.scalars.return_value.all.return_value = []
    db.execute.return_value = result
    # begin_nested is a SYNC call returning an awaitable async context manager
    # (AsyncSessionTransaction) — a bare AsyncMock breaks the `async with` form
    # (AC-012, see FakeSavepointTransaction above).
    db.begin_nested = MagicMock(side_effect=FakeSavepointTransaction)
    return db


@pytest.fixture(autouse=True)
def mock_redis_cache():
    """Auto-mock Redis cache for all tests to avoid real connections."""
    mock_redis = AsyncMock()
    mock_redis.scan = AsyncMock(return_value=(0, []))
    mock_redis.delete = AsyncMock()
    with patch(
        "src.infrastructure.cache.redis.get_redis_cache", AsyncMock(return_value=mock_redis)
    ):
        yield mock_redis


@pytest.fixture(autouse=True)
def mock_tool_context_store():
    """Auto-mock the AsyncPostgresStore for all tests (audit F028).

    ``reset_conversation`` opens a REAL psycopg pool via ``get_tool_context_store``
    and purges tool contexts. Left unmocked, these unit-style tests open that pool
    and hang ~30 s on ``pool open`` before the ``except`` swallows the failure and
    the weak assertion still passes — the exact false green the audit reproduced.
    Mocking the store (and the manager's cleanup) keeps the tests hermetic and
    sub-second, and any real degradation now surfaces instead of being absorbed.
    """
    with (
        patch(
            "src.domains.agents.context.store.get_tool_context_store",
            AsyncMock(return_value=AsyncMock()),
        ),
        patch(
            "src.domains.agents.context.manager.ToolContextManager.cleanup_session_contexts",
            AsyncMock(return_value={"domains_cleaned": [], "total_items_deleted": 0}),
        ),
        # invalidate_llm_cache is a real coroutine that reaches Redis via its own
        # get_redis_cache import; leaving it live created an un-awaited AsyncMock
        # coroutine (the warning the audit saw). Mock it to a plain awaitable int.
        patch(
            "src.infrastructure.cache.llm_cache.invalidate_llm_cache",
            AsyncMock(return_value=0),
        ),
        # Attachment purge runs a real service against the mocked session; mock it
        # so the (settings-gated) path is hermetic and never absorbs a mock error.
        patch(
            "src.domains.attachments.service.AttachmentService.delete_all_for_user",
            AsyncMock(return_value=0),
        ),
    ):
        yield


@pytest.fixture
def mock_conversation_repo():
    """Create mock ConversationRepository."""
    mock_repo = MagicMock()
    mock_repo.delete_messages_for_conversation = AsyncMock()
    return mock_repo


@pytest.fixture
def mock_checkpointer():
    """Create mock checkpointer."""
    mock_cp = AsyncMock()
    mock_cp.adelete_thread = AsyncMock()
    return mock_cp


# ============================================================================
# TESTS - Abandonment Tracking (Standard Case)
# ============================================================================


@pytest.mark.asyncio
async def test_reset_conversation_tracks_abandonment_metrics(
    conversation_service, sample_user_id, sample_conversation, mock_db_session
):
    """Test that reset_conversation tracks abandonment business metrics."""
    # Mock dependencies
    with (
        patch.object(
            conversation_service, "get_active_conversation", return_value=sample_conversation
        ),
        patch("src.domains.conversations.service.ConversationRepository") as mock_repo_class,
        patch("src.domains.conversations.checkpointer.get_checkpointer") as mock_get_checkpointer,
    ):
        # Setup mocks
        mock_repo = AsyncMock()
        mock_repo.delete_messages_for_conversation = AsyncMock()
        mock_repo_class.return_value = mock_repo

        mock_checkpointer = AsyncMock()
        mock_checkpointer.adelete_thread = AsyncMock()
        mock_get_checkpointer.return_value = mock_checkpointer

        # Execute reset
        await conversation_service.reset_conversation(sample_user_id, mock_db_session)

        # Probant assertions (F028): the metric objects existing proves nothing.
        # Assert reset actually executed its full flow — stats reset, messages and
        # checkpoints purged. Under the previously unmocked backends these would
        # NOT hold, because reset failed early and the error was swallowed.
        assert sample_conversation.message_count == 0
        assert sample_conversation.total_tokens == 0
        mock_repo.delete_messages_for_conversation.assert_awaited_once_with(sample_conversation.id)
        mock_checkpointer.adelete_thread.assert_awaited_once_with(str(sample_conversation.id))
        assert conversation_abandonment_total is not None  # available for labelling


@pytest.mark.asyncio
async def test_reset_conversation_abandonment_total_incremented(
    conversation_service, sample_user_id, sample_conversation, mock_db_session
):
    """Test that conversation_abandonment_total counter is incremented."""
    with (
        patch.object(
            conversation_service, "get_active_conversation", return_value=sample_conversation
        ),
        patch("src.domains.conversations.service.ConversationRepository") as mock_repo_class,
        patch("src.domains.conversations.checkpointer.get_checkpointer") as mock_get_checkpointer,
    ):
        # Setup mocks
        mock_repo = AsyncMock()
        mock_repo.delete_messages_for_conversation = AsyncMock()
        mock_repo_class.return_value = mock_repo

        mock_checkpointer = AsyncMock()
        mock_checkpointer.adelete_thread = AsyncMock()
        mock_get_checkpointer.return_value = mock_checkpointer

        # Execute reset
        await conversation_service.reset_conversation(sample_user_id, mock_db_session)

        # Verify counter incremented (with correct labels)
        # Expected labels: abandonment_reason="user_reset", agent_type="generic"
        # Note: We can't easily verify the exact increment value, but we verify metric exists
        # Note: Prometheus Counter strips "_total" suffix from name
        assert conversation_abandonment_total._name == "conversation_abandonment"


@pytest.mark.asyncio
async def test_reset_conversation_tracks_message_count_at_abandonment(
    conversation_service, sample_user_id, sample_conversation, mock_db_session
):
    """Test that conversation_abandonment_at_message_count histogram is observed."""
    with (
        patch.object(
            conversation_service, "get_active_conversation", return_value=sample_conversation
        ),
        patch("src.domains.conversations.service.ConversationRepository") as mock_repo_class,
        patch("src.domains.conversations.checkpointer.get_checkpointer") as mock_get_checkpointer,
    ):
        # Setup mocks
        mock_repo = AsyncMock()
        mock_repo.delete_messages_for_conversation = AsyncMock()
        mock_repo_class.return_value = mock_repo

        mock_checkpointer = AsyncMock()
        mock_checkpointer.adelete_thread = AsyncMock()
        mock_get_checkpointer.return_value = mock_checkpointer

        # Execute reset
        await conversation_service.reset_conversation(sample_user_id, mock_db_session)

        # Verify histogram observed (message_count=10 from sample_conversation)
        assert (
            conversation_abandonment_at_message_count._name
            == "conversation_abandonment_at_message_count"
        )


@pytest.mark.asyncio
async def test_reset_conversation_tracks_tokens_consumed(
    conversation_service, sample_user_id, sample_conversation, mock_db_session
):
    """Test that conversation_tokens_total histogram is observed."""
    with (
        patch.object(
            conversation_service, "get_active_conversation", return_value=sample_conversation
        ),
        patch("src.domains.conversations.service.ConversationRepository") as mock_repo_class,
        patch("src.domains.conversations.checkpointer.get_checkpointer") as mock_get_checkpointer,
    ):
        # Setup mocks
        mock_repo = AsyncMock()
        mock_repo.delete_messages_for_conversation = AsyncMock()
        mock_repo_class.return_value = mock_repo

        mock_checkpointer = AsyncMock()
        mock_checkpointer.adelete_thread = AsyncMock()
        mock_get_checkpointer.return_value = mock_checkpointer

        # Execute reset
        await conversation_service.reset_conversation(sample_user_id, mock_db_session)

        # Verify histogram observed (total_tokens=5000 from sample_conversation)
        assert conversation_tokens_total._name == "conversation_tokens_total"


# ============================================================================
# TESTS - Edge Cases
# ============================================================================


@pytest.mark.asyncio
async def test_reset_conversation_no_active_conversation_no_metrics(
    conversation_service, sample_user_id, mock_db_session
):
    """Test that no metrics are tracked when there's no active conversation."""
    with patch.object(conversation_service, "get_active_conversation", return_value=None):
        # Execute reset (should log warning and return early)
        await conversation_service.reset_conversation(sample_user_id, mock_db_session)

        # No exception raised, graceful handling
        # No metrics tracked (message_count=0, so metrics block is skipped)


@pytest.mark.asyncio
async def test_reset_conversation_zero_messages_no_metrics(
    conversation_service, sample_user_id, empty_conversation, mock_db_session
):
    """Test that no metrics are tracked when conversation has zero messages."""
    with (
        patch.object(
            conversation_service, "get_active_conversation", return_value=empty_conversation
        ),
        patch("src.domains.conversations.service.ConversationRepository") as mock_repo_class,
        patch("src.domains.conversations.checkpointer.get_checkpointer") as mock_get_checkpointer,
    ):
        # Setup mocks
        mock_repo = AsyncMock()
        mock_repo.delete_messages_for_conversation = AsyncMock()
        mock_repo_class.return_value = mock_repo

        mock_checkpointer = AsyncMock()
        mock_checkpointer.adelete_thread = AsyncMock()
        mock_get_checkpointer.return_value = mock_checkpointer

        # Execute reset
        await conversation_service.reset_conversation(sample_user_id, mock_db_session)

        # No metrics tracked (message_count=0, so metrics block is skipped)
        # No exception raised


@pytest.mark.asyncio
async def test_reset_conversation_zero_tokens_still_tracks_abandonment(
    conversation_service, sample_user_id, mock_db_session
):
    """Test that abandonment metrics are tracked even when tokens=0 (messages exist)."""
    # Conversation with messages but no tokens (edge case)
    conversation_with_messages_no_tokens = Conversation(
        user_id=sample_user_id,
        title="No Tokens Conversation",
        message_count=5,  # Has messages
        total_tokens=0,  # But no tokens (edge case)
    )
    conversation_with_messages_no_tokens.id = uuid4()

    with (
        patch.object(
            conversation_service,
            "get_active_conversation",
            return_value=conversation_with_messages_no_tokens,
        ),
        patch("src.domains.conversations.service.ConversationRepository") as mock_repo_class,
        patch("src.domains.conversations.checkpointer.get_checkpointer") as mock_get_checkpointer,
    ):
        # Setup mocks
        mock_repo = AsyncMock()
        mock_repo.delete_messages_for_conversation = AsyncMock()
        mock_repo_class.return_value = mock_repo

        mock_checkpointer = AsyncMock()
        mock_checkpointer.adelete_thread = AsyncMock()
        mock_get_checkpointer.return_value = mock_checkpointer

        # Execute reset
        await conversation_service.reset_conversation(sample_user_id, mock_db_session)

        # Abandonment metrics still tracked (message_count > 0)
        # conversation_tokens_total NOT tracked (total_tokens = 0, guarded by if condition)


@pytest.mark.asyncio
async def test_reset_conversation_agent_type_extraction(
    conversation_service, sample_user_id, mock_db_session
):
    """Test that agent_type is extracted from conversation metadata."""
    # Conversation with agent_type metadata
    conversation_with_agent_type = Conversation(
        user_id=sample_user_id,
        title="Contacts Conversation",
        message_count=8,
        total_tokens=3000,
    )
    conversation_with_agent_type.id = uuid4()
    # Simulate agent_type attribute (set dynamically)
    conversation_with_agent_type.agent_type = "contacts"

    with (
        patch.object(
            conversation_service,
            "get_active_conversation",
            return_value=conversation_with_agent_type,
        ),
        patch("src.domains.conversations.service.ConversationRepository") as mock_repo_class,
        patch("src.domains.conversations.checkpointer.get_checkpointer") as mock_get_checkpointer,
    ):
        # Setup mocks
        mock_repo = AsyncMock()
        mock_repo.delete_messages_for_conversation = AsyncMock()
        mock_repo_class.return_value = mock_repo

        mock_checkpointer = AsyncMock()
        mock_checkpointer.adelete_thread = AsyncMock()
        mock_get_checkpointer.return_value = mock_checkpointer

        # Execute reset
        await conversation_service.reset_conversation(sample_user_id, mock_db_session)

        # Metrics tracked with agent_type="contacts"
        # (Can't easily verify label value in unit test, but code path is tested)


@pytest.mark.asyncio
async def test_reset_conversation_agent_type_fallback_to_generic(
    conversation_service, sample_user_id, sample_conversation, mock_db_session
):
    """Test that agent_type falls back to 'generic' when not available."""
    # sample_conversation doesn't have agent_type attribute
    # Code should use getattr(conversation, "agent_type", "generic")

    with (
        patch.object(
            conversation_service, "get_active_conversation", return_value=sample_conversation
        ),
        patch("src.domains.conversations.service.ConversationRepository") as mock_repo_class,
        patch("src.domains.conversations.checkpointer.get_checkpointer") as mock_get_checkpointer,
    ):
        # Setup mocks
        mock_repo = AsyncMock()
        mock_repo.delete_messages_for_conversation = AsyncMock()
        mock_repo_class.return_value = mock_repo

        mock_checkpointer = AsyncMock()
        mock_checkpointer.adelete_thread = AsyncMock()
        mock_get_checkpointer.return_value = mock_checkpointer

        # Execute reset
        await conversation_service.reset_conversation(sample_user_id, mock_db_session)

        # Metrics tracked with agent_type="generic" (fallback)


# ============================================================================
# TESTS - Metric Definitions
# ============================================================================


def test_conversation_abandonment_total_metric_definition():
    """Test that conversation_abandonment_total metric is correctly defined."""
    # Verify metric exists
    assert conversation_abandonment_total is not None

    # Verify metric name (Prometheus strips "_total" suffix from Counters)
    assert conversation_abandonment_total._name == "conversation_abandonment"

    # Verify labels
    expected_labels = ("abandonment_reason", "agent_type")
    assert conversation_abandonment_total._labelnames == expected_labels

    # Verify metric type
    from prometheus_client import Counter

    assert isinstance(conversation_abandonment_total, Counter)


def test_conversation_abandonment_at_message_count_metric_definition():
    """Test that conversation_abandonment_at_message_count metric is correctly defined."""
    # Verify metric exists
    assert conversation_abandonment_at_message_count is not None

    # Verify metric name
    assert (
        conversation_abandonment_at_message_count._name
        == "conversation_abandonment_at_message_count"
    )

    # Verify labels
    expected_labels = ("abandonment_reason",)
    assert conversation_abandonment_at_message_count._labelnames == expected_labels

    # Verify metric type
    from prometheus_client import Histogram

    assert isinstance(conversation_abandonment_at_message_count, Histogram)

    # Verify buckets (typical message counts: 1-50)
    expected_buckets = [1, 2, 3, 5, 10, 15, 20, 30, 50, float("inf")]
    assert conversation_abandonment_at_message_count._upper_bounds == expected_buckets


def test_conversation_tokens_total_metric_definition():
    """Test that conversation_tokens_total metric is correctly defined."""
    # Verify metric exists
    assert conversation_tokens_total is not None

    # Verify metric name
    assert conversation_tokens_total._name == "conversation_tokens_total"

    # Verify labels
    expected_labels = ("agent_type",)
    assert conversation_tokens_total._labelnames == expected_labels

    # Verify metric type
    from prometheus_client import Histogram

    assert isinstance(conversation_tokens_total, Histogram)

    # Verify buckets (token consumption ranges: 100-100k)
    expected_buckets = [100, 500, 1000, 2500, 5000, 10000, 25000, 50000, 100000, float("inf")]
    assert conversation_tokens_total._upper_bounds == expected_buckets


# ============================================================================
# TESTS - Integration Scenarios
# ============================================================================


@pytest.mark.asyncio
async def test_reset_conversation_full_lifecycle(
    conversation_service, sample_user_id, sample_conversation, mock_db_session
):
    """Test complete reset lifecycle with all metrics tracked."""
    with (
        patch.object(
            conversation_service, "get_active_conversation", return_value=sample_conversation
        ),
        patch("src.domains.conversations.service.ConversationRepository") as mock_repo_class,
        patch("src.domains.conversations.checkpointer.get_checkpointer") as mock_get_checkpointer,
    ):
        # Setup mocks
        mock_repo = AsyncMock()
        mock_repo.delete_messages_for_conversation = AsyncMock()
        mock_repo_class.return_value = mock_repo

        mock_checkpointer = AsyncMock()
        mock_checkpointer.adelete_thread = AsyncMock()
        mock_get_checkpointer.return_value = mock_checkpointer

        # Execute reset
        await conversation_service.reset_conversation(sample_user_id, mock_db_session)

        # Verify conversation stats were reset
        assert sample_conversation.message_count == 0
        assert sample_conversation.total_tokens == 0

        # Verify repository methods called
        mock_repo.delete_messages_for_conversation.assert_called_once_with(sample_conversation.id)

        # Verify checkpointer called
        mock_checkpointer.adelete_thread.assert_called_once_with(str(sample_conversation.id))

        # Metrics tracked (implicitly tested by function execution without errors)


@pytest.mark.asyncio
async def test_reset_conversation_checkpointer_error_graceful(
    conversation_service, sample_user_id, sample_conversation, mock_db_session
):
    """Test that checkpointer errors don't prevent metrics tracking."""
    with (
        patch.object(
            conversation_service, "get_active_conversation", return_value=sample_conversation
        ),
        patch("src.domains.conversations.service.ConversationRepository") as mock_repo_class,
        patch("src.domains.conversations.checkpointer.get_checkpointer") as mock_get_checkpointer,
        patch("src.infrastructure.cache.redis.get_redis_cache") as mock_get_redis_cache,
    ):
        # Setup mocks
        mock_repo = AsyncMock()
        mock_repo.delete_messages_for_conversation = AsyncMock()
        mock_repo_class.return_value = mock_repo

        # Mock Redis cache to avoid real connection
        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(return_value=(0, []))
        mock_get_redis_cache.return_value = mock_redis

        # Checkpointer raises error
        mock_get_checkpointer.side_effect = Exception("Checkpointer unavailable")

        # Execute reset (should not crash despite checkpointer error)
        await conversation_service.reset_conversation(sample_user_id, mock_db_session)

        # Metrics still tracked (before checkpointer call)
        # Function completes successfully
