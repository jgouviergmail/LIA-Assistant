"""Typed, run-scoped context for the agent graph (ADR-231).

Replaces the untyped ``config["configurable"]`` bag that carried the run context:
17 keys written at a single chokepoint and read across 43 files, four of them
private (``__deps``, ``__browser_context``, ``__user_message``,
``__side_channel_queue``) — an enforced but unpublished contract, the class
ADR-184 named. The same identity travelled under two keys and two types:
``user_id`` as a ``uuid.UUID`` from the chokepoint but a ``str`` from the parallel
executor, plus a ``langgraph_user_id`` duplicate justified by a LangMem
integration that is not installed.

Two measured properties of LangGraph shape this design:

- **The context is never checkpointed.** Verified with a sentinel value written
  nowhere in the state: it appears neither in the latest checkpoint nor anywhere
  in the history. So nothing that must survive an interrupt resume may live here
  — that belongs in ``MessagesState``.
- **The context is never copied.** Object identity is preserved through node,
  subgraph and tool, so live run dependencies (an ``asyncio.Queue``, the tool
  dependency container, an open transport) are safe as fields.

The dataclass is frozen: a run's context is read-only for the nodes that consume
it. Mutating a field's *contents* (appending to a queue) remains possible and is
the intended way to use the live dependencies.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field, replace
from typing import Any

from langgraph.runtime import get_runtime
from langgraph.store.base import BaseStore

from src.core.config import settings
from src.core.constants import (
    DEFAULT_TIMEZONE,
    EXECUTION_MODE_PIPELINE,
    RESPONSE_DISPLAY_MODE_DEFAULT,
)

# ``BaseStore`` and ``asyncio`` are imported at RUNTIME, not under TYPE_CHECKING:
# every tool's parameter is annotated ``ToolRuntime[LiaRuntimeContext, Any]``, and
# Pydantic resolves that annotation when it builds the tool's schema. Deferring
# either import breaks every such tool with
# "`<tool>` is not fully defined; you should define `BaseStore`". Neither module
# imports back into this package, so there is no cycle to avoid.

__all__ = [
    "LiaRuntimeContext",
    "assert_runtime_context",
    "derive_sub_agent_context",
    "runtime_context_if_running",
    "runtime_user_id_str",
    "tool_runtime_context",
    "tool_user_id_str",
]


@dataclass(frozen=True, slots=True)
class LiaRuntimeContext:
    """Everything a run needs to know about who and what it is running for.

    Declared as the graph's ``context_schema`` and injected at four points: the
    ``graph.astream`` call, the ``ToolRuntime`` built by the parallel executor,
    the synthetic runtime built for skill location resolution, and the ReAct
    sub-agent's ``ainvoke`` (which receives the parent's context derived via
    :func:`derive_sub_agent_context`).

    Attributes:
        user_id: The acting user. Canonical and unique — there is no string
            twin, and no ``langgraph_user_id``.
        thread_id: LangGraph thread. Equals ``conversation_id`` for a normal run,
            and is replaced by a synthetic value for a sub-agent run.
        conversation_id: The conversation this run belongs to. Unlike
            ``thread_id`` it is stable across sub-agent derivation, so a
            side-effect can always attribute itself to the real conversation.
        store: Long-term memory store, injected at graph compile time.
        memory_enabled: User preference — long-term memory extraction.
        journals_enabled: User preference — personal journals.
        psyche_enabled: User preference — psyche engine.
        display_mode: Render mode the user chose (cards / html / markdown).
        execution_mode: Pipeline or ReAct (ADR-070).
        is_automated_source: True for runs the user did not type (scheduled
            actions, heartbeat); post-response extractions are skipped for those.
        deps: Tool dependency container. A live object, passed by reference.
        browser_context: Consented geolocation and client hints, when the client
            supplied them. Read by the location-aware tools.
        user_message: The original user message, kept for location-phrase
            detection that needs the raw wording rather than the planned params.
        side_channel_queue: SSE side channel a tool can push progress onto. A
            live queue, passed by reference.
        timezone: The user's display timezone.
        language: The user's language, backend-canonical (``zh-CN``, not ``zh``).
        display_name: The user's name, used as a sender identity by
            content-generating tools such as email signatures.
    """

    user_id: uuid.UUID
    thread_id: str
    conversation_id: str

    store: BaseStore | None = None

    memory_enabled: bool = False
    journals_enabled: bool = False
    psyche_enabled: bool = False
    is_automated_source: bool = False

    display_mode: str = RESPONSE_DISPLAY_MODE_DEFAULT
    execution_mode: str = EXECUTION_MODE_PIPELINE
    timezone: str = DEFAULT_TIMEZONE
    language: str = field(default_factory=lambda: settings.default_language)
    display_name: str | None = None

    deps: Any = None
    browser_context: Any = None
    user_message: str = ""
    side_channel_queue: asyncio.Queue | None = None

    @classmethod
    def for_conversation(
        cls, *, user_id: uuid.UUID, conversation_id: uuid.UUID, **overrides: Any
    ) -> LiaRuntimeContext:
        """Build the context of a normal conversation run.

        The single construction rule the chokepoint applies: LangGraph's
        ``thread_id`` **is** the conversation id. Keeping it here rather than at
        the call site means a sub-agent deriving a synthetic thread
        (``dataclasses.replace(ctx, thread_id=...)``) cannot accidentally lose the
        conversation it belongs to — ``conversation_id`` survives independently.

        Args:
            user_id: The acting user.
            conversation_id: The conversation this run belongs to.
            **overrides: Any other field of the context.

        Returns:
            A ready-to-inject runtime context.
        """
        return cls(
            user_id=user_id,
            conversation_id=str(conversation_id),
            thread_id=str(conversation_id),
            **overrides,
        )


def tool_runtime_context(runtime: object) -> LiaRuntimeContext | None:
    """The context a tool was injected with, or None.

    A tool must read its OWN ``runtime.context`` rather than the ambient
    ContextVar: the runtime is the explicit contract the tool layer hands it, it
    is what a test can construct, and it is what stays correct if a tool is ever
    driven from outside the run that built the context.
    :func:`runtime_context_if_running` is the counterpart for code that has no
    runtime parameter to read — nodes, services, the parallel executor.

    Args:
        runtime: The injected ``ToolRuntime`` (or None).

    Returns:
        The typed context, or None when the tool ran outside the agent layer.
    """
    context = getattr(runtime, "context", None) if runtime is not None else None
    return context if isinstance(context, LiaRuntimeContext) else None


def tool_user_id_str(runtime: object, default: str | None = None) -> str | None:
    """The acting user's id as a string, from the tool's own runtime.

    Args:
        runtime: The injected ``ToolRuntime``.
        default: What to return when the tool has no context.

    Returns:
        The stringified user id, or ``default``.
    """
    context = tool_runtime_context(runtime)
    return str(context.user_id) if context is not None else default


def runtime_language(default: str | None = None) -> str:
    """The run's language, backend-canonical.

    Args:
        default: What to answer outside a run. ``None`` means the configured
            default language — the same source the context itself uses, so the
            two can never disagree.

    Returns:
        The language code.
    """
    context = runtime_context_if_running()
    if context is not None:
        return context.language
    return default if default is not None else settings.default_language


def runtime_timezone(default: str = DEFAULT_TIMEZONE) -> str:
    """The run's display timezone.

    Args:
        default: What to answer outside a run. Call sites differ deliberately —
            ``DEFAULT_TIMEZONE`` ("UTC") is the storage default, while
            ``DEFAULT_USER_DISPLAY_TIMEZONE`` is what a human-facing rendering
            falls back to — so the default stays explicit rather than assumed.

    Returns:
        An IANA timezone name.
    """
    context = runtime_context_if_running()
    return context.timezone if context is not None else default


def runtime_psyche_enabled(default: bool = False) -> bool:
    """Whether the psyche engine is enabled for this run."""
    context = runtime_context_if_running()
    return context.psyche_enabled if context is not None else default


def runtime_browser_context() -> Any:
    """The consented geolocation and client hints, or None outside a run."""
    context = runtime_context_if_running()
    return context.browser_context if context is not None else None


def runtime_display_mode(default: str = RESPONSE_DISPLAY_MODE_DEFAULT) -> str:
    """The render mode the user chose (cards / html / markdown).

    Args:
        default: What to answer outside a run.

    Returns:
        The display mode.
    """
    context = runtime_context_if_running()
    return context.display_mode if context is not None else default


def runtime_deps() -> Any:
    """The tool dependency container carried by the run, or None outside one."""
    context = runtime_context_if_running()
    return context.deps if context is not None else None


def runtime_user_id_str(default: str | None = "") -> str | None:
    """The run's user id, as the string most call sites still speak.

    The canonical identity is a ``uuid.UUID`` on the context; Store namespaces,
    log fields and tool payloads are string-keyed, so the projection happens here
    once instead of at every call site — which is how the codebase ended up with
    a ``user_id`` and a ``langgraph_user_id`` spelling of the same value.

    Args:
        default: What to return outside a graph run (a direct call from a unit
            test or a script). Each call site keeps the default its previous bag
            lookup used, so migrating changes no behaviour.

    Returns:
        The stringified user id, or ``default`` outside a run.
    """
    context = runtime_context_if_running()
    return str(context.user_id) if context is not None else default


def derive_sub_agent_context(parent: LiaRuntimeContext, *, thread_id: str) -> LiaRuntimeContext:
    """Derive a sub-agent's context from its parent, changing only the thread.

    Replaces a hand-written projection that carried 6 of the parent's 17 values
    and dropped 11 — the consented geolocation, the raw user message, the sender
    identity, the automated-source flag. Latent when it was written, because the
    default sub-agent whitelist reads none of them, but that whitelist is
    ``.env``-configurable: adding one location-aware tool would have degraded
    geolocation in silence, and the *next* field added to the context would have
    been lost the same way.

    Deriving makes "inherit" the default, so a new field is carried without
    touching this function. ``conversation_id`` is a field of its own precisely
    so that a synthetic thread does not detach a sub-run from the conversation it
    belongs to.

    Args:
        parent: The context of the run spawning the sub-agent.
        thread_id: The sub-run's isolated LangGraph thread.

    Returns:
        The parent's context with ``thread_id`` replaced. Live dependencies keep
        their identity — LangGraph does not copy the context.
    """
    return replace(parent, thread_id=thread_id)


def runtime_context_if_running() -> LiaRuntimeContext | None:
    """Read the run context, tolerating callers that run outside a graph.

    Distinguishes the two situations a naive read conflates:

    - **No graph run at all** — a direct call from a unit test, a script, or a
      service reached outside the agent layer. Returns ``None``; that is not the
      defect this migration guards against.
    - **A run whose context is missing or malformed** — exactly the measured trap:
      with ``context_schema`` declared but no ``context=`` supplied, a run
      (a HITL resume in particular) succeeds silently and every node reads
      ``None``. Raises.

    Returns:
        The context of the run in progress, or ``None`` outside any run.

    Raises:
        RuntimeError: Inside a run that carries no valid context.
    """
    try:
        runtime = get_runtime(LiaRuntimeContext)
    except RuntimeError:
        # No RunnableConfig at all: a plain call from a test or a script.
        return None
    if runtime is None:
        # A RunnableConfig exists but carries no LangGraph runtime. This happens
        # whenever a tool is invoked through ``.ainvoke()`` outside the graph —
        # LangChain installs a child config, LangGraph never filled it — and
        # ``get_runtime`` reads that slot with ``.get()``, so it returns None
        # instead of raising. Treating it as "no run" is what the caller means.
        return None
    return assert_runtime_context(runtime.context)


def assert_runtime_context(value: object) -> LiaRuntimeContext:
    """Return the value as a runtime context, or fail loudly.

    Guards the trap this whole migration exists to remove: with ``context_schema``
    declared but no context supplied, a run — including a resume after a HITL
    interrupt — succeeds **silently** and every node reads ``None``. Measured, not
    assumed. Doctrine ADR-085: refuse to proceed rather than degrade.

    The pre-migration shape (a raw ``dict``) is rejected for the same reason: it
    would read as "present" while carrying none of the guarantees.

    Args:
        value: Whatever ``runtime.context`` yielded.

    Returns:
        The value, narrowed to ``LiaRuntimeContext``.

    Raises:
        RuntimeError: When the runtime context is absent or of the wrong shape.
    """
    if isinstance(value, LiaRuntimeContext):
        return value

    raise RuntimeError(
        "runtime context missing or malformed: expected a LiaRuntimeContext, got "
        f"{type(value).__name__}. Every graph run must pass context=... to "
        "graph.astream — including a resume after a HITL interrupt, where a "
        "missing context otherwise degrades silently (ADR-231)."
    )
