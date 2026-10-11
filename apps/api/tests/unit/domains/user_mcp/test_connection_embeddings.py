"""Optional discovery embeddings must respect account spend and attribute usage."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domains.user_mcp.connection_embeddings import build_connection_embeddings
from src.infrastructure.llm.embedding_context import (
    clear_embedding_context,
    get_embedding_context,
    set_embedding_context,
)


@pytest.mark.parametrize("blocked", [False, True])
async def test_embeddings_obey_spend_and_restore_context(monkeypatch, blocked: bool):
    owner = uuid4()
    seen = []

    async def compute(**kwargs):
        context = get_embedding_context()
        assert context is not None and context.user_id == str(owner)
        seen.append(kwargs)
        return {"read": {"description": [0.2, 0.5]}}

    monkeypatch.setattr(
        "src.domains.user_mcp.connection_embeddings.spend_blocked", AsyncMock(return_value=blocked)
    )
    limit = AsyncMock()
    monkeypatch.setattr("src.domains.user_mcp.connection_embeddings.enforce_usage_limit", limit)
    set_embedding_context(str(uuid4()), "previous-context")
    previous = get_embedding_context()
    try:
        result = await build_connection_embeddings(
            owner,
            "owned",
            [{"name": "read", "description": "x" * 100_000, "input_schema": {"private": "schema"}}],
            compute,
        )
        assert get_embedding_context() == previous
        if blocked:
            assert not result and not seen and not limit.called
        else:
            assert result and len(seen) == 1
            assert len(seen[0]["tool_metadata"][0]["description"]) == 512
            assert "input_schema" not in seen[0]["tool_metadata"][0]
            limit.assert_awaited_once_with(owner, layer="mcp_connection_embeddings")
    finally:
        clear_embedding_context()


async def test_usage_refusal_precedes_embedding_provider(monkeypatch):
    monkeypatch.setattr(
        "src.domains.user_mcp.connection_embeddings.spend_blocked", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(
        "src.domains.user_mcp.connection_embeddings.enforce_usage_limit",
        AsyncMock(side_effect=RuntimeError("quota refused")),
    )
    compute = AsyncMock()
    with pytest.raises(RuntimeError, match="quota refused"):
        await build_connection_embeddings(
            uuid4(), "owned", [{"name": "read", "description": "Read"}], compute
        )
    compute.assert_not_called()


async def test_provider_failure_restores_previous_context_and_leaves_no_retry(monkeypatch):
    monkeypatch.setattr(
        "src.domains.user_mcp.connection_embeddings.spend_blocked", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(
        "src.domains.user_mcp.connection_embeddings.enforce_usage_limit", AsyncMock()
    )
    compute = AsyncMock(side_effect=RuntimeError("provider refused"))
    set_embedding_context(str(uuid4()), "previous-context")
    previous = get_embedding_context()
    try:
        with pytest.raises(RuntimeError, match="provider refused"):
            await build_connection_embeddings(
                uuid4(), "owned", [{"name": "read", "description": "Read"}], compute
            )
        assert get_embedding_context() == previous
        compute.assert_awaited_once()
    finally:
        clear_embedding_context()
