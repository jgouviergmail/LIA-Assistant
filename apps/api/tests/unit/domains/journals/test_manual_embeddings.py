"""Quota checks occur at each source call; scoped cost attribution always unwinds."""

from uuid import uuid4

import pytest

from src.domains.journals import manual_embeddings
from src.infrastructure.llm.embedding_context import (
    clear_embedding_context,
    get_embedding_context,
    set_embedding_context,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("scenario", ["complete", "second_quota", "provider_failure", "no_hints"])
async def test_manual_embedding_calls_are_guarded_and_restore_parent_context(
    monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    owner, command = uuid4(), uuid4()
    set_embedding_context("parent-owner", "parent-session", "parent-conversation", "parent-run")
    previous = get_embedding_context()
    calls: list[str] = []
    quotas: list[str] = []

    async def guard():
        assert get_embedding_context().user_id == str(owner)

    async def quota(actor_id, *, layer):
        assert actor_id == owner and layer == "journal_management"
        quotas.append(layer)
        if scenario == "second_quota" and len(quotas) == 2:
            raise RuntimeError("quota withdrew")

    async def embed(text: str):
        context = get_embedding_context()
        assert context is not None and context.run_id == str(command)
        calls.append(text)
        if scenario == "provider_failure":
            raise RuntimeError("transport stopped")
        return None

    monkeypatch.setattr(manual_embeddings, "enforce_usage_limit", quota)
    monkeypatch.setattr(manual_embeddings, "_generate_document_embedding", embed)
    try:
        pending = manual_embeddings.prepare_manual_journal_embeddings(
            owner, command, "Title", "Content", None if scenario == "no_hints" else ["Hint"], guard
        )
        if scenario in {"second_quota", "provider_failure"}:
            with pytest.raises(RuntimeError):
                await pending
        else:
            assert await pending == (None, None)
        assert calls == (
            ["Title. Content.", "Hint"] if scenario == "complete" else ["Title. Content."]
        )
        assert len(quotas) == (2 if scenario in {"complete", "second_quota"} else 1)
        assert get_embedding_context() == previous
    finally:
        clear_embedding_context()
