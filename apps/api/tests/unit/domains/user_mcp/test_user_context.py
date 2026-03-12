"""Tests for user MCP session context manager and setup/cleanup functions."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.context import UserMCPToolsContext, user_mcp_tools_ctx
from src.infrastructure.mcp.user_context import (
    cleanup_user_mcp_tools,
    setup_user_mcp_tools,
    user_mcp_session,
)


class TestSetupUserMCPTools:
    """Tests for setup_user_mcp_tools standalone function."""

    @pytest.mark.asyncio
    @patch("src.infrastructure.mcp.user_context.settings")
    async def test_disabled_returns_none(self, mock_settings) -> None:
        """Should return None immediately when feature is disabled."""
        mock_settings.mcp_user_enabled = False
        token = await setup_user_mcp_tools(uuid4(), AsyncMock())
        assert token is None

    @pytest.mark.asyncio
    @patch("src.infrastructure.mcp.user_context.settings")
    @patch("src.domains.user_mcp.repository.UserMCPServerRepository")
    async def test_no_servers_returns_none(self, mock_repo_cls, mock_settings) -> None:
        """Should return None when user has no active servers."""
        mock_settings.mcp_user_enabled = True
        mock_repo = AsyncMock()
        mock_repo.get_enabled_active_for_user = AsyncMock(return_value=[])
        mock_repo_cls.return_value = mock_repo

        token = await setup_user_mcp_tools(uuid4(), AsyncMock())
        assert token is None

    @pytest.mark.asyncio
    @patch("src.infrastructure.mcp.user_context.settings")
    @patch("src.domains.user_mcp.repository.UserMCPServerRepository")
    @patch("src.infrastructure.mcp.user_context.get_user_mcp_pool")
    async def test_pool_not_initialized_returns_none(
        self, mock_get_pool, mock_repo_cls, mock_settings
    ) -> None:
        """Should return None when pool is not initialized."""
        mock_settings.mcp_user_enabled = True
        mock_repo = AsyncMock()
        server = MagicMock()
        server.id = uuid4()
        server.name = "Test"
        server.url = "https://example.com"
        mock_repo.get_enabled_active_for_user = AsyncMock(return_value=[server])
        mock_repo_cls.return_value = mock_repo
        mock_get_pool.return_value = None

        token = await setup_user_mcp_tools(uuid4(), AsyncMock())
        assert token is None

    @pytest.mark.asyncio
    @patch("src.infrastructure.mcp.user_context.settings")
    @patch("src.domains.user_mcp.repository.UserMCPServerRepository")
    @patch("src.infrastructure.mcp.user_context.get_user_mcp_pool")
    @patch("src.infrastructure.mcp.user_context.build_auth_for_server")
    async def test_server_connect_failure_is_resilient(
        self, mock_build_auth, mock_get_pool, mock_repo_cls, mock_settings
    ) -> None:
        """Should skip server on connection failure without raising."""
        mock_settings.mcp_user_enabled = True
        mock_settings.mcp_hitl_required = True

        server = MagicMock()
        server.id = uuid4()
        server.name = "Failing Server"
        server.url = "https://fail.example.com"
        server.auth_type = "none"
        server.credentials_encrypted = None
        server.timeout_seconds = 30
        server.hitl_required = None

        mock_repo = AsyncMock()
        mock_repo.get_enabled_active_for_user = AsyncMock(return_value=[server])
        mock_repo_cls.return_value = mock_repo

        mock_pool = AsyncMock()
        mock_pool.get_or_connect = AsyncMock(side_effect=RuntimeError("connection refused"))
        mock_get_pool.return_value = mock_pool
        mock_build_auth.return_value = MagicMock()

        # Should NOT raise — failure is logged and skipped
        token = await setup_user_mcp_tools(uuid4(), AsyncMock())
        assert token is None  # No tools available → no ContextVar set

    @pytest.mark.asyncio
    @patch("src.infrastructure.mcp.user_context.settings")
    @patch("src.domains.user_mcp.repository.UserMCPServerRepository")
    @patch("src.infrastructure.mcp.user_context.get_user_mcp_pool")
    @patch("src.infrastructure.mcp.user_context.build_auth_for_server")
    @patch("src.infrastructure.mcp.user_context._build_user_tool_manifest")
    async def test_sets_context_var(
        self, mock_manifest, mock_build_auth, mock_get_pool, mock_repo_cls, mock_settings
    ) -> None:
        """Should set ContextVar when tools are discovered."""
        mock_settings.mcp_user_enabled = True
        mock_settings.mcp_hitl_required = True

        server = MagicMock()
        server.id = uuid4()
        server.name = "Good Server"
        server.url = "https://good.example.com"
        server.timeout_seconds = 30
        server.hitl_required = None
        server.domain_description = None
        server.tool_embeddings_cache = None

        mock_repo = AsyncMock()
        mock_repo.get_enabled_active_for_user = AsyncMock(return_value=[server])
        mock_repo_cls.return_value = mock_repo

        entry = MagicMock()
        entry.tools = [
            {"name": "test_tool", "description": "Test", "input_schema": {}},
        ]

        mock_pool = AsyncMock()
        mock_pool.get_or_connect = AsyncMock(return_value=entry)
        mock_get_pool.return_value = mock_pool
        mock_build_auth.return_value = MagicMock()
        mock_manifest.return_value = MagicMock()

        user_id = uuid4()
        db = AsyncMock()

        token = await setup_user_mcp_tools(user_id, db)
        try:
            assert token is not None
            ctx = user_mcp_tools_ctx.get()
            assert ctx is not None
            assert len(ctx.tool_instances) == 1
        finally:
            cleanup_user_mcp_tools(token)

    @pytest.mark.asyncio
    @patch("src.infrastructure.mcp.user_context.settings")
    @patch("src.domains.user_mcp.repository.UserMCPServerRepository")
    @patch("src.infrastructure.mcp.user_context.get_user_mcp_pool")
    @patch("src.infrastructure.mcp.user_context.build_auth_for_server")
    @patch("src.infrastructure.mcp.user_context._build_user_tool_manifest")
    async def test_loads_server_descriptions(
        self, mock_manifest, mock_build_auth, mock_get_pool, mock_repo_cls, mock_settings
    ) -> None:
        """Should populate server_descriptions from domain_description."""
        mock_settings.mcp_user_enabled = True
        mock_settings.mcp_hitl_required = True

        server = MagicMock()
        server.id = uuid4()
        server.name = "HuggingFace"
        server.url = "https://hf.example.com"
        server.timeout_seconds = 30
        server.hitl_required = None
        server.domain_description = "Search ML models on HuggingFace Hub"
        server.tool_embeddings_cache = None

        mock_repo = AsyncMock()
        mock_repo.get_enabled_active_for_user = AsyncMock(return_value=[server])
        mock_repo_cls.return_value = mock_repo

        entry = MagicMock()
        entry.tools = [
            {"name": "hub_search", "description": "Search HF Hub", "input_schema": {}},
        ]

        mock_pool = AsyncMock()
        mock_pool.get_or_connect = AsyncMock(return_value=entry)
        mock_get_pool.return_value = mock_pool
        mock_build_auth.return_value = MagicMock()
        mock_manifest.return_value = MagicMock()

        token = await setup_user_mcp_tools(uuid4(), AsyncMock())
        try:
            ctx = user_mcp_tools_ctx.get()
            assert ctx is not None
            assert "HuggingFace" in ctx.server_descriptions
            assert ctx.server_descriptions["HuggingFace"] == "Search ML models on HuggingFace Hub"
        finally:
            cleanup_user_mcp_tools(token)

    @pytest.mark.asyncio
    @patch("src.infrastructure.mcp.user_context.settings")
    @patch("src.domains.user_mcp.repository.UserMCPServerRepository")
    @patch("src.infrastructure.mcp.user_context.get_user_mcp_pool")
    @patch("src.infrastructure.mcp.user_context.build_auth_for_server")
    @patch("src.infrastructure.mcp.user_context._build_user_tool_manifest")
    async def test_rekeys_embeddings_to_adapter_names(
        self, mock_manifest, mock_build_auth, mock_get_pool, mock_repo_cls, mock_settings
    ) -> None:
        """Should re-key embeddings from raw MCP names to adapter names."""
        mock_settings.mcp_user_enabled = True
        mock_settings.mcp_hitl_required = True

        server = MagicMock()
        server.id = uuid4()
        server.name = "TestServer"
        server.url = "https://example.com"
        server.timeout_seconds = 30
        server.hitl_required = None
        server.domain_description = None
        # Embeddings stored by raw MCP tool name
        server.tool_embeddings_cache = {
            "hub_search": {"description": [0.1, 0.2], "keywords": [[0.3, 0.4]]},
        }

        mock_repo = AsyncMock()
        mock_repo.get_enabled_active_for_user = AsyncMock(return_value=[server])
        mock_repo_cls.return_value = mock_repo

        entry = MagicMock()
        entry.tools = [
            {"name": "hub_search", "description": "Search", "input_schema": {}},
        ]

        mock_pool = AsyncMock()
        mock_pool.get_or_connect = AsyncMock(return_value=entry)
        mock_get_pool.return_value = mock_pool
        mock_build_auth.return_value = MagicMock()

        # The adapter's name will be the prefixed version
        adapter_mock = MagicMock()
        adapter_name = f"mcp_user_{str(server.id)[:8]}_hub_search"
        adapter_mock.name = adapter_name
        mock_manifest.return_value = MagicMock()

        from src.infrastructure.mcp.user_tool_adapter import UserMCPToolAdapter

        with patch.object(UserMCPToolAdapter, "from_discovered_tool", return_value=adapter_mock):
            token = await setup_user_mcp_tools(uuid4(), AsyncMock())
            try:
                ctx = user_mcp_tools_ctx.get()
                assert ctx is not None
                # Embeddings should be re-keyed from "hub_search" to adapter_name
                assert adapter_name in ctx.tool_embeddings
                assert ctx.tool_embeddings[adapter_name]["description"] == [0.1, 0.2]
            finally:
                cleanup_user_mcp_tools(token)


class TestResolveToolName:
    """Tests for UserMCPToolsContext.resolve_tool_name fuzzy matching."""

    def _make_ctx_with_manifests(self, names: list[str]) -> UserMCPToolsContext:
        """Create context with mock tool manifests having given names."""
        ctx = UserMCPToolsContext()
        for name in names:
            m = MagicMock()
            m.name = name
            ctx.tool_manifests.append(m)
        return ctx

    def test_exact_match(self) -> None:
        """Should return exact name when it matches."""
        ctx = self._make_ctx_with_manifests(["mcp_user_37e4_hub_repo_search"])
        assert (
            ctx.resolve_tool_name("mcp_user_37e4_hub_repo_search")
            == "mcp_user_37e4_hub_repo_search"
        )

    def test_strip_tool_suffix(self) -> None:
        """Should strip '_tool' suffix hallucinated by planner LLM."""
        ctx = self._make_ctx_with_manifests(["mcp_user_37e4_hub_repo_search"])
        assert (
            ctx.resolve_tool_name("mcp_user_37e4_hub_repo_search_tool")
            == "mcp_user_37e4_hub_repo_search"
        )

    def test_strip_action_suffix(self) -> None:
        """Should strip '_action' suffix hallucinated by planner LLM."""
        ctx = self._make_ctx_with_manifests(["mcp_user_37e4_space_search"])
        assert (
            ctx.resolve_tool_name("mcp_user_37e4_space_search_action")
            == "mcp_user_37e4_space_search"
        )

    def test_no_match_returns_none(self) -> None:
        """Should return None when no match found."""
        ctx = self._make_ctx_with_manifests(["mcp_user_37e4_hub_repo_search"])
        assert ctx.resolve_tool_name("completely_different_tool") is None

    def test_suffix_strip_no_false_positive(self) -> None:
        """Should not strip suffix if the stripped name doesn't match either."""
        ctx = self._make_ctx_with_manifests(["mcp_user_37e4_hub_repo_search"])
        assert ctx.resolve_tool_name("mcp_user_37e4_other_tool") is None

    def test_native_tool_unaffected(self) -> None:
        """Should return None for native tools not in user MCP context."""
        ctx = self._make_ctx_with_manifests(["mcp_user_37e4_hub_search"])
        assert ctx.resolve_tool_name("unified_web_search_tool") is None

    def test_empty_manifests(self) -> None:
        """Should return None when no manifests registered."""
        ctx = UserMCPToolsContext()
        assert ctx.resolve_tool_name("any_tool") is None

    def test_exact_match_preferred_over_fuzzy(self) -> None:
        """Exact match should be returned even if fuzzy would also match."""
        ctx = self._make_ctx_with_manifests(
            [
                "mcp_user_37e4_search",
                "mcp_user_37e4_search_tool",  # This IS a real tool name
            ]
        )
        assert ctx.resolve_tool_name("mcp_user_37e4_search_tool") == "mcp_user_37e4_search_tool"


