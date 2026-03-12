"""
Tests for Perplexity tools.

LOT 10: Tests for Perplexity web search integration.

Updated for APIKeyConnectorTool architecture that retrieves user-specific
API keys from the database via ToolDependencies.

Updated for StandardToolOutput format with Data Registry support.
"""

import json
from unittest.mock import AsyncMock, MagicMock, create_autospec, patch
from uuid import uuid4

import pytest
from langgraph.prebuilt.tool_node import ToolRuntime

from src.domains.agents.tools.output import StandardToolOutput
from src.domains.connectors.schemas import APIKeyCredentials


def create_mock_api_key_dependencies(
    api_key_credentials: APIKeyCredentials | None = None,
) -> MagicMock:
    """Create a mock ToolDependencies for API key connectors.

    Args:
        api_key_credentials: Credentials to return from get_api_key_credentials.
            If None, simulates disabled connector.
    """
    mock_deps = MagicMock()

    # Mock connector service with get_api_key_credentials
    mock_connector_service = MagicMock()
    mock_connector_service.get_api_key_credentials = AsyncMock(return_value=api_key_credentials)
    mock_deps.get_connector_service = AsyncMock(return_value=mock_connector_service)

    # Mock db property
    mock_deps.db = MagicMock()

    return mock_deps


def create_mock_runtime(user_id: str) -> ToolRuntime:
    """Create a mock ToolRuntime with configurable user_id."""
    runtime = create_autospec(ToolRuntime, instance=True)
    configurable = {
        "user_id": user_id,
        "thread_id": f"test_thread_{user_id[:8]}",
    }

    runtime.config = {"configurable": configurable}
    mock_store = MagicMock()
    mock_store.get = MagicMock(return_value=None)
    mock_store.put = MagicMock()
    runtime.store = mock_store
    runtime.state = {}
    runtime.context = {}
    runtime.stream_writer = MagicMock()
    runtime.tool_call_id = "test_call_id"
    return runtime


