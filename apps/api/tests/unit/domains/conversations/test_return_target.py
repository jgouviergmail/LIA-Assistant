"""Where an out-of-turn return runs: the act's annex while it lives, else Main (2026-11-14)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.conversation_selection import ConversationSelection
from src.core.conversation_target import ConversationOrigin
from src.domains.conversations import return_target as module
from src.domains.conversations.return_target import ReturnTarget, return_target

pytestmark = pytest.mark.unit


def _db() -> AsyncSession:
    session: AsyncSession = AsyncMock(spec=AsyncSession)
    return session


def _install(monkeypatch: pytest.MonkeyPatch, *, annex: UUID | None, main: UUID) -> dict:
    seen: dict = {"main_created": 0}

    class _Publication:
        def __init__(self, db: object) -> None:
            pass

        async def secondary_origin(self, owner_id: UUID, origin: ConversationOrigin) -> UUID | None:
            seen["asked"] = (owner_id, origin)
            return annex

    class _Conversations:
        async def get_or_create_conversation(
            self, owner_id: UUID, db: object, *, language: str | None
        ) -> SimpleNamespace:
            seen["main_created"] += 1
            seen["language"] = language
            return SimpleNamespace(id=main)

    monkeypatch.setattr(module, "ConversationPublicationRepository", _Publication)
    monkeypatch.setattr(module, "ConversationService", _Conversations)
    return seen


async def test_a_live_annex_is_selected_by_its_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    annex, main = uuid4(), uuid4()
    seen = _install(monkeypatch, annex=annex, main=main)
    origin = ConversationOrigin(annex, 4)

    target = await return_target(_db(), uuid4(), origin, language="fr")

    assert target == ReturnTarget(annex, 4)
    assert target.selection == ConversationSelection(conversation_id=annex, conversation_revision=4)
    assert seen["main_created"] == 0


async def test_a_retired_annex_returns_to_main_by_omission(monkeypatch: pytest.MonkeyPatch) -> None:
    main = uuid4()
    seen = _install(monkeypatch, annex=None, main=main)

    target = await return_target(_db(), uuid4(), ConversationOrigin(uuid4(), 1), language="de")

    assert target == ReturnTarget(main, None)
    assert target.selection == ConversationSelection()
    assert seen["language"] == "de"


async def test_an_act_begun_nowhere_returns_to_main(monkeypatch: pytest.MonkeyPatch) -> None:
    main = uuid4()
    seen = _install(monkeypatch, annex=uuid4(), main=main)

    target = await return_target(_db(), uuid4(), None, language="fr")

    assert target == ReturnTarget(main, None)
    assert "asked" not in seen


async def test_a_run_begun_nowhere_reads_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """A scheduled tick has no origin: no lookup, Main by omission."""
    seen = _install(monkeypatch, annex=None, main=uuid4())

    assert await module.origin_target(_db(), uuid4(), None, language="fr") is None
    assert "asked" not in seen and seen["main_created"] == 0


async def test_a_run_asked_in_an_annex_answers_there(monkeypatch: pytest.MonkeyPatch) -> None:
    annex = uuid4()
    _install(monkeypatch, annex=annex, main=uuid4())

    target = await module.origin_target(_db(), uuid4(), ConversationOrigin(annex, 4), language="fr")

    assert target == ReturnTarget(annex, 4)
    assert module.selection_of(target) == ConversationSelection(
        conversation_id=annex, conversation_revision=4
    )
    assert module.annex_of(target) == annex


def test_main_is_selected_by_omission_and_opens_no_annex() -> None:
    main = ReturnTarget(uuid4(), None)

    for target in (None, main):
        assert module.selection_of(target) == ConversationSelection()
        assert module.annex_of(target) is None


async def test_the_browser_s_annex_becomes_the_act_s_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    annex = uuid4()

    async def _origin(db: object, owner_id: UUID, conversation_id: UUID | None):
        return ConversationOrigin(annex, 2) if conversation_id == annex else None

    monkeypatch.setattr(module, "annex_origin", _origin)

    assert await module.annex_origin_columns(_db(), uuid4(), annex) == {
        "origin_conversation_id": annex,
        "origin_conversation_revision": 2,
    }
    assert await module.annex_origin_columns(_db(), uuid4(), None) == {
        "origin_conversation_id": None,
        "origin_conversation_revision": None,
    }
