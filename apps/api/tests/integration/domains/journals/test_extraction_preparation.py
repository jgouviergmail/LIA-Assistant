"""A paused embedding provider must not hold the account's write lock."""

import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.domains.journals import extraction_service as extraction
from src.domains.journals.models import JournalEntry
from src.domains.journals.service import JournalService
from src.domains.users.models import User
from src.infrastructure.llm.embedding_context import get_embedding_context

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.parametrize("mutation", ["unchanged", "opt_out", "edit", "title_edit", "hints_edit"])
async def test_embedding_preparation_leaves_owner_available_and_refuses_stale_work(
    async_engine, monkeypatch, mutation
):
    maker = async_sessionmaker(async_engine, expire_on_commit=False)

    @asynccontextmanager
    async def db_context():
        async with maker() as db:
            yield db

    async with maker() as db:
        user = User(
            email=f"embedding-barrier-{uuid4()}@example.test",
            hashed_password="x",
            journals_enabled=True,
            is_active=True,
        )
        db.add(user)
        await db.flush()
        entry = await JournalService(db).create_entry(
            user.id, "learnings", "Rule", "Original rule.", precomputed_embeddings=(None, None)
        )
        await db.commit()
        owner_id, entry_id = user.id, entry.id

    started, release = asyncio.Event(), asyncio.Event()
    session_id, run_id = str(uuid4()), str(uuid4())

    async def embedding_provider(*_):
        context = get_embedding_context()
        assert context is not None and context.user_id == str(owner_id)
        assert context.session_id == session_id and context.run_id == run_id
        started.set()
        await release.wait()
        return None, None

    monkeypatch.setattr("src.infrastructure.database.get_db_context", db_context)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", db_context)
    monkeypatch.setattr(
        "src.domains.journals.service._generate_dual_embeddings", embedding_provider
    )
    monkeypatch.setattr(extraction.settings, "journals_enabled", True)
    monkeypatch.setattr(extraction.settings, "journal_extraction_enabled", True)
    monkeypatch.setattr(extraction.settings, "journal_extraction_min_messages", 1)
    monkeypatch.setattr(extraction, "is_capability_enabled", AsyncMock(return_value=True))
    monkeypatch.setattr(extraction, "runtime_context_if_running", lambda: None)
    monkeypatch.setattr(
        extraction, "get_llm_config_for_agent", lambda *_: SimpleNamespace(model="offline")
    )
    monkeypatch.setattr(extraction, "get_llm", lambda *_: SimpleNamespace(model_name="offline"))
    monkeypatch.setattr(extraction, "start_extraction_observation", MagicMock())
    for name in ("_persist_journal_tokens", "_update_user_last_cost"):
        monkeypatch.setattr(extraction, name, AsyncMock())
    for name in ("_maybe_build_health_context", "_maybe_build_inner_state_section"):
        monkeypatch.setattr(extraction, name, AsyncMock(return_value=""))
    proposed = "WHEN corrected -> DO preserve the condition BECAUSE scope is explicit."
    monkeypatch.setattr(
        extraction,
        "invoke_with_instrumentation",
        AsyncMock(
            return_value=AIMessage(
                content=json.dumps(
                    [{"action": "update", "entry_id": str(entry_id), "content": proposed}]
                )
            )
        ),
    )
    task = asyncio.create_task(
        extraction.extract_journal_entry_background.__wrapped__(
            str(owner_id),
            [HumanMessage(content="Keep the condition.", id="source-message")],
            session_id,
            parent_run_id=run_id,
        )
    )
    try:
        await asyncio.wait_for(started.wait(), timeout=3)
        async with maker() as db:
            await db.execute(text("SET LOCAL lock_timeout = '200ms'"))
            locked = await db.scalar(select(User).where(User.id == owner_id).with_for_update())
            assert locked is not None, "The real account lock is obtainable while embeddings wait"
            if mutation == "opt_out":
                locked.journals_enabled = False
                locked.extraction_revision += 1
            elif mutation == "edit":
                current = await db.get(JournalEntry, entry_id)
                await JournalService(db).update_entry(
                    current,
                    content="Manual correction wins.",
                    expected_revision=1,
                    precomputed_embeddings=(None, None),
                )
            elif mutation in ("title_edit", "hints_edit"):
                current = await db.get(JournalEntry, entry_id)
                fields = (
                    {"title": "Manual title"}
                    if mutation == "title_edit"
                    else {"search_hints": ["manual hint"]}
                )
                await JournalService(db).update_entry(
                    current, expected_revision=1, precomputed_embeddings=(None, None), **fields
                )
                assert current.revision == 1  # Metadata edits retain proposition validation.
            await db.commit()
        release.set()
        assert await asyncio.wait_for(task, timeout=5) == (1 if mutation == "unchanged" else 0)
        async with maker() as db:
            current = await db.get(JournalEntry, entry_id)
            expected = {
                "unchanged": proposed,
                "opt_out": "Original rule.",
                "edit": "Manual correction wins.",
                "title_edit": "Original rule.",
                "hints_edit": "Original rule.",
            }
            assert current.content == expected[mutation]
            if mutation == "title_edit":
                assert current.title == "Manual title"
            if mutation == "hints_edit":
                assert current.search_hints == ["manual hint"]
    finally:
        release.set()
        if not task.done():
            await asyncio.wait_for(task, timeout=5)
        async with maker() as db:
            await db.execute(delete(User).where(User.id == owner_id))
            await db.commit()