class TestPerplexitySearchTool:
    """Tests for perplexity_search_tool with APIKeyConnectorTool architecture."""

    @pytest.fixture
    def mock_credentials(self) -> APIKeyCredentials:
        """Create mock API key credentials."""
        return APIKeyCredentials(
            api_key="pplx-test-api-key-12345",
            key_name="Test Key",
        )

    @pytest.fixture
    def user_id(self) -> str:
        """Generate test user ID."""
        return str(uuid4())

    @pytest.mark.asyncio
    async def test_search_success(self, mock_credentials, user_id):
        """Test successful web search with user's API key."""
        from src.domains.agents.tools.perplexity_tools import _perplexity_search_tool_impl
        from src.domains.connectors.clients.perplexity_client import PerplexityClient

        # Create mock client
        mock_client = AsyncMock(spec=PerplexityClient)
        mock_client.search = AsyncMock(
            return_value={
                "answer": "AI developments include LLMs and multimodal models.",
                "citations": ["https://example.com/ai-news"],
                "related_questions": ["What are LLMs?"],
                "query": "Latest AI developments",
                "model": "sonar",
            }
        )

        # Create mock dependencies
        mock_deps = create_mock_api_key_dependencies(
            api_key_credentials=mock_credentials,
        )

        # Create runtime
        runtime = create_mock_runtime(user_id)

        # Patch get_dependencies to return our mock deps
        # AND patch create_client to return our mock client
        with patch(
            "src.domains.agents.tools.base.get_dependencies",
            return_value=mock_deps,
        ):
            original_create_client = _perplexity_search_tool_impl.create_client
            _perplexity_search_tool_impl.create_client = lambda creds, uid: mock_client

            try:
                result = await _perplexity_search_tool_impl.execute(
                    runtime,
                    query="Latest AI developments",
                )

                # Verify StandardToolOutput format
                assert isinstance(result, StandardToolOutput)
                assert (
                    "AI developments include LLMs and multimodal models." in result.summary_for_llm
                )
                assert len(result.registry_updates) == 1
                # Verify registry item
                registry_item = list(result.registry_updates.values())[0]
                assert (
                    registry_item.payload["answer"]
                    == "AI developments include LLMs and multimodal models."
                )
                assert registry_item.payload["citations"] == ["https://example.com/ai-news"]
                assert registry_item.payload["model"] == "sonar"
            finally:
                _perplexity_search_tool_impl.create_client = original_create_client

    @pytest.mark.asyncio
    async def test_search_with_recency_filter(self, mock_credentials, user_id):
        """Test search with recency filter."""
        from src.domains.agents.tools.perplexity_tools import _perplexity_search_tool_impl
        from src.domains.connectors.clients.perplexity_client import PerplexityClient

        mock_client = AsyncMock(spec=PerplexityClient)
        mock_client.search = AsyncMock(
            return_value={
                "answer": "Stock news from today",
                "citations": [],
                "related_questions": [],
                "query": "Stock market news",
                "model": "sonar",
            }
        )

        mock_deps = create_mock_api_key_dependencies(api_key_credentials=mock_credentials)
        runtime = create_mock_runtime(user_id)

        with patch(
            "src.domains.agents.tools.base.get_dependencies",
            return_value=mock_deps,
        ):
            original_create_client = _perplexity_search_tool_impl.create_client
            _perplexity_search_tool_impl.create_client = lambda creds, uid: mock_client

            try:
                result = await _perplexity_search_tool_impl.execute(
                    runtime,
                    query="Stock market news",
                    recency="day",
                )

                # Verify StandardToolOutput format
                assert isinstance(result, StandardToolOutput)
                assert "Stock news from today" in result.summary_for_llm
                # Verify recency filter was passed
                mock_client.search.assert_called_once()
                call_args = mock_client.search.call_args
                assert call_args.kwargs["search_recency_filter"] == "day"
            finally:
                _perplexity_search_tool_impl.create_client = original_create_client

    @pytest.mark.asyncio
    async def test_search_connector_not_activated(self, user_id):
        """Test handling when connector is not activated."""
        from src.domains.agents.tools.perplexity_tools import _perplexity_search_tool_impl

        # No credentials = connector not activated
        mock_deps = create_mock_api_key_dependencies(api_key_credentials=None)
        runtime = create_mock_runtime(user_id)

        with patch(
            "src.domains.agents.tools.base.get_dependencies",
            return_value=mock_deps,
        ):
            result = await _perplexity_search_tool_impl.execute(
                runtime,
                query="Test query",
            )

            data = json.loads(result)
            assert data["error"] == "connector_not_activated"
            assert "Perplexity" in data["message"]

    @pytest.mark.asyncio
    async def test_search_api_error(self, mock_credentials, user_id):
        """Test handling of API errors."""
        from src.domains.agents.tools.perplexity_tools import _perplexity_search_tool_impl
        from src.domains.connectors.clients.perplexity_client import PerplexityClient

        mock_client = AsyncMock(spec=PerplexityClient)
        mock_client.search = AsyncMock(side_effect=Exception("API Error"))

        mock_deps = create_mock_api_key_dependencies(api_key_credentials=mock_credentials)
        runtime = create_mock_runtime(user_id)

        with patch(
            "src.domains.agents.tools.base.get_dependencies",
            return_value=mock_deps,
        ):
            original_create_client = _perplexity_search_tool_impl.create_client
            _perplexity_search_tool_impl.create_client = lambda creds, uid: mock_client

            try:
                result = await _perplexity_search_tool_impl.execute(
                    runtime,
                    query="Test query",
                )

                data = json.loads(result)
                assert data["success"] is False
                assert "error" in data
            finally:
                _perplexity_search_tool_impl.create_client = original_create_client


