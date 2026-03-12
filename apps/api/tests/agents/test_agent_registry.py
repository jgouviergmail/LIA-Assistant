"""
Tests for Agent Registry.

Tests the centralized agent management system with:
- Registration and retrieval
- Lazy initialization
- Dependency injection (checkpointer, store)
- Thread safety
- Error handling

Compliance: LangGraph v1.0 + LangChain v1.0 best practices
"""

from unittest.mock import Mock

import pytest

from src.domains.agents.registry import (
    AgentAlreadyRegisteredError,
    AgentNotFoundError,
    AgentRegistry,
    AgentRegistryError,
    get_global_registry,
    reset_global_registry,
    set_global_registry,
)


class TestAgentRegistryBasics:
    """Test basic registry operations."""

    def test_registry_initialization(self):
        """Test registry can be initialized."""
        registry = AgentRegistry()
        assert registry is not None
        assert registry.get_checkpointer() is None
        assert registry.get_store() is None

    def test_registry_with_dependencies(self):
        """Test registry initialization with checkpointer and store."""
        mock_checkpointer = Mock()
        mock_store = Mock()

        registry = AgentRegistry(checkpointer=mock_checkpointer, store=mock_store)

        assert registry.get_checkpointer() == mock_checkpointer
        assert registry.get_store() == mock_store

    def test_list_agents_empty(self):
        """Test listing agents when none registered."""
        registry = AgentRegistry()
        assert registry.list_agents() == []

    def test_is_registered_false(self):
        """Test is_registered returns False for unregistered agent."""
        registry = AgentRegistry()
        assert registry.is_registered("nonexistent") is False

    def test_is_built_false(self):
        """Test is_built returns False for agent not yet built."""
        registry = AgentRegistry()

        def mock_builder():
            return Mock()

        registry.register_agent("test_agent", mock_builder)
        assert registry.is_built("test_agent") is False


class TestAgentRegistration:
    """Test agent registration."""

    def test_register_agent_success(self):
        """Test successful agent registration."""
        registry = AgentRegistry()

        def mock_builder():
            return Mock(name="TestAgent")

        registry.register_agent("test_agent", mock_builder)

        assert registry.is_registered("test_agent")
        assert "test_agent" in registry.list_agents()

    def test_register_multiple_agents(self):
        """Test registering multiple agents."""
        registry = AgentRegistry()

        def builder1():
            return Mock(name="Agent1")

        def builder2():
            return Mock(name="Agent2")

        registry.register_agent("agent1", builder1)
        registry.register_agent("agent2", builder2)

        assert registry.list_agents() == ["agent1", "agent2"]

    def test_register_agent_invalid_name(self):
        """Test registration fails with invalid name."""
        registry = AgentRegistry()

        with pytest.raises(ValueError, match="Invalid agent name"):
            registry.register_agent("", lambda: Mock())

        with pytest.raises(ValueError, match="Invalid agent name"):
            registry.register_agent(None, lambda: Mock())

    def test_register_agent_invalid_builder(self):
        """Test registration fails with non-callable builder."""
        registry = AgentRegistry()

        with pytest.raises(ValueError, match="must be callable"):
            registry.register_agent("test_agent", "not_a_function")

    def test_register_agent_duplicate_fails(self):
        """Test registering duplicate agent fails without override."""
        registry = AgentRegistry()

        def mock_builder():
            return Mock()

        registry.register_agent("test_agent", mock_builder)

        with pytest.raises(AgentAlreadyRegisteredError, match="already registered"):
            registry.register_agent("test_agent", mock_builder)

    def test_register_agent_override(self):
        """Test overriding existing agent registration."""
        registry = AgentRegistry()

        marker1 = {"value": "agent1"}
        marker2 = {"value": "agent2"}

        def builder1():
            mock = Mock(name="Agent1")
            mock.marker = marker1
            return mock

        def builder2():
            mock = Mock(name="Agent2")
            mock.marker = marker2
            return mock

        registry.register_agent("test_agent", builder1)
        registry.register_agent("test_agent", builder2, override=True)

        agent = registry.get_agent("test_agent")
        assert agent.marker == marker2  # Should be from builder2


