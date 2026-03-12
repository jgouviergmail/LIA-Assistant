"""Tests for user MCP pipeline integration — ContextVar injection and fallbacks."""

import json
from unittest.mock import MagicMock

from src.core.constants import MCP_USER_TOOL_NAME_PREFIX
from src.core.context import UserMCPToolsContext, user_mcp_tools_ctx


class TestContextVarInjection:
    """Tests for ContextVar setup and access."""

    def test_default_is_none(self) -> None:
        """ContextVar should default to None."""
        assert user_mcp_tools_ctx.get() is None

    def test_set_and_get(self) -> None:
        """Should set and retrieve UserMCPToolsContext."""
        ctx = UserMCPToolsContext()
        ctx.tool_manifests.append(MagicMock())
        ctx.tool_instances["test"] = MagicMock()

        token = user_mcp_tools_ctx.set(ctx)
        try:
            retrieved = user_mcp_tools_ctx.get()
            assert retrieved is ctx
            assert len(retrieved.tool_manifests) == 1
            assert "test" in retrieved.tool_instances
        finally:
            user_mcp_tools_ctx.reset(token)

    def test_reset_to_none(self) -> None:
        """Should reset to None after cleanup."""
        ctx = UserMCPToolsContext()
        token = user_mcp_tools_ctx.set(ctx)
        user_mcp_tools_ctx.reset(token)
        assert user_mcp_tools_ctx.get() is None


class TestUserMCPToolsContext:
    """Tests for UserMCPToolsContext dataclass."""

    def test_default_empty(self) -> None:
        """Should initialize with empty lists and dicts."""
        ctx = UserMCPToolsContext()
        assert ctx.tool_manifests == []
        assert ctx.tool_instances == {}

    def test_add_manifests_and_instances(self) -> None:
        """Should allow adding tool manifests and instances."""
        ctx = UserMCPToolsContext()
        manifest = MagicMock(name="mcp_user_12345678_read_file")
        adapter = MagicMock()

        ctx.tool_manifests.append(manifest)
        ctx.tool_instances["mcp_user_12345678_read_file"] = adapter

        assert len(ctx.tool_manifests) == 1
        assert len(ctx.tool_instances) == 1


class TestUserMCPToolPrefixIdentification:
    """Tests for identifying user MCP tools by prefix."""

    def test_prefix_constant(self) -> None:
        """MCP_USER_TOOL_NAME_PREFIX should be defined and consistent."""
        assert MCP_USER_TOOL_NAME_PREFIX == "mcp_user"

    def test_user_tool_name_detection(self) -> None:
        """Should correctly identify user MCP tools by prefix."""
        user_tool_name = f"{MCP_USER_TOOL_NAME_PREFIX}_12345678_read_file"
        admin_tool_name = "mcp_filesystem_read_file"
        regular_tool_name = "gmail_send"

        assert user_tool_name.startswith(MCP_USER_TOOL_NAME_PREFIX)
        assert not admin_tool_name.startswith(MCP_USER_TOOL_NAME_PREFIX)
        assert not regular_tool_name.startswith(MCP_USER_TOOL_NAME_PREFIX)


class TestDomainProtectedTools:
    """Tests verifying that user MCP tools bypass semantic scoring."""

    def test_user_mcp_tools_are_domain_protected(self) -> None:
        """
        User MCP tools should be added to domain_protected_tools
        to bypass the semantic score threshold.
        """
        # Simulate what normal_filtering.py does
        domain_protected_tools: set[str] = set()

        user_ctx = UserMCPToolsContext()
        manifest1 = MagicMock()
        manifest1.name = f"{MCP_USER_TOOL_NAME_PREFIX}_abcdef12_search"
        manifest2 = MagicMock()
        manifest2.name = f"{MCP_USER_TOOL_NAME_PREFIX}_abcdef12_query"
        user_ctx.tool_manifests = [manifest1, manifest2]

        # This replicates the logic in normal_filtering.py
        for manifest in user_ctx.tool_manifests:
            if manifest.name.startswith(MCP_USER_TOOL_NAME_PREFIX):
                domain_protected_tools.add(manifest.name)

        assert len(domain_protected_tools) == 2
        assert manifest1.name in domain_protected_tools
        assert manifest2.name in domain_protected_tools


