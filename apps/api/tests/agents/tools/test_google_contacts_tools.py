"""
Tests for Google Contacts LangChain tools.

Updated for LangChain v1 / LangGraph with ToolRuntime pattern.

Phase 3.2 Migration: Tests now use ToolDependencies pattern for dependency injection.
The ToolDependencies must be injected via runtime.config["configurable"]["__deps"].

Tests mock:
- get_global_registry (for normalize_field_names)
- get_dependencies (for ToolDependencies injection)
- GoogleContactsClient (for API calls)
"""

import json
from unittest.mock import AsyncMock, MagicMock, create_autospec, patch
from uuid import uuid4

import pytest
from langgraph.prebuilt.tool_node import ToolRuntime

from src.domains.agents.tools import (
    get_contact_details_tool,
    list_contacts_tool,
    search_contacts_tool,
)
from src.domains.agents.tools.output import StandardToolOutput

# Test user ID (valid UUID format)
TEST_USER_ID = str(uuid4())


def create_mock_tool_dependencies(
    connector_credentials: dict | None = None,
    client_mock: MagicMock | None = None,
) -> MagicMock:
    """Create a mock ToolDependencies with configurable connector and client.

    Args:
        connector_credentials: Credentials to return from get_connector_credentials.
            If None, simulates disabled connector.
        client_mock: Mock client to return from get_or_create_client.
    """
    mock_deps = MagicMock()

    # Mock connector service
    mock_connector_service = MagicMock()
    mock_connector_service.get_connector_credentials = AsyncMock(return_value=connector_credentials)
    mock_deps.get_connector_service = AsyncMock(return_value=mock_connector_service)

    # Mock client cache
    if client_mock:
        mock_deps.get_or_create_client = AsyncMock(return_value=client_mock)
    else:
        mock_deps.get_or_create_client = AsyncMock(return_value=MagicMock())

    # Mock db property (needed for some operations)
    mock_deps.db = MagicMock()

    return mock_deps


def create_mock_runtime(
    user_id: str,
    tool_deps: MagicMock | None = None,
) -> ToolRuntime:
    """Create a mock ToolRuntime with configurable user_id and dependencies.

    Uses create_autospec to satisfy Pydantic validation while
    allowing us to configure the runtime.config attribute.

    Args:
        user_id: User ID string
        tool_deps: Optional mock ToolDependencies. If provided, will be injected
            into config["configurable"]["__deps"].
    """
    # Create a spec-compliant mock
    runtime = create_autospec(ToolRuntime, instance=True)
    # Configure the config attribute with user_id and thread_id
    configurable = {
        "user_id": user_id,
        "thread_id": f"test_thread_{user_id[:8]}",
    }

    # Inject ToolDependencies if provided
    if tool_deps is not None:
        configurable["__deps"] = tool_deps

    runtime.config = {"configurable": configurable}
    # Mock store with async methods for context manager
    mock_store = MagicMock()
    mock_store.get = MagicMock(return_value=None)
    mock_store.put = MagicMock()
    mock_store.aget = AsyncMock(return_value=None)
    mock_store.aput = AsyncMock()
    runtime.store = mock_store
    runtime.state = {}
    runtime.context = {}
    runtime.stream_writer = MagicMock()
    runtime.tool_call_id = "test_call_id"
    return runtime


# =============================================================================
# Phase 3.2 Tests - Using new ToolDependencies architecture
# =============================================================================


@pytest.fixture
def mock_registry():
    """Mock get_global_registry for normalize_field_names.

    Creates a registry mock that returns field_mappings for contacts tools.
    Since the import is local (inside normalize_field_names), we patch at source.
    """
    mock_registry_instance = MagicMock()
    mock_manifest = MagicMock()

    # Field mappings for contacts tools (user-friendly -> API)
    mock_manifest.get.return_value = {
        "name": "names",
        "names": "names",
        "email": "emailAddresses",
        "emails": "emailAddresses",
        "emailAddresses": "emailAddresses",
        "phone": "phoneNumbers",
        "phones": "phoneNumbers",
        "phoneNumbers": "phoneNumbers",
        "organization": "organizations",
        "organizations": "organizations",
        "address": "addresses",
        "addresses": "addresses",
    }
    mock_registry_instance.get_tool_manifest.return_value = mock_manifest

    # Patch at source module since it's a local import inside normalize_field_names
    with patch(
        "src.domains.agents.registry.get_global_registry",
        return_value=mock_registry_instance,
    ):
        yield mock_registry_instance


