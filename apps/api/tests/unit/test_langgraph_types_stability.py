"""
LangGraph types stability tests.

Permanent tests to detect breaking changes in LangGraph's public API
during future version upgrades. Covers Command, interrupt, error hierarchy,
add_messages behavior, and StateGraph.compile() signature.
"""

import inspect

import pytest

# ============================================================================
# Command pattern (used in resumption_strategies.py)
# ============================================================================


@pytest.mark.unit
class TestCommandPattern:
    """Verify Command constructor patterns used in resumption_strategies.py."""

    def test_command_resume_only(self):
        from langgraph.types import Command

        cmd = Command(resume={"decision": "APPROVE"})
        assert cmd.resume == {"decision": "APPROVE"}

    def test_command_resume_with_update(self):
        from langchain_core.messages import HumanMessage
        from langgraph.types import Command

        cmd = Command(
            resume={"decision": "EDIT"},
            update={"messages": [HumanMessage(content="reformulated")]},
        )
        assert cmd.resume == {"decision": "EDIT"}
        assert "messages" in cmd.update


# ============================================================================
# Interrupt pattern
# ============================================================================


@pytest.mark.unit
class TestInterruptPattern:

    def test_interrupt_is_callable(self):
        from langgraph.types import interrupt

        assert callable(interrupt)


# ============================================================================
# Graph error hierarchy
# ============================================================================


@pytest.mark.unit
class TestGraphErrorHierarchy:

    def test_graph_interrupt_is_base_exception(self):
        from langgraph.errors import GraphInterrupt

        assert issubclass(GraphInterrupt, BaseException)

    def test_graph_recursion_error_is_exception(self):
        from langgraph.errors import GraphRecursionError

        assert issubclass(GraphRecursionError, Exception)


# ============================================================================
# add_messages behavior (used in models.py add_messages_with_truncate())
# ============================================================================


@pytest.mark.unit
class TestAddMessagesBehavior:
    """Verify add_messages behaviors used in models.py add_messages_with_truncate()."""

    def test_append_messages(self):
        from langchain_core.messages import HumanMessage
        from langgraph.graph.message import add_messages

        result = add_messages(
            [HumanMessage(content="a", id="1")],
            [HumanMessage(content="b", id="2")],
        )
        assert len(result) == 2

    def test_replace_by_id(self):
        from langchain_core.messages import HumanMessage
        from langgraph.graph.message import add_messages

        result = add_messages(
            [HumanMessage(content="old", id="1")],
            [HumanMessage(content="new", id="1")],
        )
        assert len(result) == 1
        assert result[0].content == "new"

    def test_remove_message_by_id(self):
        from langchain_core.messages import HumanMessage, RemoveMessage
        from langgraph.graph.message import add_messages

        result = add_messages(
            [HumanMessage(content="a", id="1"), HumanMessage(content="b", id="2")],
            [RemoveMessage(id="1")],
        )
        assert len(result) == 1
        assert result[0].id == "2"

    def test_preserves_message_order(self):
        from langchain_core.messages import AIMessage, HumanMessage
        from langgraph.graph.message import add_messages

        result = add_messages(
            [HumanMessage(content="q1", id="1")],
            [AIMessage(content="a1", id="2"), HumanMessage(content="q2", id="3")],
        )
        assert len(result) == 3
        assert result[0].content == "q1"
        assert result[1].content == "a1"
        assert result[2].content == "q2"


# ============================================================================
# StateGraph.compile() signature
# ============================================================================


@pytest.mark.unit
class TestStateGraphCompile:

    def test_compile_accepts_checkpointer_and_store(self):
        """Verify compile() keyword args used in graph.py L717-720."""
        from langgraph.graph import StateGraph

        sig = inspect.signature(StateGraph.compile)  # type: ignore[arg-type]
        params = sig.parameters
        assert "checkpointer" in params
        assert "store" in params
