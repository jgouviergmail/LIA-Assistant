"""
Tests for Subgraph Tracing - Phase 3.1.5.

Test coverage:
- create_instrumented_config with subgraph parameters
- create_subgraph_config helper
- Metadata enrichment (parent_trace_id, subgraph_name, depth)
- Context propagation from parent to child
- Depth incrementing

Phase: 3.1.5 - Nested Trace Hierarchy
Date: 2025-11-23
"""

import pytest
from langchain_core.runnables import RunnableConfig

from src.infrastructure.llm.instrumentation import (
    create_instrumented_config,
    create_subgraph_config,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def parent_config() -> RunnableConfig:
    """Parent config with session, user, trace context."""
    return create_instrumented_config(
        llm_type="orchestrator",
        session_id="session_123",
        user_id="user_456",
        trace_id="trace_root_abc",
        depth=0,
    )


# ============================================================================
# TESTS: create_instrumented_config - Subgraph Parameters
# ============================================================================


class TestCreateInstrumentedConfigSubgraph:
    """Tests for create_instrumented_config with subgraph parameters."""

    def test_subgraph_metadata_enrichment(self):
        """Test that subgraph parameters are added to metadata."""
        config = create_instrumented_config(
            llm_type="contacts_agent",
            session_id="session_123",
            parent_trace_id="trace_parent_xyz",
            subgraph_name="contacts_search",
            depth=1,
        )

        metadata = config.get("metadata", {})

        # Check subgraph metadata
        assert metadata["langfuse_parent_trace_id"] == "trace_parent_xyz"
        assert metadata["langfuse_subgraph_name"] == "contacts_search"
        assert metadata["langfuse_trace_depth"] == 1

        # Check standard metadata still present
        assert metadata["llm_type"] == "contacts_agent"
        assert metadata["langfuse_session_id"] == "session_123"

    def test_depth_defaults_to_zero(self):
        """Test that depth defaults to 0 if not provided."""
        config = create_instrumented_config(
            llm_type="router",
            session_id="session_123",
        )

        metadata = config.get("metadata", {})
        assert metadata["langfuse_trace_depth"] == 0

    def test_depth_can_be_set_explicitly(self):
        """Test explicit depth values."""
        for depth_value in [0, 1, 2, 5, 10]:
            config = create_instrumented_config(
                llm_type="test_agent",
                session_id="session_123",
                depth=depth_value,
            )

            metadata = config.get("metadata", {})
            assert metadata["langfuse_trace_depth"] == depth_value

    def test_parent_trace_id_optional(self):
        """Test that parent_trace_id is optional."""
        # Without parent_trace_id
        config = create_instrumented_config(
            llm_type="router",
            session_id="session_123",
            subgraph_name="router_subgraph",
            depth=0,
        )

        metadata = config.get("metadata", {})
        assert "langfuse_parent_trace_id" not in metadata
        assert metadata["langfuse_subgraph_name"] == "router_subgraph"
        assert metadata["langfuse_trace_depth"] == 0

    def test_subgraph_name_optional(self):
        """Test that subgraph_name is optional."""
        # Without subgraph_name
        config = create_instrumented_config(
            llm_type="planner",
            session_id="session_123",
            parent_trace_id="trace_parent_123",
            depth=1,
        )

        metadata = config.get("metadata", {})
        assert metadata["langfuse_parent_trace_id"] == "trace_parent_123"
        assert "langfuse_subgraph_name" not in metadata
        assert metadata["langfuse_trace_depth"] == 1

    def test_all_subgraph_parameters_together(self):
        """Test all subgraph parameters used together."""
        config = create_instrumented_config(
            llm_type="emails_agent",
            session_id="session_123",
            user_id="user_456",
            trace_id="trace_child_def",
            parent_trace_id="trace_parent_abc",
            subgraph_name="emails_fetch",
            depth=2,
            metadata={"query": "fetch recent emails"},
        )

        metadata = config.get("metadata", {})

        # Subgraph metadata
        assert metadata["langfuse_parent_trace_id"] == "trace_parent_abc"
        assert metadata["langfuse_subgraph_name"] == "emails_fetch"
        assert metadata["langfuse_trace_depth"] == 2

        # Standard metadata
        assert metadata["llm_type"] == "emails_agent"
        assert metadata["langfuse_session_id"] == "session_123"
        assert metadata["langfuse_user_id"] == "user_456"
        assert metadata["langfuse_trace_id"] == "trace_child_def"

        # Custom metadata
        assert metadata["query"] == "fetch recent emails"


# ============================================================================
# TESTS: create_subgraph_config - Context Propagation
# ============================================================================


class TestCreateSubgraphConfig:
    """Tests for create_subgraph_config helper."""

    def test_propagates_session_id_from_parent(self, parent_config):
        """Test that session_id is propagated from parent config."""
        subgraph_config = create_subgraph_config(
            llm_type="contacts_agent",
            parent_config=parent_config,
            subgraph_name="contacts_search",
        )

        metadata = subgraph_config.get("metadata", {})
        parent_metadata = parent_config.get("metadata", {})

        assert metadata["langfuse_session_id"] == parent_metadata["langfuse_session_id"]
        assert metadata["langfuse_session_id"] == "session_123"

    def test_propagates_user_id_from_parent(self, parent_config):
        """Test that user_id is propagated from parent config."""
        subgraph_config = create_subgraph_config(
            llm_type="emails_agent",
            parent_config=parent_config,
            subgraph_name="emails_fetch",
        )

        metadata = subgraph_config.get("metadata", {})
        parent_metadata = parent_config.get("metadata", {})

        assert metadata["langfuse_user_id"] == parent_metadata["langfuse_user_id"]
        assert metadata["langfuse_user_id"] == "user_456"

    def test_sets_parent_trace_id_from_parent_trace_id(self, parent_config):
        """Test that parent_trace_id is set from parent's trace_id."""
        subgraph_config = create_subgraph_config(
            llm_type="contacts_agent",
            parent_config=parent_config,
            subgraph_name="contacts_search",
        )

        metadata = subgraph_config.get("metadata", {})
        parent_metadata = parent_config.get("metadata", {})

        assert metadata["langfuse_parent_trace_id"] == parent_metadata.get("langfuse_trace_id")
        assert metadata["langfuse_parent_trace_id"] == "trace_root_abc"

    def test_increments_depth(self, parent_config):
        """Test that depth is incremented by 1."""
        # Parent depth = 0
        subgraph_config = create_subgraph_config(
            llm_type="contacts_agent",
            parent_config=parent_config,
            subgraph_name="contacts_search",
        )

        metadata = subgraph_config.get("metadata", {})
        parent_metadata = parent_config.get("metadata", {})

        parent_depth = parent_metadata.get("langfuse_trace_depth", 0)
        assert metadata["langfuse_trace_depth"] == parent_depth + 1
        assert metadata["langfuse_trace_depth"] == 1

    def test_increments_depth_for_nested_subgraphs(self):
        """Test depth increments correctly for multi-level nesting."""
        # Level 0: Root
        root_config = create_instrumented_config(
            llm_type="orchestrator",
            session_id="session_123",
            depth=0,
        )
        assert root_config["metadata"]["langfuse_trace_depth"] == 0

        # Level 1: First subgraph
        level1_config = create_subgraph_config(
            llm_type="contacts_agent",
            parent_config=root_config,
            subgraph_name="contacts_search",
        )
        assert level1_config["metadata"]["langfuse_trace_depth"] == 1

        # Level 2: Nested subgraph
        level2_config = create_subgraph_config(
            llm_type="gmail_client",
            parent_config=level1_config,
            subgraph_name="gmail_api_call",
        )
        assert level2_config["metadata"]["langfuse_trace_depth"] == 2

    def test_adds_subgraph_name_to_metadata(self, parent_config):
        """Test that subgraph_name is added to metadata."""
        subgraph_config = create_subgraph_config(
            llm_type="emails_agent",
            parent_config=parent_config,
            subgraph_name="emails_fetch",
        )

        metadata = subgraph_config.get("metadata", {})
        assert metadata["langfuse_subgraph_name"] == "emails_fetch"

    def test_adds_subgraph_tag(self, parent_config):
        """Test that subgraph tag is added to tags."""
        subgraph_config = create_subgraph_config(
            llm_type="contacts_agent",
            parent_config=parent_config,
            subgraph_name="contacts_search",
        )

        metadata = subgraph_config.get("metadata", {})
        tags = metadata.get("langfuse_tags", [])

        assert "subgraph:contacts_search" in tags

    def test_preserves_parent_tags(self):
        """Test that parent tags are preserved and merged."""
        # Parent with custom tags
        parent_config = create_instrumented_config(
            llm_type="orchestrator",
            session_id="session_123",
            tags=["production", "batch_job"],
            depth=0,
        )

        subgraph_config = create_subgraph_config(
            llm_type="contacts_agent",
            parent_config=parent_config,
            subgraph_name="contacts_search",
        )

        metadata = subgraph_config.get("metadata", {})
        tags = metadata.get("langfuse_tags", [])

        # Parent tags should be preserved
        assert "orchestrator" in tags  # Parent llm_type
        assert "production" in tags
        assert "batch_job" in tags

        # Subgraph tags should be added
        assert "contacts_agent" in tags  # Subgraph llm_type
        assert "subgraph:contacts_search" in tags

    def test_merges_custom_metadata(self, parent_config):
        """Test that custom metadata is merged correctly."""
        subgraph_config = create_subgraph_config(
            llm_type="emails_agent",
            parent_config=parent_config,
            subgraph_name="emails_fetch",
            metadata={"query": "fetch recent emails", "limit": 10},
        )

        metadata = subgraph_config.get("metadata", {})

        # Custom metadata should be present
        assert metadata["query"] == "fetch recent emails"
        assert metadata["limit"] == 10

        # Standard metadata should still be there
        assert metadata["llm_type"] == "emails_agent"
        assert metadata["langfuse_subgraph_name"] == "emails_fetch"

    def test_preserves_base_config_properties(self):
        """Test that base config properties are preserved."""
        # Parent config with recursion_limit
        parent_config_with_limit = create_instrumented_config(
            llm_type="orchestrator",
            session_id="session_123",
            base_config={"recursion_limit": 50, "max_concurrency": 10},
        )

        subgraph_config = create_subgraph_config(
            llm_type="contacts_agent",
            parent_config=parent_config_with_limit,
            subgraph_name="contacts_search",
        )

        # Base config properties should be preserved
        assert subgraph_config.get("recursion_limit") == 50
        assert subgraph_config.get("max_concurrency") == 10

    def test_trace_name_format(self, parent_config):
        """Test that trace_name follows subgraph naming convention."""
        subgraph_config = create_subgraph_config(
            llm_type="contacts_agent",
            parent_config=parent_config,
            subgraph_name="contacts_search",
        )

        metadata = subgraph_config.get("metadata", {})
        trace_name = metadata.get("langfuse_trace_name")

        assert trace_name == "contacts_search_subgraph"

    def test_handles_missing_parent_metadata_gracefully(self):
        """Test graceful handling of parent config with no metadata."""
        # Parent config with minimal metadata
        minimal_parent_config: RunnableConfig = {"recursion_limit": 50}

        subgraph_config = create_subgraph_config(
            llm_type="contacts_agent",
            parent_config=minimal_parent_config,
            subgraph_name="contacts_search",
        )

        metadata = subgraph_config.get("metadata", {})

        # Should still create valid subgraph config
        assert metadata["llm_type"] == "contacts_agent"
        assert metadata["langfuse_subgraph_name"] == "contacts_search"
        assert metadata["langfuse_trace_depth"] == 1  # 0 + 1 (default parent depth)

        # Parent context should be None/missing
        assert metadata.get("langfuse_session_id") is None
        assert metadata.get("langfuse_user_id") is None
        assert metadata.get("langfuse_parent_trace_id") is None


# ============================================================================
# TESTS: Integration - Full Hierarchy
# ============================================================================


class TestSubgraphHierarchyIntegration:
    """Integration tests for complete trace hierarchy."""

    def test_three_level_hierarchy(self):
        """Test complete 3-level trace hierarchy."""
        # Level 0: Root orchestrator
        root_config = create_instrumented_config(
            llm_type="orchestrator",
            session_id="session_xyz",
            user_id="user_789",
            trace_id="trace_root",
            depth=0,
        )

        # Validate root
        root_meta = root_config["metadata"]
        assert root_meta["langfuse_trace_depth"] == 0
        assert root_meta["langfuse_trace_id"] == "trace_root"
        assert "langfuse_parent_trace_id" not in root_meta

        # Level 1: Contacts subgraph
        contacts_config = create_subgraph_config(
            llm_type="contacts_agent",
            parent_config=root_config,
            subgraph_name="contacts_search",
        )

        # Validate level 1
        contacts_meta = contacts_config["metadata"]
        assert contacts_meta["langfuse_trace_depth"] == 1
        assert contacts_meta["langfuse_parent_trace_id"] == "trace_root"
        assert contacts_meta["langfuse_subgraph_name"] == "contacts_search"
        assert contacts_meta["langfuse_session_id"] == "session_xyz"
        assert contacts_meta["langfuse_user_id"] == "user_789"

        # Level 2: Gmail API call nested in contacts
        gmail_config = create_subgraph_config(
            llm_type="gmail_client",
            parent_config=contacts_config,
            subgraph_name="gmail_api_call",
        )

        # Validate level 2
        gmail_meta = gmail_config["metadata"]
        assert gmail_meta["langfuse_trace_depth"] == 2
        # Parent is contacts config (not root!)
        assert gmail_meta["langfuse_parent_trace_id"] == contacts_meta.get("langfuse_trace_id")
        assert gmail_meta["langfuse_subgraph_name"] == "gmail_api_call"
        assert gmail_meta["langfuse_session_id"] == "session_xyz"
        assert gmail_meta["langfuse_user_id"] == "user_789"
