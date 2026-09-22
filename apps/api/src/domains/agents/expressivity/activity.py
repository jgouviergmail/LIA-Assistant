"""Bounded, payload-free evidence for the companion's current activity.

The effect gate calls this ONLY around the original operation, after admission
and deduplication. Neither a plan, a requested call nor a served ledger result
can produce an event. Nested capabilities keep their parent's performance.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Literal
from uuid import uuid4

import structlog
from langgraph.errors import GraphInterrupt
from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.domains.agents.effects.scope import current_scope
from src.domains.agents.registry.catalogue import ToolManifest, infer_tool_category_or_none
from src.domains.agents.registry.manifest_resolution import resolve_tool_manifest

ActivityFamily = Literal[
    "reading", "organizing", "communicating", "calculating", "creating", "exploring", "generic"
]
ActivityOutcome = Literal["succeeded", "prepared", "failed", "cancelled", "waiting", "unknown"]
logger = structlog.get_logger(__name__)

# These executors bypass tool manifests. Keys are the draft registry's public
# discriminants, never inferred from a requested call or a model's wording.
DRAFT_FAMILIES: dict[str, ActivityFamily] = {
    **dict.fromkeys(
        ("email", "email_reply", "email_forward", "phone_call", "peer_message"), "communicating"
    ),
    **dict.fromkeys(
        (
            "event",
            "event_update",
            "event_delete",
            "contact",
            "contact_update",
            "contact_delete",
            "task",
            "task_update",
            "task_delete",
            "email_delete",
            "file_delete",
            "label_delete",
            "reminder_delete",
            "scheduled_action",
            "vacation_responder",
            "email_filter",
            "ticket_delete",
        ),
        "organizing",
    ),
    "spreadsheet_write": "creating",
    "document_append": "creating",
    "devops_task": "exploring",
    "sandbox_egress": "exploring",
    "tool_call": "generic",
}


class Activity(BaseModel):
    """Versioned evidence, never tool arguments, names, results or error text."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    version: Literal[1] = 1
    run_id: str = Field(min_length=1, max_length=200)
    invocation_id: str = Field(min_length=1, max_length=100)
    family: ActivityFamily
    intent: Literal["read", "prepare", "act"]
    phase: Literal["started", "finished"]
    outcome: ActivityOutcome | None = None

    @model_validator(mode="after")
    def coherent_phase(self) -> Activity:
        if (self.phase == "started") != (self.outcome is None):
            raise ValueError("a terminal phase requires an outcome; a start has none")
        return self


_ACTIVE: ContextVar[bool] = ContextVar("companion_activity_active", default=False)
_CAPTURE: ContextVar[tuple[str, list[Activity]] | None] = ContextVar(
    "companion_activity_capture", default=None
)


@contextmanager
def capture_activity(run_id: str) -> Iterator[list[Activity]]:
    """A direct voice lookup has an HTTP response instead of the chat side channel."""
    events: list[Activity] = []
    token = _CAPTURE.set((run_id, events))
    try:
        yield events
    finally:
        _CAPTURE.reset(token)


def activity_family(manifest: ToolManifest | None) -> ActivityFamily:
    """Read the existing catalogue; an unknown tool stays deliberately generic."""
    if manifest is None:
        return "generic"
    agent = manifest.agent.removesuffix("_agent")
    category = manifest.tool_category or infer_tool_category_or_none(manifest.name)
    if agent in {"python_sandbox", "query"}:
        return "calculating"
    if agent in {"browser", "sub_agent", "skill", "skills"}:
        return "exploring"
    if category == "send":
        return "communicating"
    if category in {"search", "readonly"}:
        return "reading"
    if agent in {"event", "task", "contact", "reminder", "label", "scheduled_action", "automation"}:
        return "organizing"
    if manifest.mutation_policy == "artefact" or category == "create":
        return "creating"
    return "generic"


def _field(result: object, name: str) -> object:
    return result.get(name) if isinstance(result, Mapping) else getattr(result, name, None)


def activity_outcome(result: object, policy: str | None) -> ActivityOutcome:
    """Only explicit success is success; preparing a draft never means acting."""
    success = _field(result, "success")
    if success is False:
        return "failed"
    if policy == "draft" or _field(result, "draft_id"):
        return "prepared"
    if success is True:
        return "succeeded"
    return "unknown"


def emit_activity(activity: Activity) -> None:
    """Use the run's existing side channel, including confirmed-draft resumes."""
    capture = _CAPTURE.get()
    if capture is not None:
        capture[1][:] = [activity]  # Only the latest event, bounded even for nested providers.
    context = runtime_context_if_running()
    if context is None or context.side_channel_queue is None or not activity.run_id:
        return
    try:
        context.side_channel_queue.put_nowait(
            ChatStreamChunk(
                type="execution_step",
                content="",
                metadata={"step_type": "activity", "activity": activity.model_dump(mode="json")},
            )
        )
    except asyncio.QueueFull:
        # Decoration cannot backpressure the execution or its cancellation.
        return


def _start(tool_name: str, policy: str | None) -> Activity:
    scope = current_scope()
    manifest = resolve_tool_manifest(tool_name)
    intent: Literal["read", "prepare", "act"] = "read"
    if policy == "draft":
        intent = "prepare"
    elif policy in {"confirm", "reversible", "artefact"}:
        intent = "act"
    capture = _CAPTURE.get()
    run_id = scope.run_id if scope else capture[0] if capture else ""
    return Activity(
        run_id=run_id,
        invocation_id=uuid4().hex,
        family=(
            DRAFT_FAMILIES.get(tool_name.removeprefix("draft:"), "generic")
            if tool_name.startswith("draft:")
            else "reading" if tool_name == "recall_memories" else activity_family(manifest)
        ),
        intent=intent,
        phase="started",
    )


def _safe_emit(activity: Activity) -> None:
    try:
        emit_activity(activity)
    except Exception as exc:
        logger.warning("companion_activity_delivery_failed", error_type=type(exc).__name__)


def _observable() -> bool:
    context = runtime_context_if_running()
    return _CAPTURE.get() is not None or (
        context is not None and context.side_channel_queue is not None
    )


async def observe_activity[T](
    tool_name: str, policy: str | None, act: Callable[[], Awaitable[T]]
) -> T:
    """Observe one actual invocation, preserving result identity and all exceptions."""
    if _ACTIVE.get():
        return await act()
    try:
        start = _start(tool_name, policy) if _observable() else None
    except Exception as exc:
        logger.warning("companion_activity_unavailable", error_type=type(exc).__name__)
        start = None
    if start is None:
        return await act()
    token = _ACTIVE.set(True)
    _safe_emit(start)
    outcome: ActivityOutcome = "unknown"
    try:
        result = await act()
        try:
            outcome = activity_outcome(result, policy)
        except Exception:
            outcome = "unknown"
        return result
    except asyncio.CancelledError:
        outcome = "cancelled"
        raise
    except GraphInterrupt:
        outcome = "waiting"
        raise
    except Exception:
        outcome = "failed"
        raise
    finally:
        try:
            _safe_emit(start.model_copy(update={"phase": "finished", "outcome": outcome}))
        finally:
            _ACTIVE.reset(token)


async def observe_read[T](tool_name: str, operation: Awaitable[T]) -> T:
    """Observe a native lookup with no manifest or effect-gate wrapper."""
    return await observe_activity(tool_name, "read", lambda: operation)
