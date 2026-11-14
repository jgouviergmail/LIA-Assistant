"""Real record writers recheck their source after paid model/embedding work."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.core.run_authority import run_authority_scope
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.services import memory_extractor
from src.domains.conversations.lifecycle import ConversationLifecycle
from src.domains.interests.models import InterestCategory, UserInterest
from src.domains.interests.schemas import ExtractedInterest
from src.domains.interests.services import extraction_service as interests
from src.domains.journals import extraction_service as journals
from src.domains.journals.models import JournalEntry
from src.domains.memories.models import Memory
from src.domains.users.models import User
from tests.fixtures.learning_sources import Sources, source_authority
from tests.fixtures.learning_sources import sources as sources
from tests.helpers.runtime_context import installed_runtime_context

pytestmark = pytest.mark.integration
Family = Literal["memory", "journal", "interests"]
Change = Literal["none", "model_reset", "embedding_reset", "other_reset", "consent"]


@pytest.mark.parametrize("family", ["memory", "journal", "interests"])
@pytest.mark.parametrize(
    "change", ["none", "model_reset", "embedding_reset", "other_reset", "consent"]
)
async def test_account_record_write_keeps_spend_but_never_restores_a_retired_source(
    async_engine: AsyncEngine,
    sources: Sources,
    monkeypatch: pytest.MonkeyPatch,
    family: Family,
    change: Change,
) -> None:
    target = sources.annex

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            yield db
            await db.commit()

    async def change_source(phase: str) -> None:
        if (phase == "model" and change == "embedding_reset") or (
            phase == "embedding" and change != "embedding_reset"
        ):
            return
        async with AsyncSession(async_engine) as db:
            if change == "consent":
                await db.execute(
                    update(User).where(User.id == target.owner_id).values(extraction_revision=1)
                )
                await db.commit()
            elif change in {"model_reset", "embedding_reset", "other_reset"}:
                reset = sources.main if change == "other_reset" else target
                await ConversationLifecycle(db).request_reset(
                    reset.owner_id, reset.id, operation_id=uuid4(), expected_revision=0
                )

    proposal = (
        {
            "action": "create",
            "content": "I prefer evidence before assertions.",
            "category": "preference",
        }
        if family == "memory"
        else {
            "action": "create",
            "theme": "learnings",
            "title": "Explain with evidence",
            "content": "WHEN explaining a change -> DO show the evidence BECAUSE the user verifies it.",
        }
    )

    async def model(*args: object, **kwargs: object) -> AIMessage:
        await change_source("model")
        return AIMessage(
            content=json.dumps([proposal]),
            usage_metadata={"input_tokens": 11, "output_tokens": 7, "total_tokens": 18},
        )

    async def analyze(*args: object, **kwargs: object) -> interests.InterestAnalysisResult:
        await change_source("model")
        return interests.InterestAnalysisResult(
            analyzed=True,
            extracted_interests=[
                ExtractedInterest(
                    action="create",
                    topic="Fictional astronomy",
                    category=InterestCategory.SCIENCE,
                    confidence=0.95,
                )
            ],
            llm_input_tokens=11,
            llm_output_tokens=7,
        )

    async def dual_embedding(*args: object, **kwargs: object) -> tuple[None, None]:
        await change_source("embedding")
        return None, None

    async def interest_embedding(*args: object, **kwargs: object) -> None:
        await change_source("embedding")

    for path in (
        "src.infrastructure.database.get_db_context",
        "src.infrastructure.database.session.get_db_context",
        "src.domains.agents.services.memory_embedding_preparation.get_db_context",
        "src.domains.interests.services.extraction_service.get_db_context",
    ):
        monkeypatch.setattr(path, session)
    for module in (memory_extractor, journals):
        monkeypatch.setattr(module, "invoke_with_instrumentation", model)
        monkeypatch.setattr(module, "get_llm", lambda *_: FakeListChatModel(responses=[]))
        monkeypatch.setattr(module, "is_capability_enabled", AsyncMock(return_value=True))
        monkeypatch.setattr(module, "_maybe_build_health_context", AsyncMock(return_value=""))
    monkeypatch.setattr(journals, "_maybe_build_inner_state_section", AsyncMock(return_value=""))
    monkeypatch.setattr(journals, "_update_user_last_cost", AsyncMock())
    for flag in ("journals_enabled", "journal_extraction_enabled"):
        monkeypatch.setattr(settings, flag, True)
    monkeypatch.setattr(settings, "journal_extraction_min_messages", 1)
    monkeypatch.setattr(interests, "_analyze_interests_core", analyze)
    monkeypatch.setattr("src.domains.memories.service._generate_dual_embeddings", dual_embedding)
    monkeypatch.setattr("src.domains.journals.service._generate_dual_embeddings", dual_embedding)
    monkeypatch.setattr(
        "src.domains.interests.helpers.generate_interest_embedding", interest_embedding
    )
    monkeypatch.setattr(
        "src.domains.interests.services.extraction_storage.enforce_usage_limit", AsyncMock()
    )
    monkeypatch.setattr(
        "src.domains.interests.services.extraction_storage.is_capability_enabled",
        AsyncMock(return_value=True),
    )
    paid = AsyncMock()
    billing = {
        "memory": (memory_extractor, "_persist_memory_tokens"),
        "journal": (journals, "_persist_journal_tokens"),
        "interests": (interests, "_persist_interest_tokens"),
    }
    module, name = billing[family]
    monkeypatch.setattr(module, name, paid)
    context = LiaRuntimeContext.for_conversation(
        target=target, extraction_revision=0, memory_enabled=True, journals_enabled=True
    )
    args: tuple[str, list[BaseMessage], str] = (
        str(target.owner_id),
        [HumanMessage(content="Remember this fictional preference.")],
        str(target.runtime_id),
    )
    with run_authority_scope(source_authority(target)), installed_runtime_context(context):
        with run_authority_scope(None):
            if family == "memory":
                count = await memory_extractor.extract_memories_background(
                    *args,
                    conversation_id=str(target.id),
                    parent_run_id=str(uuid4()),
                    query_embedding=[],
                    user_timezone=None,
                )
            elif family == "journal":
                count = await journals.extract_journal_entry_background(
                    *args,
                    conversation_id=str(target.id),
                    parent_run_id=str(uuid4()),
                    query_embedding=[],
                    user_timezone=None,
                )
            else:
                count = await interests.extract_interests_background(
                    *args,
                    conversation_id=str(target.id),
                    parent_run_id=str(uuid4()),
                    user_timezone=None,
                )
    paid.assert_awaited_once()
    async with AsyncSession(async_engine) as db:
        model_type = {"memory": Memory, "journal": JournalEntry, "interests": UserInterest}[family]
        rows = await db.scalar(
            select(func.count())
            .select_from(model_type)
            .where(model_type.user_id == target.owner_id)
        )
    assert count == rows == int(change in {"none", "other_reset"})
