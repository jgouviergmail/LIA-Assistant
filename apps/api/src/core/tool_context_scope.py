"""Explicit runtime ancestry for exact tool-context namespaces."""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

VoiceContextSurface = Literal["phone_call", "live_session"]
VOICE_CONTEXT_SURFACES: frozenset[str] = frozenset({"phone_call", "live_session"})


@dataclass(frozen=True, slots=True)
class ChildToolContextScope:
    """A synthetic child lives under its declared parent's cleanup prefix."""

    runtime_id: UUID
    child_id: str


type ToolContextScope = str | ChildToolContextScope


def tool_context_namespace(owner_id: str, scope: ToolContextScope, domain: str) -> tuple[str, ...]:
    """Keep exact lookups while making all children discoverable by runtime."""
    if isinstance(scope, ChildToolContextScope):
        return (owner_id, str(scope.runtime_id), "context", domain, scope.child_id)
    return (owner_id, scope, "context", domain)


def tool_context_scope(thread_id: object, runtime_id: object = None) -> ToolContextScope | None:
    """Read declared ancestry; a synthetic thread never reveals its parent by shape."""
    if not isinstance(thread_id, str) or not thread_id:
        return None
    if runtime_id is None:
        return thread_id
    if not isinstance(runtime_id, (UUID, str)):
        raise ValueError("Invalid parent runtime identity")
    parent = runtime_id if isinstance(runtime_id, UUID) else UUID(runtime_id)
    if thread_id == str(parent):
        return thread_id
    return ChildToolContextScope(parent, thread_id)


def voice_context_id(surface: VoiceContextSurface, key: str) -> str:
    """Declare the non-conversation context of a direct voice lookup."""
    UUID(key)
    return f"{surface}:{key}"


def is_voice_context_id(value: str) -> bool:
    """Read the explicitly declared wire form, never infer a conversation parent."""
    surface, separator, key = value.partition(":")
    if not separator or surface not in VOICE_CONTEXT_SURFACES:
        return False
    try:
        UUID(key)
    except ValueError:
        return False
    return True