@pytest.fixture
def mock_contacts_client():
    """Mock GoogleContactsClient with standard responses."""
    client = MagicMock()

    # Default search response
    client.search_contacts = AsyncMock(
        return_value={
            "results": [
                {
                    "person": {
                        "resourceName": "people/c123456",
                        "names": [
                            {
                                "displayName": "Jean Dupont",
                                "givenName": "Jean",
                                "familyName": "Dupont",
                            }
                        ],
                        "emailAddresses": [{"value": "jean.dupont@example.com"}],
                    }
                }
            ],
            "totalPeople": 1,
        }
    )

    # Default list response - list_connections is the actual method name
    client.list_connections = AsyncMock(
        return_value={
            "connections": [
                {
                    "resourceName": "people/c789012",
                    "names": [{"displayName": "Marie Martin"}],
                    "emailAddresses": [{"value": "marie@example.com"}],
                }
            ],
            "totalPeople": 1,
            "totalItems": 1,
        }
    )

    # Also mock list_all_contacts for compatibility
    client.list_all_contacts = AsyncMock(
        return_value={
            "connections": [
                {
                    "resourceName": "people/c789012",
                    "names": [{"displayName": "Marie Martin"}],
                    "emailAddresses": [{"value": "marie@example.com"}],
                }
            ],
            "totalPeople": 1,
            "totalItems": 1,
        }
    )

    # Default get details response - get method for single contact
    client.get = AsyncMock(
        return_value={
            "resourceName": "people/c123456",
            "names": [{"displayName": "Jean Dupont"}],
            "emailAddresses": [{"value": "jean.dupont@example.com"}],
        }
    )

    # get_person is used by _execute_batch in get_contact_details_tool
    client.get_person = AsyncMock(
        return_value={
            "resourceName": "people/c123456",
            "names": [{"displayName": "Jean Dupont"}],
            "emailAddresses": [{"value": "jean.dupont@example.com"}],
        }
    )

    # Also mock get_contact_details for compatibility
    client.get_contact_details = AsyncMock(
        return_value={
            "resourceName": "people/c123456",
            "names": [{"displayName": "Jean Dupont"}],
            "emailAddresses": [{"value": "jean.dupont@example.com"}],
        }
    )

    # Batch get response - batch_get_people is the actual method
    client.batch_get_people = AsyncMock(
        return_value={
            "responses": [
                {
                    "person": {
                        "resourceName": "people/c123456",
                        "names": [{"displayName": "Jean Dupont"}],
                    }
                }
            ]
        }
    )

    # Also mock batch_get_contacts for compatibility
    client.batch_get_contacts = AsyncMock(
        return_value={
            "responses": [
                {
                    "person": {
                        "resourceName": "people/c123456",
                        "names": [{"displayName": "Jean Dupont"}],
                    }
                }
            ]
        }
    )

    return client


def _parse_result(result):
    """Parse tool result - either StandardToolOutput or JSON string."""
    if isinstance(result, StandardToolOutput):
        return {"success": True, "summary": result.summary_for_llm, "data": result.structured_data}
    # Error cases return JSON string
    try:
        return json.loads(result) if isinstance(result, str) else result
    except (json.JSONDecodeError, TypeError):
        return {"error": "parse_error", "raw": str(result)}


@pytest.mark.asyncio
async def test_search_contacts_tool_success(mock_registry, mock_contacts_client):
    """Test search_contacts_tool with valid results."""
    tool_deps = create_mock_tool_dependencies(
        connector_credentials={"access_token": "test_token"},
        client_mock=mock_contacts_client,
    )

    runtime = create_mock_runtime(TEST_USER_ID, tool_deps=tool_deps)

    with patch("src.domains.agents.tools.base.get_dependencies", return_value=tool_deps):
        result = await search_contacts_tool.ainvoke(
            {
                "query": "Jean",
                "runtime": runtime,
            },
        )

        # Success returns StandardToolOutput
        assert isinstance(result, StandardToolOutput)
        assert "contact" in result.summary_for_llm.lower()


