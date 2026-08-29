"""Install a typed run context around code that expects to run inside the graph.

ADR-231 moved the run-scoped context out of ``config["configurable"]`` into a
frozen ``LiaRuntimeContext`` read through a ContextVar. In production every reader
runs inside a graph run, so ``runtime_context_if_running()`` always answers. A
unit test that calls a node, a service or a tool *directly* has no run — and
before this helper, each test that needed one either passed ``context=None`` (six
files did, each rolling its own ``ToolRuntime``) or could not exercise the real
contract at all.

This is the single place that knows how to install a context outside a run. It
deliberately touches LangGraph internals (``CONF`` / ``CONFIG_KEY_RUNTIME``):
``get_runtime()`` reads the runtime out of the RunnableConfig ContextVar under a
private key, and there is no public writer for it. Keeping that knowledge in ONE
test helper means a LangGraph upgrade that moves the key breaks a single, loudly
named place — ``test_runtime_context_helper.py`` pins the mechanism — instead of
scattering private imports across the suite. Production code never imports this.

Typical uses::

    with installed_runtime_context(language="de"):
        result = await router_node_v3(state, config)

    runtime = make_tool_runtime(configurable={"thread_id": "t"})
    output = await my_tool.ainvoke({"x": 1, "runtime": runtime})
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from langchain.tools import ToolRuntime
from langchain_core.runnables.config import var_child_runnable_config
from langgraph._internal._constants import CONF, CONFIG_KEY_RUNTIME
from langgraph.runtime import Runtime

from src.domains.agents.context.runtime_context import LiaRuntimeContext

__all__ = [
    "installed_runtime_context",
    "no_runtime_context",
    "make_contextless_tool_runtime",
    "make_runtime_context",
    "make_tool_runtime",
]

#: Stable identity for tests that do not care which user they run as. A fixed
#: value keeps assertions and Store namespaces reproducible across runs.
DEFAULT_TEST_USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
DEFAULT_TEST_CONVERSATION_ID = "test-conversation"


def make_runtime_context(**overrides: Any) -> LiaRuntimeContext:
    """Build a valid runtime context, overriding only what the test is about.

    Args:
        **overrides: Any field of :class:`LiaRuntimeContext`.

    Returns:
        A context with sane, reproducible defaults.
    """
    base: dict[str, Any] = {
        "user_id": DEFAULT_TEST_USER_ID,
        "thread_id": DEFAULT_TEST_CONVERSATION_ID,
        "conversation_id": DEFAULT_TEST_CONVERSATION_ID,
    }
    return LiaRuntimeContext(**{**base, **overrides})


@contextmanager
def installed_runtime_context(
    context: LiaRuntimeContext | None = None, **overrides: Any
) -> Iterator[LiaRuntimeContext]:
    """Make ``runtime_context_if_running()`` answer for the duration of the block.

    Restores the previous state on exit — including when the body raises — so
    tests cannot leak a context into their neighbours (the isolation failure that
    would make a suite pass only in a given order).

    Args:
        context: An explicit context; built from ``overrides`` when omitted.
        **overrides: Fields forwarded to :func:`make_runtime_context`.

    Yields:
        The installed context, so the test can assert on the very same object.
    """
    installed = context if context is not None else make_runtime_context(**overrides)
    token = var_child_runnable_config.set({CONF: {CONFIG_KEY_RUNTIME: Runtime(context=installed)}})
    try:
        yield installed
    finally:
        var_child_runnable_config.reset(token)


@contextmanager
def no_runtime_context() -> Iterator[None]:
    """Make ``runtime_context_if_running()`` answer None inside the block.

    The counterpart of :func:`installed_runtime_context`, for the tests that
    exercise "this code ran outside a graph run" while a module- or class-level
    fixture has installed a context for everything else. Restores the previous
    state on exit, including when the body raises.
    """
    token = var_child_runnable_config.set({})
    try:
        yield
    finally:
        var_child_runnable_config.reset(token)


def make_tool_runtime(
    *,
    context: LiaRuntimeContext | None = None,
    configurable: dict[str, Any] | None = None,
    store: Any = None,
    state: Any = None,
    tool_call_id: str | None = None,
    **context_overrides: Any,
) -> ToolRuntime[LiaRuntimeContext, Any]:
    """Build the ``ToolRuntime`` the tool layer injects, carrying a real context.

    Replaces six hand-rolled constructions that all passed ``context=None`` and
    therefore could not exercise the typed contract.

    Args:
        context: An explicit context; built from ``context_overrides`` when omitted.
        configurable: Extra ``configurable`` entries. ``thread_id`` defaults to the
            context's thread so the two planes agree, as they do in production.
        store: The store the tool will see.
        state: The graph state the tool will see.
        tool_call_id: The tool call id, when the tool reads it.
        **context_overrides: Fields forwarded to :func:`make_runtime_context`.

    Returns:
        A ready-to-inject ``ToolRuntime``.
    """
    ctx = context if context is not None else make_runtime_context(**context_overrides)
    merged = {"thread_id": ctx.thread_id, "user_id": str(ctx.user_id), **(configurable or {})}
    return ToolRuntime(
        state=state,
        context=ctx,
        config={"configurable": merged},
        stream_writer=lambda _: None,
        tool_call_id=tool_call_id,
        store=store,
    )


def make_contextless_tool_runtime(
    *, configurable: dict[str, Any] | None = None, store: Any = None, state: Any = None
) -> ToolRuntime[Any, Any]:
    """Build the runtime a tool sees when it runs OUTSIDE any graph run.

    Distinct from :func:`make_tool_runtime`, which always carries a context. Since
    ``LiaRuntimeContext.user_id`` is mandatory and typed, "the tool sees no acting
    user" is no longer expressible as a missing key — it is only expressible as
    "there is no run context at all" (ADR-231). Tests that exercise the
    no-identity short-circuits need exactly this shape.

    Args:
        configurable: Extra ``configurable`` entries (LangGraph plumbing only).
        store: The store the tool will see.
        state: The graph state the tool will see.

    Returns:
        A ``ToolRuntime`` whose ``context`` is None.
    """
    return ToolRuntime(
        state=state,
        context=None,
        config={"configurable": configurable or {}},
        stream_writer=lambda _: None,
        tool_call_id=None,
        store=store,
    )
