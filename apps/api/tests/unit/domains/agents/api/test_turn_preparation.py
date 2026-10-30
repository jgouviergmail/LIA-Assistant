"""``prepare_turn_state``: the state, its attachments and the archived request of one turn.

The order against the MCP preparation is pinned in
``tests/agents/test_turn_preparation_order.py``; these tests pin what the
extracted step itself guarantees — a retry never archives twice, uploads off
means no attachment read, and the archived row lists what the turn attached.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any

import pytest

from src.domains.agents.api import turn_preparation
from src.domains.agents.api.turn_preparation import TurnStateRequest, prepare_turn_state

pytestmark = pytest.mark.unit

ROW_ID = uuid.uuid4()
ATTACHMENT_ID = uuid.uuid4()


class _Orchestration:
    def __init__(self) -> None:
        self.state: dict[str, Any] = {"messages": [], "metadata": {}}

    async def load_or_create_state(self, **kwargs: Any) -> dict[str, Any]:
        return self.state


class _Conversations:
    def __init__(self) -> None:
        self.archived: list[tuple[str, str, dict[str, Any], dict[str, Any]]] = []

    async def archive_message(
        self,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        metadata: dict,
        db: Any,
        **stt: Any,
    ) -> SimpleNamespace:
        self.archived.append((role, content, metadata, stt))
        return SimpleNamespace(id=ROW_ID)


def _request(**overrides: Any) -> TurnStateRequest:
    values: dict[str, Any] = {
        "conversation_id": uuid.uuid4(),
        "user_message": "bonjour",
        "user_id": uuid.uuid4(),
        "session_id": "sess",
        "run_id": "run-1",
        "user_timezone": "UTC",
        "user_language": "fr",
        "oauth_scopes": [],
        "personality_instruction": None,
        "is_hitl_resumption": False,
        "user_display_name": None,
        "hitl_decision": None,
        "attachment_ids": None,
        "auto_approve_plan": False,
        "archive_user_message": True,
        "stt_kwargs": {"stt_provider": "remote"},
    }
    values.update(overrides)
    return TurnStateRequest(**values)


@pytest.fixture
def noted(monkeypatch: pytest.MonkeyPatch) -> list[uuid.UUID | None]:
    seen: list[uuid.UUID | None] = []
    monkeypatch.setattr(turn_preparation, "note_request_message", seen.append)

    @asynccontextmanager
    async def fake_db_context() -> AsyncIterator[object]:
        yield object()

    monkeypatch.setattr("src.infrastructure.database.get_db_context", fake_db_context)
    return seen


async def _prepare(request: TurnStateRequest, conversations: _Conversations) -> Any:
    return await prepare_turn_state(
        request,
        graph=object(),
        db=object(),  # type: ignore[arg-type]
        orchestration_service=_Orchestration(),  # type: ignore[arg-type]
        conv_service=conversations,  # type: ignore[arg-type]
    )


async def test_request_archived_with_its_attachments_and_noted(
    noted: list[uuid.UUID | None], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(turn_preparation.settings, "attachments_enabled", True, raising=False)

    async def inject(*, state: dict[str, Any], **_: Any) -> None:
        state["metadata"]["current_turn_attachments"] = [
            {
                "id": str(ATTACHMENT_ID),
                "original_filename": "plan.pdf",
                "mime_type": "application/pdf",
                "file_size": 12,
                "content_type": "document",
            }
        ]

    monkeypatch.setattr(turn_preparation, "inject_attachments_into_state", inject)
    conversations = _Conversations()

    prepared = await _prepare(
        _request(attachment_ids=[ATTACHMENT_ID], auto_approve_plan=True), conversations
    )

    assert prepared.archived_user_msg_id == ROW_ID
    assert noted == [ROW_ID]
    role, content, metadata, stt = conversations.archived[0]
    assert (role, content) == ("user", "bonjour")
    assert metadata["run_id"] == "run-1"
    assert metadata["attachments"][0]["filename"] == "plan.pdf"
    assert stt == {"stt_provider": "remote"}
    assert prepared.state["plan_approved"] is True


async def test_retry_never_archives_the_request_twice(noted: list[uuid.UUID | None]) -> None:
    """A scheduled-action retry: attempt 1 already archived the request."""
    conversations = _Conversations()

    prepared = await _prepare(_request(archive_user_message=False), conversations)

    assert prepared.archived_user_msg_id is None
    assert conversations.archived == []
    assert noted == []


async def test_uploads_off_reads_no_attachment(
    noted: list[uuid.UUID | None], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(turn_preparation.settings, "attachments_enabled", False, raising=False)
    called: list[bool] = []

    async def inject(**_: Any) -> None:
        called.append(True)

    monkeypatch.setattr(turn_preparation, "inject_attachments_into_state", inject)

    prepared = await _prepare(_request(attachment_ids=[ATTACHMENT_ID]), _Conversations())

    assert called == []
    assert "plan_approved" not in prepared.state
