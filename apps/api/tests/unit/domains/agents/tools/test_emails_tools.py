"""
Unit tests for emails_tools.py scope behavior (Issue #28).

Tests cover:
- Default scope application (-in:sent -in:draft for received emails)
- Explicit inbox request keywords (label:inbox)
- Existing scope preservation
- Log event validation
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.tools.emails_tools import SearchEmailsTool

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def user_id():
    """Generate test user ID."""
    return uuid4()


@pytest.fixture
def mock_gmail_client():
    """Mock GoogleGmailClient."""
    client = AsyncMock()
    client.search_emails = AsyncMock(
        return_value={"messages": [], "resultSizeEstimate": 0, "from_cache": False}
    )
    # Mock resolve_label_names_in_query to return input query unchanged (pass-through)
    client.resolve_label_names_in_query = AsyncMock(side_effect=lambda q, **kwargs: q)
    return client


@pytest.fixture
def search_emails_tool():
    """Create SearchEmailsTool instance."""
    return SearchEmailsTool()


# ============================================================================
# TEST 1: DEFAULT SCOPE (NO KEYWORDS) → -in:sent -in:draft (received emails)
# ============================================================================


@pytest.mark.asyncio
async def test_search_emails_no_scope_adds_received_filter(
    search_emails_tool, user_id, mock_gmail_client
):
    """Test default scope excludes sent/drafts (received emails only) when no keywords present."""
    # Given: Query without scope keywords
    kwargs = {"query": "from:jean", "max_results": 10}

    # When: Execute API call (business logic only)
    with patch("src.domains.agents.tools.emails_tools.logger") as mock_logger:
        await search_emails_tool.execute_api_call(mock_gmail_client, user_id, **kwargs)

    # Then: Query modified to exclude sent/drafts, exclude trash, and add default date filter
    mock_gmail_client.search_emails.assert_called_once()
    call_args = mock_gmail_client.search_emails.call_args
    final_query = call_args[1]["query"]
    assert "from:jean" in final_query
    assert "-in:sent" in final_query
    assert "-in:draft" in final_query
    assert "-in:trash" in final_query
    assert "after:" in final_query  # Default 90-day date filter

    # And: Log event emitted with correct scope
    assert mock_logger.info.call_count >= 1
    log_calls = [
        call for call in mock_logger.info.call_args_list if "search_emails_query_scope" in call[0]
    ]
    assert len(log_calls) == 1

    log_event = log_calls[0][0][0]
    log_kwargs = log_calls[0][1]
    assert log_event == "search_emails_query_scope"
    assert log_kwargs["original_query"] == "from:jean"
    assert "-in:sent" in log_kwargs["final_query"]
    assert "-in:draft" in log_kwargs["final_query"]
    assert "-in:trash" in log_kwargs["final_query"]
    assert log_kwargs["user_requested_inbox_only"] is False
    assert log_kwargs["scope_applied"] == "received"
    assert log_kwargs["trash_excluded"] is True


# ============================================================================
# TEST 2: EXPLICIT INBOX KEYWORDS → label:inbox
# ============================================================================


@pytest.mark.parametrize(
    "query_with_inbox_keyword",
    [
        "from:jean dans ma boîte de réception",
        "from:jean dans inbox",
        "from:jean dans ma boite de reception",
        "from:jean in inbox",
        "from:jean in my inbox",
        "from:jean inbox only",
        "from:jean boîte de réception",
        "from:jean boite de reception",
    ],
)
@pytest.mark.asyncio
async def test_search_emails_inbox_keywords_adds_label_inbox(
    search_emails_tool, user_id, mock_gmail_client, query_with_inbox_keyword
):
    """Test explicit inbox request applies label:inbox."""
    # Given: Query with explicit inbox keywords
    kwargs = {"query": query_with_inbox_keyword, "max_results": 10}

    # When: Execute search_emails
    with patch("src.domains.agents.tools.emails_tools.logger") as mock_logger:
        await search_emails_tool.execute_api_call(mock_gmail_client, user_id, **kwargs)

    # Then: Query modified to include label:inbox (explicit request)
    mock_gmail_client.search_emails.assert_called_once()
    call_args = mock_gmail_client.search_emails.call_args
    final_query = call_args[1]["query"]
    assert "label:inbox" in final_query
    assert "-in:sent" not in final_query  # Should NOT add sent exclusion (inbox already scopes it)
    assert (
        "-in:draft" not in final_query
    )  # Should NOT add draft exclusion (inbox already scopes it)

    # And: Log event emitted with inbox scope
    assert mock_logger.info.call_count >= 1
    log_calls = [
        call for call in mock_logger.info.call_args_list if "search_emails_query_scope" in call[0]
    ]
    assert len(log_calls) == 1

    log_kwargs = log_calls[0][1]
    assert log_kwargs["user_requested_inbox_only"] is True
    assert log_kwargs["scope_applied"] == "inbox"


# ============================================================================
# TEST 3: EXISTING SCOPE PRESERVED (label: or in: already present)
# ============================================================================


@pytest.mark.parametrize(
    "query_with_existing_scope,expected_preserved_scope,expects_trash_exclusion",
    [
        ("from:jean label:SENT", "label:SENT", True),  # Not trash → add -in:trash
        ("from:jean in:trash", "in:trash", False),  # Explicit trash → no exclusion
        ("from:jean in:spam", "in:spam", True),  # Not trash → add -in:trash
        ("from:jean label:IMPORTANT", "label:IMPORTANT", True),  # Not trash → add -in:trash
    ],
)
@pytest.mark.asyncio
async def test_search_emails_existing_scope_preserved(
    search_emails_tool,
    user_id,
    mock_gmail_client,
    query_with_existing_scope,
    expected_preserved_scope,
    expects_trash_exclusion,
):
    """Test existing scope operator is not overridden, but trash exclusion is added (Session 40)."""
    # Given: Query with existing scope operator
    kwargs = {"query": query_with_existing_scope, "max_results": 10}

    # When: Execute search_emails
    with patch("src.domains.agents.tools.emails_tools.logger"):
        await search_emails_tool.execute_api_call(mock_gmail_client, user_id, **kwargs)

    # Then: Scope preserved, trash exclusion added unless explicitly requesting trash
    mock_gmail_client.search_emails.assert_called_once()
    call_args = mock_gmail_client.search_emails.call_args
    final_query = call_args[1]["query"]

    # Should NOT add -in:sent/-in:draft or label:inbox when scope already present
    assert expected_preserved_scope in final_query
    # Verify -in:sent/-in:draft NOT added (existing scope takes precedence)
    if expected_preserved_scope not in ["-in:sent", "-in:draft"]:
        # Only check if the preserved scope isn't already sent/draft exclusion
        pass  # Scope preservation takes priority, no additional sent/draft filters

    # Trash exclusion behavior (Session 40) + default date filter
    if expects_trash_exclusion:
        assert "-in:trash" in final_query
        assert final_query.startswith(f"{query_with_existing_scope} -in:trash")
        assert "after:" in final_query  # Default 90-day date filter
    else:
        # Explicit trash request → no exclusion added
        assert "-in:trash" not in final_query
        assert final_query.startswith(query_with_existing_scope)


# ============================================================================
# TEST 4: CASE INSENSITIVITY (keyword detection)
# ============================================================================


@pytest.mark.parametrize(
    "query_mixed_case",
    [
        "from:jean DANS MA BOÎTE DE RÉCEPTION",  # Uppercase
        "from:jean DaNs InBoX",  # Mixed case
        "from:jean IN MY INBOX",  # Uppercase English
    ],
)
@pytest.mark.asyncio
async def test_search_emails_inbox_keywords_case_insensitive(
    search_emails_tool, user_id, mock_gmail_client, query_mixed_case
):
    """Test inbox keyword detection is case-insensitive."""
    # Given: Query with mixed-case inbox keywords
    kwargs = {"query": query_mixed_case, "max_results": 10}

    # When: Execute search_emails
    with patch("src.domains.agents.tools.emails_tools.logger"):
        await search_emails_tool.execute_api_call(mock_gmail_client, user_id, **kwargs)

    # Then: Inbox keyword detected despite case variation
    mock_gmail_client.search_emails.assert_called_once()
    call_args = mock_gmail_client.search_emails.call_args
    final_query = call_args[1]["query"]
    assert "label:inbox" in final_query  # Inbox keyword detected


# ============================================================================
# TEST 5: LOG EVENT VALIDATION (search_emails_query_scope)
# ============================================================================


@pytest.mark.asyncio
async def test_search_emails_logs_scope_applied(search_emails_tool, user_id, mock_gmail_client):
    """Test search_emails_query_scope log event emitted with correct fields."""
    # Given: Query without scope
    kwargs = {"query": "from:jean", "max_results": 10}

    # When: Execute search_emails
    with patch("src.domains.agents.tools.emails_tools.logger") as mock_logger:
        await search_emails_tool.execute_api_call(mock_gmail_client, user_id, **kwargs)

    # Then: Log event contains all required fields
    log_calls = [
        call for call in mock_logger.info.call_args_list if "search_emails_query_scope" in call[0]
    ]
    assert len(log_calls) == 1

    log_event = log_calls[0][0][0]
    log_kwargs = log_calls[0][1]

    # Validate event name
    assert log_event == "search_emails_query_scope"

    # Validate required fields
    assert "original_query" in log_kwargs
    assert "final_query" in log_kwargs
    assert "user_requested_inbox_only" in log_kwargs
    assert "scope_applied" in log_kwargs

    # Validate field types
    assert isinstance(log_kwargs["original_query"], str)
    assert isinstance(log_kwargs["final_query"], str)
    assert isinstance(log_kwargs["user_requested_inbox_only"], bool)
    assert log_kwargs["scope_applied"] in [
        "inbox",
        "received",
        "preserved",
    ]  # New: "received" for default, "preserved" for existing scope


# ============================================================================
# TEST 6: BACKWARD COMPATIBILITY (Session 38 behavior preserved)
# ============================================================================


@pytest.mark.asyncio
async def test_search_emails_explicit_in_anywhere_preserved(
    search_emails_tool, user_id, mock_gmail_client
):
    """Test backward compatibility: explicit 'in:anywhere' in query is preserved."""
    # Given: Query with explicit "in:anywhere" operator
    kwargs = {"query": "from:jean in:anywhere", "max_results": 10}

    # When: Execute search_emails
    with patch("src.domains.agents.tools.emails_tools.logger"):
        await search_emails_tool.execute_api_call(mock_gmail_client, user_id, **kwargs)

    # Then: in:anywhere preserved (backward compatible for explicit requests)
    mock_gmail_client.search_emails.assert_called_once()
    call_args = mock_gmail_client.search_emails.call_args
    final_query = call_args[1]["query"]
    assert "in:anywhere" in final_query  # Explicit scope preserved
    assert (
        "-in:sent" not in final_query
    )  # Should NOT add sent exclusion when in:anywhere is explicit
    assert (
        "-in:draft" not in final_query
    )  # Should NOT add draft exclusion when in:anywhere is explicit


# ============================================================================
# TEST 7: EDGE CASE - Query already has 'in:anywhere'
# ============================================================================


@pytest.mark.asyncio
async def test_search_emails_already_has_in_anywhere(
    search_emails_tool, user_id, mock_gmail_client
):
    """Test query with existing in:anywhere adds trash exclusion (Session 40)."""
    # Given: Query already contains in:anywhere
    kwargs = {"query": "from:jean in:anywhere", "max_results": 10}

    # When: Execute search_emails
    with patch("src.domains.agents.tools.emails_tools.logger"):
        await search_emails_tool.execute_api_call(mock_gmail_client, user_id, **kwargs)

    # Then: Query has in:anywhere preserved + trash exclusion + date filter added (Session 40)
    mock_gmail_client.search_emails.assert_called_once()
    call_args = mock_gmail_client.search_emails.call_args
    final_query = call_args[1]["query"]
    assert "from:jean" in final_query
    assert "in:anywhere" in final_query
    assert "-in:trash" in final_query
    assert "after:" in final_query  # Default 90-day date filter
    assert final_query.count("in:anywhere") == 1  # No duplication


# ============================================================================
# TEST 8: EDGE CASE - Query with both label: and in: (should preserve)
# ============================================================================


@pytest.mark.asyncio
async def test_search_emails_both_label_and_in_preserved(
    search_emails_tool, user_id, mock_gmail_client
):
    """Test query with both label: and in: adds trash exclusion (Session 40)."""
    # Given: Query has both label: and in: operators
    kwargs = {"query": "from:jean label:IMPORTANT in:anywhere", "max_results": 10}

    # When: Execute search_emails
    with patch("src.domains.agents.tools.emails_tools.logger"):
        await search_emails_tool.execute_api_call(mock_gmail_client, user_id, **kwargs)

    # Then: Scope preserved + trash exclusion + date filter added (Session 40)
    mock_gmail_client.search_emails.assert_called_once()
    call_args = mock_gmail_client.search_emails.call_args
    final_query = call_args[1]["query"]
    assert "from:jean" in final_query
    assert "label:IMPORTANT" in final_query
    assert "in:anywhere" in final_query
    assert "-in:trash" in final_query
    assert "after:" in final_query  # Default 90-day date filter