class TestAgentRetrieval:
    """Test agent retrieval and lazy initialization."""

    def test_get_agent_success(self):
        """Test successful agent retrieval."""
        registry = AgentRegistry()

        mock_agent = Mock(name="TestAgent")

        def mock_builder():
            return mock_agent

        registry.register_agent("test_agent", mock_builder)

        agent = registry.get_agent("test_agent")

        assert agent == mock_agent
        assert registry.is_built("test_agent")

    def test_get_agent_not_found(self):
        """Test retrieval fails for unregistered agent."""
        registry = AgentRegistry()

        with pytest.raises(AgentNotFoundError, match="not found in registry"):
            registry.get_agent("nonexistent")

    def test_get_agent_lazy_initialization(self):
        """Test agent is built only on first access."""
        registry = AgentRegistry()

        build_count = {"count": 0}

        def counting_builder():
            build_count["count"] += 1
            return Mock(name=f"Agent{build_count['count']}")

        registry.register_agent("test_agent", counting_builder)

        # Not built yet
        assert registry.is_built("test_agent") is False
        assert build_count["count"] == 0

        # First access - triggers build
        agent1 = registry.get_agent("test_agent")
        assert build_count["count"] == 1
        assert registry.is_built("test_agent") is True

        # Second access - uses cache
        agent2 = registry.get_agent("test_agent")
        assert build_count["count"] == 1  # Still 1, not rebuilt
        assert agent1 == agent2  # Same instance

    def test_get_agent_build_failure(self):
        """Test proper error handling when agent build fails."""
        registry = AgentRegistry()

        def failing_builder():
            raise RuntimeError("Build failed!")

        registry.register_agent("test_agent", failing_builder)

        with pytest.raises(AgentRegistryError, match="Failed to build agent"):
            registry.get_agent("test_agent")

        # Agent should not be cached after failure
        assert registry.is_built("test_agent") is False


class TestAgentRebuild:
    """Test agent rebuild functionality."""

    def test_rebuild_agent(self):
        """Test rebuilding an agent clears cache."""
        registry = AgentRegistry()

        build_count = {"count": 0}

        def counting_builder():
            build_count["count"] += 1
            return Mock(name=f"Agent{build_count['count']}")

        registry.register_agent("test_agent", counting_builder)

        # First build
        agent1 = registry.get_agent("test_agent")
        assert build_count["count"] == 1

        # Rebuild
        agent2 = registry.rebuild_agent("test_agent")
        assert build_count["count"] == 2  # Built again
        assert agent1 != agent2  # Different instance

    def test_rebuild_unregistered_agent(self):
        """Test rebuilding unregistered agent fails."""
        registry = AgentRegistry()

        with pytest.raises(AgentNotFoundError):
            registry.rebuild_agent("nonexistent")


class TestCacheManagement:
    """Test cache management operations."""

    def test_clear_cache(self):
        """Test clearing entire cache."""
        registry = AgentRegistry()

        def mock_builder():
            return Mock()

        registry.register_agent("agent1", mock_builder)
        registry.register_agent("agent2", mock_builder)

        # Build both
        registry.get_agent("agent1")
        registry.get_agent("agent2")

        assert registry.is_built("agent1")
        assert registry.is_built("agent2")

        # Clear cache
        registry.clear_cache()

        assert not registry.is_built("agent1")
        assert not registry.is_built("agent2")

        # But still registered
        assert registry.is_registered("agent1")
        assert registry.is_registered("agent2")

    def test_clear_cache_empty(self):
        """Test clearing empty cache."""
        registry = AgentRegistry()
        registry.clear_cache()  # Should not raise


class TestRegistryStats:
    """Test registry statistics."""

    def test_get_stats_empty(self):
        """Test stats for empty registry."""
        registry = AgentRegistry()

        stats = registry.get_stats()

        assert stats["registered"] == 0
        assert stats["built"] == 0
        assert stats["has_checkpointer"] is False
        assert stats["has_store"] is False
        assert stats["agents"]["registered"] == []
        assert stats["agents"]["built"] == []

    def test_get_stats_with_agents(self):
        """Test stats with registered and built agents."""
        mock_checkpointer = Mock()
        mock_store = Mock()

        registry = AgentRegistry(checkpointer=mock_checkpointer, store=mock_store)

        def mock_builder():
            return Mock()

        registry.register_agent("agent1", mock_builder)
        registry.register_agent("agent2", mock_builder)
        registry.get_agent("agent1")  # Build only agent1

        stats = registry.get_stats()

        assert stats["registered"] == 2
        assert stats["built"] == 1
        assert stats["has_checkpointer"] is True
        assert stats["has_store"] is True
        assert set(stats["agents"]["registered"]) == {"agent1", "agent2"}
        assert stats["agents"]["built"] == ["agent1"]


