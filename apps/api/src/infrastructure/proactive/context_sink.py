"""Injected owner-scoped continuity writes; domains never import their agent consumer."""

from collections.abc import Awaitable, Callable
from uuid import UUID

from pydantic import JsonValue

ProactiveContextWriter = Callable[[UUID, dict[str, JsonValue]], Awaitable[None]]
_writer: ProactiveContextWriter | None = None


def configure_proactive_context_writer(
    writer: ProactiveContextWriter | None,
) -> ProactiveContextWriter | None:
    global _writer
    previous, _writer = _writer, writer
    return previous


async def write_heartbeat_context(actor_id: UUID, value: dict[str, JsonValue]) -> None:
    writer = _writer
    if writer is None:
        raise RuntimeError("Proactive context writer is not initialized")
    await writer(actor_id, value)
