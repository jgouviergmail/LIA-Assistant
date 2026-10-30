"""Bound and attribute optional probe embeddings outside all write locks."""

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Protocol
from uuid import UUID

from pydantic import JsonValue, TypeAdapter

from src.domains.usage_limits.enforcement import spend_blocked
from src.infrastructure.llm.embedding_context import (
    clear_embedding_context,
    get_embedding_context,
    set_embedding_context,
)
from src.infrastructure.llm.usage_guard import enforce_usage_limit


class MCPEmbeddingBuilder(Protocol):
    async def __call__(
        self, *, tool_metadata: list[dict[str, str]], server_name: str
    ) -> object: ...


def _bounded_metadata(tools: Sequence[Mapping[str, object]]) -> list[dict[str, str]]:
    admitted: list[dict[str, str]] = []
    remaining = 4096
    for tool in tools[:64]:
        name, description = tool.get("name"), tool.get("description")
        if not isinstance(name, str) or not name or len(name) > 256:
            continue
        excerpt = description[:512] if isinstance(description, str) else ""
        size = len(name.encode("utf-8")) + len(excerpt.encode("utf-8"))
        if size > remaining:
            break
        admitted.append({"name": name, "description": excerpt})
        remaining -= size
    return admitted


@contextmanager
def embedding_attribution(user_id: UUID, session_id: str) -> Iterator[None]:
    """Attribute the embeddings computed inside to the account, then restore the caller's.

    Args:
        user_id: The account that owns the spend.
        session_id: The bounded label of the operation (no content).
    """
    previous = get_embedding_context()
    set_embedding_context(str(user_id), session_id)
    try:
        yield
    finally:
        clear_embedding_context()
        if previous is not None:
            set_embedding_context(
                previous.user_id, previous.session_id, previous.conversation_id, previous.run_id
            )


async def build_connection_embeddings(
    user_id: UUID,
    server_name: str,
    tools: Sequence[Mapping[str, object]],
    builder: MCPEmbeddingBuilder,
) -> dict[str, JsonValue]:
    metadata = _bounded_metadata(tools)
    if not metadata or await spend_blocked(user_id):
        return {}
    await enforce_usage_limit(user_id, layer="mcp_connection_embeddings")
    with embedding_attribution(user_id, f"mcp-connection:{user_id}"):
        return TypeAdapter(dict[str, JsonValue]).validate_python(
            await builder(tool_metadata=metadata, server_name=server_name[:100])
        )