class TestGlobalRegistry:
    """Test global registry singleton."""

    def teardown_method(self):
        """Reset global registry after each test."""
        reset_global_registry()

    def test_get_global_registry(self):
        """Test getting global registry singleton."""
        registry1 = get_global_registry()
        registry2 = get_global_registry()

        assert registry1 is registry2  # Same instance

    def test_set_global_registry(self):
        """Test setting global registry."""
        custom_registry = AgentRegistry()

        def mock_builder():
            return Mock()

        custom_registry.register_agent("test_agent", mock_builder)

        set_global_registry(custom_registry)

        retrieved_registry = get_global_registry()

        assert retrieved_registry is custom_registry
        assert retrieved_registry.is_registered("test_agent")

    def test_reset_global_registry(self):
        """Test resetting global registry."""
        # Get initial registry
        registry1 = get_global_registry()

        # Reset
        reset_global_registry()

        # Get new registry
        registry2 = get_global_registry()

        # Should be different instance
        assert registry1 is not registry2


class TestThreadSafety:
    """Test thread safety of registry operations."""

    def test_concurrent_registration(self):
        """Test concurrent agent registration."""
        import threading

        registry = AgentRegistry()
        results = []

        def register_agent(name):
            try:

                def mock_builder():
                    return Mock()

                registry.register_agent(name, mock_builder)
                results.append(("success", name))
            except Exception as e:
                results.append(("error", name, str(e)))

        # Register 10 agents concurrently
        threads = [threading.Thread(target=register_agent, args=(f"agent{i}",)) for i in range(10)]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # All should succeed
        assert len([r for r in results if r[0] == "success"]) == 10
        assert len(registry.list_agents()) == 10

    def test_concurrent_retrieval(self):
        """Test concurrent agent retrieval (lazy init)."""
        import threading

        registry = AgentRegistry()

        build_count = {"count": 0, "lock": threading.Lock()}

        def counting_builder():
            with build_count["lock"]:
                build_count["count"] += 1
            return Mock(name="TestAgent")

        registry.register_agent("test_agent", counting_builder)

        results = []

        def get_agent():
            agent = registry.get_agent("test_agent")
            results.append(agent)

        # Get agent from 5 threads concurrently
        threads = [threading.Thread(target=get_agent) for _ in range(5)]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # All should get the same agent instance
        assert len(results) == 5
        assert all(agent == results[0] for agent in results)

        # Agent should be built only once
        assert build_count["count"] == 1


class TestIntegration:
    """Integration tests for realistic scenarios."""

    def test_multi_agent_system(self):
        """Test registry with multiple agents (realistic scenario)."""
        mock_checkpointer = Mock()
        mock_store = Mock()

        registry = AgentRegistry(checkpointer=mock_checkpointer, store=mock_store)

        # Register multiple agents
        def build_contacts_agent():
            return Mock(name="ContactsAgent")

        def build_emails_agent():
            return Mock(name="GmailAgent")

        def build_calendar_agent():
            return Mock(name="CalendarAgent")

        registry.register_agent("contacts_agent", build_contacts_agent)
        registry.register_agent("emails_agent", build_emails_agent)
        registry.register_agent("calendar_agent", build_calendar_agent)

        # Retrieve agents
        contacts = registry.get_agent("contacts_agent")
        gmail = registry.get_agent("emails_agent")
        calendar = registry.get_agent("calendar_agent")

        # Verify all distinct instances
        assert contacts is not gmail
        assert contacts is not calendar
        assert gmail is not calendar

        # Verify they are Mock objects with correct names
        assert isinstance(contacts, Mock)
        assert isinstance(gmail, Mock)
        assert isinstance(calendar, Mock)

        # Stats
        stats = registry.get_stats()
        assert stats["registered"] == 3
        assert stats["built"] == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