class TestPerplexityAskTool:
    """Tests for perplexity_ask_tool with APIKeyConnectorTool architecture."""

    @pytest.fixture
    def mock_credentials(self) -> APIKeyCredentials:
        """Create mock API key credentials."""
        return APIKeyCredentials(
            api_key="pplx-test-api-key-12345",
            key_name="Test Key",
        )

    @pytest.fixture
    def user_id(self) -> str:
        """Generate test user ID."""
        return str(uuid4())

    @pytest.mark.asyncio
    async def test_ask_success(self, mock_credentials, user_id):
        """Test successful question answering with user's API key."""
        from src.domains.agents.tools.perplexity_tools import _perplexity_ask_tool_impl
        from src.domains.connectors.clients.perplexity_client import PerplexityClient

        mock_client = AsyncMock(spec=PerplexityClient)
        mock_client.ask = AsyncMock(
            return_value={
                "answer": "REST API design involves resources, HTTP methods, and status codes.",
                "citations": ["https://restfulapi.net"],
                "question": "Best practices for REST API design",
                "model": "sonar",
            }
        )

        mock_deps = create_mock_api_key_dependencies(api_key_credentials=mock_credentials)
        runtime = create_mock_runtime(user_id)

        with patch(
            "src.domains.agents.tools.base.get_dependencies",
            return_value=mock_deps,
        ):
            original_create_client = _perplexity_ask_tool_impl.create_client
            _perplexity_ask_tool_impl.create_client = lambda creds, uid: mock_client

            try:
                result = await _perplexity_ask_tool_impl.execute(
                    runtime,
                    question="Best practices for REST API design",
                )

                # Verify StandardToolOutput format
                assert isinstance(result, StandardToolOutput)
                assert "REST API design involves resources" in result.summary_for_llm
                assert len(result.registry_updates) == 1
                # Verify registry item
                registry_item = list(result.registry_updates.values())[0]
                assert (
                    registry_item.payload["answer"]
                    == "REST API design involves resources, HTTP methods, and status codes."
                )
                assert registry_item.payload["citations"] == ["https://restfulapi.net"]
            finally:
                _perplexity_ask_tool_impl.create_client = original_create_client

    @pytest.mark.asyncio
    async def test_ask_with_context(self, mock_credentials, user_id):
        """Test question with custom context."""
        from src.domains.agents.tools.perplexity_tools import _perplexity_ask_tool_impl
        from src.domains.connectors.clients.perplexity_client import PerplexityClient

        mock_client = AsyncMock(spec=PerplexityClient)
        mock_client.ask = AsyncMock(
            return_value={
                "answer": "Medical treatment options include...",
                "citations": [],
                "question": "Treatment options",
                "model": "sonar",
            }
        )

        mock_deps = create_mock_api_key_dependencies(api_key_credentials=mock_credentials)
        runtime = create_mock_runtime(user_id)

        with patch(
            "src.domains.agents.tools.base.get_dependencies",
            return_value=mock_deps,
        ):
            original_create_client = _perplexity_ask_tool_impl.create_client
            _perplexity_ask_tool_impl.create_client = lambda creds, uid: mock_client

            try:
                result = await _perplexity_ask_tool_impl.execute(
                    runtime,
                    question="Treatment options",
                    context="medical",
                )

                # Verify StandardToolOutput format
                assert isinstance(result, StandardToolOutput)
                assert "Medical treatment options include" in result.summary_for_llm
                assert "medical" in result.summary_for_llm  # Context in summary
                # Verify registry item has context
                registry_item = list(result.registry_updates.values())[0]
                assert registry_item.payload["context"] == "medical"
                # Verify system prompt was built with context
                mock_client.ask.assert_called_once()
                call_args = mock_client.ask.call_args
                assert "medical" in call_args.kwargs["system_prompt"]
            finally:
                _perplexity_ask_tool_impl.create_client = original_create_client

    @pytest.mark.asyncio
    async def test_ask_connector_not_activated(self, user_id):
        """Test handling when connector is not activated."""
        from src.domains.agents.tools.perplexity_tools import _perplexity_ask_tool_impl

        mock_deps = create_mock_api_key_dependencies(api_key_credentials=None)
        runtime = create_mock_runtime(user_id)

        with patch(
            "src.domains.agents.tools.base.get_dependencies",
            return_value=mock_deps,
        ):
            result = await _perplexity_ask_tool_impl.execute(
                runtime,
                question="Test question",
            )

            data = json.loads(result)
            assert data["error"] == "connector_not_activated"
            assert "Perplexity" in data["message"]
