"""What the caller knows and the gate cannot see (ADR-263).

The gate is installed on the tool itself, so it sees the arguments and the run
context — but not the things only the EXECUTOR knows: which call this is
(``tool_call_id``, ``step_id``, ``draft_id``), whether a human confirmed it,
and which run it belongs to. Those travel in a ``ContextVar`` set around the
call, the same way ``draft_executor`` already carries its SSE queue: it costs no
signature change across three executors and 119 tools.

Absence of a scope is never treated as permission. It means no executor
published one, so nobody can have confirmed anything — the gate refuses a
``confirm`` effect and counts every other one it lets through.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace

from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.domains.agents.effects.schemas import EffectSourceName


@dataclass(frozen=True)
class EffectScope:
    """The authority under which the current tool call runs.

    Attributes:
        run_id: Billing/correlation id of the run performing the call.
        idempotency_key: Identity of THIS call, unique within the thread —
            ``tool_call_id`` in ReAct, ``run_id:step_id`` in the pipeline,
            ``draft_id`` for a confirmed draft.
        source: Who asked for the turn.
        approved: True only when a human explicitly confirmed THIS operation.
        approval_kind: How it was confirmed, when it was.
        approval_ref: The card's ``message_id`` or the ``draft_id``.
        draft_digest: Digest of the draft content the user was shown, so the
            ledger records that what ran is what was displayed (ADR-092).
    """

    run_id: str
    idempotency_key: str
    source: EffectSourceName = "user"
    approved: bool = False
    approval_kind: str | None = None
    approval_ref: str | None = None
    draft_digest: str | None = None


_CURRENT_SCOPE: ContextVar[EffectScope | None] = ContextVar("agent_effect_scope", default=None)


def current_scope() -> EffectScope | None:
    """Return the scope of the running tool call, or None outside one."""
    return _CURRENT_SCOPE.get()


@contextmanager
def effect_scope(scope: EffectScope) -> Iterator[EffectScope]:
    """Publish ``scope`` for the duration of a tool call.

    Always resets, so concurrent runs never see each other's authority — the
    same discipline as the draft executor's side-channel queue.

    Args:
        scope: The authority to publish.

    Yields:
        The scope, so a caller can derive from it.
    """
    token = _CURRENT_SCOPE.set(scope)
    try:
        yield scope
    finally:
        _CURRENT_SCOPE.reset(token)


def approved_scope(scope: EffectScope, *, kind: str, ref: str | None = None) -> EffectScope:
    """Derive the same scope carrying an explicit human confirmation.

    Args:
        scope: The scope to derive from.
        kind: How the user confirmed (``tool_confirmation``, ``draft_critique``…).
        ref: The card's message id, or the draft id.

    Returns:
        A new scope; the original is frozen and untouched.
    """
    return replace(scope, approved=True, approval_kind=kind, approval_ref=ref)


def scope_from_config(
    config: object,
    *,
    idempotency_key: str,
    approved: bool = False,
    approval_kind: str | None = None,
    approval_ref: str | None = None,
    draft_digest: str | None = None,
    run_id: str | None = None,
) -> EffectScope:
    """Build the scope of one call from the run's ``RunnableConfig``.

    Factored here because all three executors need the same two facts — the
    run id and who asked for the turn — and a fourth executor should get them
    the same way rather than re-deriving them.

    Args:
        config: The LangGraph ``RunnableConfig`` of the running node.
        idempotency_key: Identity of THIS call within the thread.
        approved: True only when a human explicitly confirmed this operation.
        approval_kind: How they confirmed it.
        approval_ref: The card's message id, or the draft id.
        draft_digest: Digest of the draft content they were shown.
        run_id: The run, when the CALLER already holds it. Measured 2026-09-04:
            the draft executor receives the authoritative ``run_id`` as an
            argument and rebuilt the scope from ``config`` instead — on a HITL
            resume that config carries none, so the effect was filed under the
            THREAD id and the turn summary, which looks up by run, found
            nothing. The card was invisible for the one path that produces
            most effects. A caller that knows must not be made to guess.

    Returns:
        The scope to publish around the call.
    """
    from src.domains.agents.context.runtime_context import runtime_context_if_running

    configurable: dict[str, object] = {}
    if isinstance(config, dict):
        configurable = config.get("configurable") or {}
    resolved = run_id or str(configurable.get("run_id") or "")

    context = runtime_context_if_running()
    if not resolved:
        # A run with no id in its config still has a thread; the ledger needs a
        # correlation value, never an invented one.
        resolved = context.thread_id if context is not None else "unknown"
    source: EffectSourceName = (
        "scheduled" if context is not None and context.is_automated_source else "user"
    )
    return EffectScope(
        run_id=resolved,
        idempotency_key=idempotency_key,
        source=source,
        approved=approved,
        approval_kind=approval_kind,
        approval_ref=approval_ref,
        draft_digest=draft_digest,
    )


def react_call_scope(config: object, tool_call_id: str, *, approved: bool) -> EffectScope:
    """Scope of one ReAct tool call, named by its ``tool_call_id``.

    The id is the natural idempotency key: LangGraph replays the whole node on
    a resume, so the same call carries the same id and the ledger recognises it
    — which is what stops an interrupted iteration from performing its earlier
    calls a second time (measured: it does today).

    Args:
        config: The node's ``RunnableConfig``.
        tool_call_id: The model's id for this call.
        approved: True when the call passed the pre-execution confirmation.

    Returns:
        The scope to publish around the call.
    """
    return scope_from_config(
        config,
        idempotency_key=f"call:{tool_call_id}",
        approved=approved,
        approval_kind="tool_confirmation" if approved else None,
    )


def step_effect_key(config: object, step_id: str) -> str:
    """Idempotency key of one PIPELINE step — scoped to its run.

    A step id comes from the plan (``search``, ``send``…) and repeats across
    turns: two turns whose plans share a step id would collide on the unique
    ``(thread_id, idempotency_key)``, and the SECOND turn's effect would be
    served from the ledger instead of performed — a silent no-op the user would
    read as a success. The run id is what makes the key unique per turn while
    staying stable across a replay of the same turn.

    Args:
        config: The node's ``RunnableConfig``.
        step_id: The plan step, or the tool name when a step has no id.

    Returns:
        The key to claim under.
    """
    configurable = config.get("configurable") or {} if isinstance(config, dict) else {}
    run_id = str(configurable.get("run_id") or "")
    if not run_id:
        context = runtime_context_if_running()
        run_id = context.thread_id if context is not None else "unknown"
    return f"{run_id}:step:{step_id}"
