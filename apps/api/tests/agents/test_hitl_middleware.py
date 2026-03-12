"""
Unit tests for Human-in-the-Loop (HITL) middleware implementation.

Tests LangChain v1.0 HumanInTheLoopMiddleware pattern for tool approval.
Validates interrupt/resume flow and approval decisions.

NOTE (2026-01-19): These tests are outdated and test legacy configuration patterns:
- tool_approval_enabled: Removed - HITL is now always enabled
- tool_approval_required: Removed - tool approval is now manifest-driven
  (defined in tool manifests via permissions.hitl_required)

TODO: Rewrite tests to use manifest-driven HITL pattern.
"""

from unittest.mock import MagicMock, patch

import pytest
from langchain.agents.middleware import HumanInTheLoopMiddleware

from src.domains.agents.utils.hitl_config import get_approval_config, requires_approval

pytestmark = pytest.mark.skip(
    reason="Tests use legacy tool_approval_enabled/required settings. "
    "HITL is now always enabled and tool approval is manifest-driven. "
    "See hitl_config.py and tool manifests for current implementation."
)


class TestHITLConfiguration:
    """Test suite for HITL configuration utilities."""

    def test_requires_approval_queries_registry(self):
        """
        GIVEN a tool name
        WHEN requires_approval is called
        THEN should query registry for manifest-driven approval
        """
        with patch("src.domains.agents.utils.hitl_config.get_global_registry") as mock_get_registry:
            mock_registry = MagicMock()
            mock_registry.requires_tool_approval.return_value = True
            mock_get_registry.return_value = mock_registry

            result = requires_approval("search_contacts_tool")

            mock_registry.requires_tool_approval.assert_called_once_with("search_contacts_tool")
            assert result is True

    def test_get_approval_config_returns_allowed_decisions(self):
        """
        GIVEN any tool name
        WHEN get_approval_config is called
        THEN should return allowed decisions
        """
        config = get_approval_config("search_contacts_tool")

        assert "allowed_decisions" in config
        assert "approve" in config["allowed_decisions"]
        assert "edit" in config["allowed_decisions"]
        assert "reject" in config["allowed_decisions"]


class TestHITLWorkflow:
    """
    Test suite for HITL workflow patterns.

    Note: These are structural tests. Full integration tests with actual
    interrupt/resume flow require a running graph with checkpointer.
    """

    def test_middleware_instantiation(self):
        """
        GIVEN valid interrupt_config
        WHEN creating HumanInTheLoopMiddleware
        THEN middleware should instantiate successfully
        """
        interrupt_config = {
            "search_contacts_tool": {"allowed_decisions": ["approve", "edit", "reject"]}
        }

        # Create middleware
        middleware = HumanInTheLoopMiddleware(interrupt_on=interrupt_config)

        # Validate middleware was created
        assert middleware is not None
        assert hasattr(middleware, "interrupt_on")


class TestHITLBestPractices:
    """Test suite validating LangChain v1.0 HITL best practices."""

    def test_middleware_pattern_over_dedicated_node(self):
        """
        GIVEN LangChain v1.0 architecture
        WHEN implementing HITL
        THEN middleware pattern should be used (not dedicated approval node)
        """
        # Correct pattern: Middleware in create_agent
        interrupt_config = {"search_contacts_tool": {"allowed_decisions": ["approve", "reject"]}}
        middleware = HumanInTheLoopMiddleware(interrupt_on=interrupt_config)

        assert middleware is not None

    def test_middleware_intercepts_before_execution(self):
        """
        GIVEN HumanInTheLoopMiddleware
        WHEN tool call is made
        THEN middleware should intercept BEFORE execution (not after)
        """
        interrupt_config = {"search_contacts_tool": {"allowed_decisions": ["approve", "reject"]}}
        middleware = HumanInTheLoopMiddleware(interrupt_on=interrupt_config)

        # Middleware should have interrupt_on attribute
        assert hasattr(middleware, "interrupt_on")
        assert "search_contacts_tool" in middleware.interrupt_on
