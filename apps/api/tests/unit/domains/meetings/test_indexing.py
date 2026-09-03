"""The « Réunions » knowledge space is found by ROLE and created once (ADR-258)."""

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError

from src.core.constants import MEETINGS_SPACE_KIND
from src.domains.meetings import indexing
from src.domains.meetings.indexing import _document_path, ensure_meetings_space

pytestmark = pytest.mark.unit


def test_document_path_stays_inside_the_storage_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(indexing.settings, "rag_spaces_storage_path", str(tmp_path))
    user_id, space_id = uuid.uuid4(), uuid.uuid4()
    path = _document_path(user_id, space_id, "abc.md")
    assert path == (tmp_path / str(user_id) / str(space_id) / "abc.md").resolve()
    with pytest.raises(RuntimeError):
        _document_path(user_id, space_id, "../../escape.md")


def _repo(existing: Any = None) -> AsyncMock:
    repo = AsyncMock()
    repo.get_by_kind_for_user.return_value = existing
    return repo


async def test_an_existing_space_is_returned_without_creating_anything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    space = SimpleNamespace(id=uuid.uuid4(), kind=MEETINGS_SPACE_KIND)
    repo = _repo(space)
    monkeypatch.setattr(indexing, "RAGSpaceRepository", lambda db: repo)
    assert await ensure_meetings_space(AsyncMock(), uuid.uuid4(), "fr") is space
    repo.create.assert_not_awaited()


async def test_the_space_is_created_in_the_users_language_with_the_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = SimpleNamespace(id=uuid.uuid4())
    repo = _repo(None)
    repo.create.return_value = created
    monkeypatch.setattr(indexing, "RAGSpaceRepository", lambda db: repo)
    db = AsyncMock()
    assert await ensure_meetings_space(db, uuid.uuid4(), "fr") is created
    payload = repo.create.call_args.args[0]
    assert payload["name"] == "Réunions" and payload["kind"] == MEETINGS_SPACE_KIND
    assert payload["is_active"] is True and payload["is_system"] is False
    db.commit.assert_awaited_once()


async def test_a_lost_race_on_the_kind_returns_the_winners_space(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    winner = SimpleNamespace(id=uuid.uuid4())
    repo = AsyncMock()
    repo.get_by_kind_for_user.side_effect = [None, winner]
    repo.create.side_effect = IntegrityError("insert", {}, Exception("dup"))
    monkeypatch.setattr(indexing, "RAGSpaceRepository", lambda db: repo)
    db = AsyncMock()
    assert await ensure_meetings_space(db, uuid.uuid4(), "en") is winner
    db.rollback.assert_awaited_once()


async def test_a_name_clash_with_a_hand_made_space_is_suffixed_never_adopted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = SimpleNamespace(id=uuid.uuid4())
    repo = AsyncMock()
    repo.get_by_kind_for_user.return_value = None
    repo.create.side_effect = [IntegrityError("insert", {}, Exception("name")), created]
    monkeypatch.setattr(indexing, "RAGSpaceRepository", lambda db: repo)
    assert await ensure_meetings_space(AsyncMock(), uuid.uuid4(), "en") is created
    names = [call.args[0]["name"] for call in repo.create.call_args_list]
    assert names == ["Meetings", "Meetings (2)"]