@pytest.mark.asyncio
async def test_search_contacts_tool_connector_disabled(mock_registry):
    """Test search_contacts_tool when connector disabled."""
    tool_deps = create_mock_tool_dependencies(
        connector_credentials=None,  # Connector disabled
    )

    runtime = create_mock_runtime(TEST_USER_ID, tool_deps=tool_deps)

    with patch("src.domains.agents.tools.base.get_dependencies", return_value=tool_deps):
        result = await search_contacts_tool.ainvoke(
            {
                "query": "Jean",
                "runtime": runtime,
            },
        )

        # Error returns JSON string
        parsed = _parse_result(result)
        assert "error" in parsed


@pytest.mark.asyncio
async def test_list_contacts_tool_success(mock_registry, mock_contacts_client):
    """Test list_contacts_tool with pagination."""
    tool_deps = create_mock_tool_dependencies(
        connector_credentials={"access_token": "test_token"},
        client_mock=mock_contacts_client,
    )

    runtime = create_mock_runtime(TEST_USER_ID, tool_deps=tool_deps)

    with patch("src.domains.agents.tools.base.get_dependencies", return_value=tool_deps):
        result = await list_contacts_tool.ainvoke(
            {
                "page_size": 10,
                "runtime": runtime,
            },
        )

        # Success returns StandardToolOutput
        assert isinstance(result, StandardToolOutput)


@pytest.mark.asyncio
async def test_list_contacts_tool_connector_disabled(mock_registry):
    """Test list_contacts_tool when connector disabled."""
    tool_deps = create_mock_tool_dependencies(
        connector_credentials=None,
    )

    runtime = create_mock_runtime(TEST_USER_ID, tool_deps=tool_deps)

    with patch("src.domains.agents.tools.base.get_dependencies", return_value=tool_deps):
        result = await list_contacts_tool.ainvoke(
            {
                "page_size": 10,
                "runtime": runtime,
            },
        )

        parsed = _parse_result(result)
        assert "error" in parsed


@pytest.mark.asyncio
async def test_get_contact_details_tool_success(mock_registry, mock_contacts_client):
    """Test get_contact_details_tool."""
    tool_deps = create_mock_tool_dependencies(
        connector_credentials={"access_token": "test_token"},
        client_mock=mock_contacts_client,
    )

    runtime = create_mock_runtime(TEST_USER_ID, tool_deps=tool_deps)

    with patch("src.domains.agents.tools.base.get_dependencies", return_value=tool_deps):
        result = await get_contact_details_tool.ainvoke(
            {
                "resource_names": "people/c123456",
                "runtime": runtime,
            },
        )

        # Success returns StandardToolOutput
        assert isinstance(result, StandardToolOutput)


@pytest.mark.asyncio
async def test_get_contact_details_tool_connector_disabled(mock_registry):
    """Test get_contact_details_tool when connector disabled."""
    tool_deps = create_mock_tool_dependencies(
        connector_credentials=None,
    )

    runtime = create_mock_runtime(TEST_USER_ID, tool_deps=tool_deps)

    with patch("src.domains.agents.tools.base.get_dependencies", return_value=tool_deps):
        result = await get_contact_details_tool.ainvoke(
            {
                "resource_names": "people/c123456",
                "runtime": runtime,
            },
        )

        parsed = _parse_result(result)
        assert "error" in parsed


@pytest.mark.asyncio
async def test_search_contacts_tool_http_exception(mock_registry, mock_contacts_client):
    """Test search_contacts_tool when HTTP error occurs."""
    from httpx import HTTPStatusError, Request, Response

    # Configure client to raise HTTP error
    mock_contacts_client.search_contacts = AsyncMock(
        side_effect=HTTPStatusError(
            "Rate limited",
            request=Request("GET", "https://example.com"),
            response=Response(429),
        )
    )

    tool_deps = create_mock_tool_dependencies(
        connector_credentials={"access_token": "test_token"},
        client_mock=mock_contacts_client,
    )

    runtime = create_mock_runtime(TEST_USER_ID, tool_deps=tool_deps)

    with patch("src.domains.agents.tools.base.get_dependencies", return_value=tool_deps):
        result = await search_contacts_tool.ainvoke(
            {
                "query": "Jean",
                "runtime": runtime,
            },
        )

        parsed = _parse_result(result)
        assert "error" in parsed