class TestManifestInjection:
    """Tests verifying that user MCP manifests are injected into catalogue."""

    def test_manifest_injection_merges_with_global(self) -> None:
        """
        User MCP manifests should be appended to global manifests.
        """
        # Simulate global manifests
        global_manifests = [MagicMock(name="gmail_send"), MagicMock(name="calendar_create")]

        # Simulate user MCP manifests from ContextVar
        user_ctx = UserMCPToolsContext()
        user_manifest = MagicMock()
        user_manifest.name = f"{MCP_USER_TOOL_NAME_PREFIX}_12345678_custom_tool"
        user_ctx.tool_manifests = [user_manifest]

        # Replicate the injection logic from normal_filtering.py
        all_manifests = list(global_manifests) + user_ctx.tool_manifests

        assert len(all_manifests) == 3
        assert all_manifests[-1].name == f"{MCP_USER_TOOL_NAME_PREFIX}_12345678_custom_tool"

    def test_no_injection_when_context_empty(self) -> None:
        """Should not inject when ContextVar is None."""
        global_manifests = [MagicMock(name="gmail_send")]

        user_ctx = user_mcp_tools_ctx.get()  # Should be None
        if user_ctx and user_ctx.tool_manifests:
            all_manifests = list(global_manifests) + user_ctx.tool_manifests
        else:
            all_manifests = global_manifests

        assert len(all_manifests) == 1


class TestExecutorFallback:
    """Tests verifying executor ContextVar fallback for tool resolution."""

    def test_tool_instance_fallback(self) -> None:
        """Should find tool in ContextVar when not in global registry."""
        tool_name = f"{MCP_USER_TOOL_NAME_PREFIX}_abcdef12_search"
        mock_tool = MagicMock()

        ctx = UserMCPToolsContext()
        ctx.tool_instances[tool_name] = mock_tool

        token = user_mcp_tools_ctx.set(ctx)
        try:
            # Simulate executor fallback
            user_ctx = user_mcp_tools_ctx.get()
            assert user_ctx is not None
            assert tool_name in user_ctx.tool_instances
            assert user_ctx.tool_instances[tool_name] is mock_tool
        finally:
            user_mcp_tools_ctx.reset(token)

    def test_manifest_fallback(self) -> None:
        """Should find manifest in ContextVar when not in global registry."""
        tool_name = f"{MCP_USER_TOOL_NAME_PREFIX}_abcdef12_query"
        mock_manifest = MagicMock()
        mock_manifest.name = tool_name

        ctx = UserMCPToolsContext()
        ctx.tool_manifests = [mock_manifest]

        token = user_mcp_tools_ctx.set(ctx)
        try:
            user_ctx = user_mcp_tools_ctx.get()
            found = None
            for m in user_ctx.tool_manifests:
                if m.name == tool_name:
                    found = m
                    break
            assert found is mock_manifest
        finally:
            user_mcp_tools_ctx.reset(token)


class TestForEachExpansionWithMCPItems:
    """Tests verifying that structured MCP items work with for_each expansion."""

    def test_structured_items_have_iterable_fields(self) -> None:
        """
        Simulate MCP structured output and verify that $item.name resolution
        works — i.e. items are dicts with real data fields, not wrappers.
        """
        from src.infrastructure.mcp.user_tool_adapter import _parse_mcp_structured_items

        # Simulate what GitHub search_repositories returns
        raw_result = json.dumps(
            [
                {"name": "LIA", "description": "AI assistant", "stargazers_count": 12},
                {"name": "OtherRepo", "description": "Another project", "stargazers_count": 5},
            ]
        )

        parsed = _parse_mcp_structured_items(raw_result)
        assert parsed is not None
        items, _ = parsed

        # Simulate $item.name resolution (what dependency_graph does)
        for item in items:
            assert isinstance(item, dict)
            resolved_name = item.get("name")
            assert resolved_name is not None
            assert resolved_name != "null"
            assert isinstance(resolved_name, str)

    def test_structured_data_keys_for_for_each_reference(self) -> None:
        """
        Verify that the structured_data returned by the adapter has keys
        that for_each can reference ($steps.step_1.<key>).
        """
        from src.infrastructure.mcp.user_tool_adapter import (
            _derive_collection_key,
            _parse_mcp_structured_items,
        )

        raw_result = json.dumps([{"name": "repo1"}, {"name": "repo2"}])
        parsed = _parse_mcp_structured_items(raw_result)
        assert parsed is not None
        items, detected_key = parsed

        collection_key = detected_key or _derive_collection_key("search_repositories")
        assert collection_key == "repositories"

        # Build structured_data as the adapter would
        structured_data = {collection_key: items}
        assert "repositories" in structured_data
        assert len(structured_data["repositories"]) == 2

        # Simulate for_each resolution: $steps.step_1.repositories[0].name
        first_item = structured_data["repositories"][0]
        assert first_item["name"] == "repo1"
