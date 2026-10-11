"""Approved source embedding work is bounded, attributed and runs outside write locks."""

from collections.abc import Awaitable, Callable
from uuid import UUID

from src.domains.interests import helpers
from src.infrastructure.llm.embedding_context import (
    clear_embedding_context,
    get_embedding_context,
    set_embedding_context,
)
from src.infrastructure.llm.usage_guard import enforce_usage_limit


async def prepare_interest_embedding(
    user_id: UUID, command_id: UUID, topic: str, guard: Callable[[], Awaitable[None]]
) -> list[float] | None:
    previous = get_embedding_context()
    set_embedding_context(
        str(user_id), f"application-interest:{command_id}", run_id=str(command_id)
    )
    try:
        await guard()
        await enforce_usage_limit(user_id, layer="application_interest")
        return await helpers.generate_interest_embedding(topic)
    finally:
        clear_embedding_context()
        if previous is not None:
            set_embedding_context(
                previous.user_id, previous.session_id, previous.conversation_id, previous.run_id
            )