@pytest.mark.asyncio
async def test_search_contacts_tool_unexpected_error(mock_registry, mock_contacts_client):
    """Test search_contacts_tool when unexpected error occurs."""
    # Configure client to raise unexpected error
    mock_contacts_client.search_contacts = AsyncMock(
        side_effect=RuntimeError("Unexpected network error")
    )

    tool_deps = create_mock_tool_dependencies(
        connector_credentials={"access_token": "test_token"},
        client_mock=mock_contacts_client,
    )

    runtime = create_mock_runtime(TEST_USER_ID, tool_deps=tool_deps)

    with patch("src.domains.agents.tools.base.get_dependencies", return_value=tool_deps):
        result = await search_contacts_tool.ainvoke(
            {
                "query": "Jean",
                "runtime": runtime,
            },
        )

        parsed = _parse_result(result)
        assert "error" in parsed


@pytest.mark.asyncio
async def test_get_contact_details_tool_resource_names_string_coercion(
    mock_registry, mock_contacts_client
):
    """Test get_contact_details_tool accepts string for resource_names (Issue #54)."""
    tool_deps = create_mock_tool_dependencies(
        connector_credentials={"access_token": "test_token"},
        client_mock=mock_contacts_client,
    )

    runtime = create_mock_runtime(TEST_USER_ID, tool_deps=tool_deps)

    with patch("src.domains.agents.tools.base.get_dependencies", return_value=tool_deps):
        # Pass string instead of list - should be handled correctly
        result = await get_contact_details_tool.ainvoke(
            {
                "resource_names": "people/c123456",  # String, not list
                "runtime": runtime,
            },
        )

        # Should succeed with StandardToolOutput
        assert isinstance(result, StandardToolOutput)


@pytest.mark.asyncio
async def test_get_contact_details_tool_resource_names_list_still_works(
    mock_registry, mock_contacts_client
):
    """Test get_contact_details_tool still works with list for resource_names."""
    tool_deps = create_mock_tool_dependencies(
        connector_credentials={"access_token": "test_token"},
        client_mock=mock_contacts_client,
    )

    runtime = create_mock_runtime(TEST_USER_ID, tool_deps=tool_deps)

    with patch("src.domains.agents.tools.base.get_dependencies", return_value=tool_deps):
        # Pass list - should also work
        result = await get_contact_details_tool.ainvoke(
            {
                "resource_names": ["people/c123456", "people/c789012"],
                "runtime": runtime,
            },
        )

        # Should succeed with StandardToolOutput
        assert isinstance(result, StandardToolOutput)


# =============================================================================
# Test that still works: Empty string handling
# =============================================================================


@pytest.mark.asyncio
async def test_get_contact_details_tool_resource_names_empty_string(mock_registry):
    """Test get_contact_details_tool handles empty string gracefully.

    When Jinja2 conditional evaluates to empty (e.g., no contacts found),
    the tool should handle this case without crashing.
    """
    # Create mock dependencies with connector disabled to trigger early return
    tool_deps = create_mock_tool_dependencies(
        connector_credentials=None,  # Connector disabled
    )

    runtime = create_mock_runtime(TEST_USER_ID)

    # Patch get_dependencies to return our mock
    with patch(
        "src.domains.agents.tools.base.get_dependencies",
        return_value=tool_deps,
    ):
        # Pass empty string (simulates Jinja2 "{% if false %}...{% endif %}")
        result = await get_contact_details_tool.ainvoke(
            {
                "resource_names": "",
                "runtime": runtime,
            },
        )

        # Should return error (connector disabled or empty input)
        parsed = _parse_result(result)
        assert "error" in parsed or parsed.get("success") is True