class TestCleanupUserMCPTools:
    """Tests for cleanup_user_mcp_tools."""

    def test_cleanup_none_token_is_noop(self) -> None:
        """Should be safe to call with None token."""
        cleanup_user_mcp_tools(None)  # Should not raise

    def test_cleanup_resets_context_var(self) -> None:
        """Should reset ContextVar to None."""
        ctx = UserMCPToolsContext()
        token = user_mcp_tools_ctx.set(ctx)
        assert user_mcp_tools_ctx.get() is ctx

        cleanup_user_mcp_tools(token)
        assert user_mcp_tools_ctx.get() is None


class TestUserMCPSessionContextManager:
    """Tests for the user_mcp_session context manager wrapper."""

    @pytest.mark.asyncio
    @patch("src.infrastructure.mcp.user_context.settings")
    async def test_disabled_feature_yields(self, mock_settings) -> None:
        """Should yield immediately when feature disabled."""
        mock_settings.mcp_user_enabled = False
        async with user_mcp_session(uuid4(), AsyncMock()):
            # Should reach here without error
            pass

    @pytest.mark.asyncio
    @patch("src.infrastructure.mcp.user_context.setup_user_mcp_tools")
    @patch("src.infrastructure.mcp.user_context.cleanup_user_mcp_tools")
    async def test_cleanup_called_on_exception(self, mock_cleanup, mock_setup) -> None:
        """Should call cleanup even when exception occurs in body."""
        mock_token = MagicMock()
        mock_setup.return_value = mock_token

        with pytest.raises(ValueError, match="test error"):
            async with user_mcp_session(uuid4(), AsyncMock()):
                raise ValueError("test error")

        mock_cleanup.assert_called_once_with(mock_token)
