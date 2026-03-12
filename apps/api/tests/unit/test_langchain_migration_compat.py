"""
LangChain/LangGraph migration compatibility tests.

Validates imports, signatures, and behaviors critical to our architecture.
These tests serve as a permanent safety net — they must pass BEFORE and AFTER
any version upgrade of the LangChain/LangGraph ecosystem.

Note: Section 1.6 (ContextOverflowError) requires langchain-core >= 1.2.10.
"""

import inspect

import pytest

# ============================================================================
# 1.1 — LangGraph Core Imports
# ============================================================================


@pytest.mark.unit
class TestLangGraphCoreImports:

    def test_state_graph_importable(self):
        from langgraph.graph import END, StateGraph

        assert callable(StateGraph)
        assert END is not None

    def test_compiled_state_graph_importable(self):
        from langgraph.graph.state import CompiledStateGraph

        assert CompiledStateGraph is not None

    def test_add_messages_importable_and_callable(self):
        from langgraph.graph.message import add_messages

        assert callable(add_messages)

    def test_state_graph_accepts_typed_dict(self):
        """StateGraph accepts a TypedDict as schema (our MessagesState pattern)."""
        from langgraph.graph import StateGraph
        from typing_extensions import TypedDict

        class MinimalState(TypedDict):
            value: str

        graph = StateGraph(MinimalState)
        assert graph is not None


# ============================================================================
# 1.2 — Signature AsyncPostgresSaver (risque principal)
# ============================================================================


@pytest.mark.unit
class TestCheckpointerSignatureCompat:

    def test_checkpoint_types_importable(self):
        from langgraph.checkpoint.base import (  # noqa: F401
            ChannelVersions,
            Checkpoint,
            CheckpointMetadata,
            CheckpointTuple,
        )

    def test_async_postgres_saver_importable(self):
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver  # noqa: F401

    def test_aput_signature_params(self):
        """Verify AsyncPostgresSaver.aput() accepts our exact parameter names."""
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        sig = inspect.signature(AsyncPostgresSaver.aput)
        params = list(sig.parameters.keys())
        assert "config" in params
        assert "checkpoint" in params
        assert "metadata" in params
        assert "new_versions" in params

    def test_instrumented_checkpointer_is_subclass(self):
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        from src.domains.conversations.instrumented_checkpointer import (
            InstrumentedAsyncPostgresSaver,
        )

        assert issubclass(InstrumentedAsyncPostgresSaver, AsyncPostgresSaver)

    def test_aput_child_matches_parent_signature(self):
        """Verify overridden aput() has same params as parent."""
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        from src.domains.conversations.instrumented_checkpointer import (
            InstrumentedAsyncPostgresSaver,
        )

        parent_params = set(inspect.signature(AsyncPostgresSaver.aput).parameters.keys())
        child_params = set(inspect.signature(InstrumentedAsyncPostgresSaver.aput).parameters.keys())
        assert parent_params == child_params


# ============================================================================
# 1.3 — Store API
# ============================================================================


@pytest.mark.unit
class TestStoreApiCompat:

    def test_async_postgres_store_importable(self):
        from langgraph.store.postgres import AsyncPostgresStore  # noqa: F401

    def test_base_store_types_importable(self):
        from langgraph.store.base import BaseStore, Item, SearchItem  # noqa: F401


# ============================================================================
# 1.4 — HITL types (Command, interrupt, errors)
# → See test_langgraph_types_stability.py for comprehensive LangGraph type tests
# ============================================================================


# ============================================================================
# 1.5 — LangChain core API
# ============================================================================


@pytest.mark.unit
class TestLangChainCoreCompat:

    def test_callback_handler_importable(self):
        from langchain_core.callbacks import AsyncCallbackHandler  # noqa: F401

    def test_llm_result_importable(self):
        from langchain_core.outputs import LLMResult  # noqa: F401

    def test_message_types_importable(self):
        from langchain_core.messages import (  # noqa: F401
            AIMessage,
            AIMessageChunk,
            HumanMessage,
            SystemMessage,
            ToolMessage,
        )

    def test_runnable_config_importable(self):
        from langchain_core.runnables import RunnableConfig  # noqa: F401

    def test_base_chat_model_has_structured_output(self):
        from langchain_core.language_models.chat_models import BaseChatModel

        assert hasattr(BaseChatModel, "with_structured_output")

    def test_tool_decorator_importable(self):
        from langchain_core.tools import tool

        assert callable(tool)


# ============================================================================
# 1.6 — ContextOverflowError (requires langchain-core >= 1.2.10)
# ============================================================================


@pytest.mark.unit
class TestContextOverflowErrorCompat:

    def test_context_overflow_error_importable(self):
        """Available in langchain-core >= 1.2.10."""
        from langchain_core.exceptions import ContextOverflowError

        assert issubclass(ContextOverflowError, Exception)

    def test_context_overflow_error_instantiable(self):
        from langchain_core.exceptions import ContextOverflowError

        err = ContextOverflowError("Context window exceeded")
        assert "Context window exceeded" in str(err)


# ============================================================================
# 1.7 — Middleware LangChain
# ============================================================================


@pytest.mark.unit
class TestMiddlewareCompat:

    def test_middleware_module_importable(self):
        from langchain.agents import middleware

        assert middleware is not None

    @pytest.mark.parametrize(
        "class_name",
        [
            "SummarizationMiddleware",
            "ModelFallbackMiddleware",
            "ToolRetryMiddleware",
            "ModelCallLimitMiddleware",
            "ContextEditingMiddleware",
            "HumanInTheLoopMiddleware",
        ],
    )
    def test_middleware_class_available(self, class_name: str):
        from langchain.agents import middleware

        assert hasattr(middleware, class_name), f"{class_name} not found in middleware"


# ============================================================================
# 1.8 — Providers
# ============================================================================


@pytest.mark.unit
class TestProviderCompat:

    def test_openai_importable(self):
        from langchain_openai import ChatOpenAI  # noqa: F401

    def test_anthropic_importable(self):
        from langchain_anthropic import ChatAnthropic  # noqa: F401

    def test_google_genai_importable(self):
        from langchain_google_genai import ChatGoogleGenerativeAI  # noqa: F401


# ============================================================================
# 1.9 — Langfuse
# ============================================================================


@pytest.mark.unit
class TestLangfuseCompat:

    def test_langfuse_callback_importable(self):
        from langfuse.langchain import CallbackHandler  # noqa: F401


# ============================================================================
# 1.10 — add_messages comportemental
# → See test_langgraph_types_stability.py for comprehensive add_messages tests
# ============================================================================
