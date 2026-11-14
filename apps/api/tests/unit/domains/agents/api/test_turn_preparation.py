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

from src.core.conversation_target import ConversationKind
from src.domains.agents.api import turn_preparation
from src.domains.agents.api.turn_preparation import TurnStateRequest, prepare_turn_state
from tests.fixtures.conversation_cases import conversation_target

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
    values["target"] = conversation_target(
        values["user_id"],
        values.pop("conversation_id"),
        kind=values.pop("kind", ConversationKind.MAIN),
    )
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


# ---------------------------------------------------------------------------
# An annex waiting for its title takes it from the first request (ADR-378
# amendment 2026-11-12)
# ---------------------------------------------------------------------------


@pytest.fixture
def titled(monkeypatch: pytest.MonkeyPatch) -> list[tuple[uuid.UUID, str]]:
    """What the turn offered as a title, in place of the catalogue's own door."""
    offered: list[tuple[uuid.UUID, str]] = []

    async def offer(conversation_id: uuid.UUID, message: str) -> None:
        offered.append((conversation_id, message))

    monkeypatch.setattr(turn_preparation, "title_waiting_discussion", offer)
    return offered


async def test_a_request_typed_in_an_annex_offers_it_its_title(
    noted: list[uuid.UUID | None], titled: list[tuple[uuid.UUID, str]]
) -> None:
    request = _request(kind=ConversationKind.SECONDARY)

    await _prepare(request, _Conversations())

    assert titled == [(request.conversation_id, "bonjour")]


async def test_the_persons_spoken_words_name_the_discussion_not_their_restatement(
    noted: list[uuid.UUID | None], titled: list[tuple[uuid.UUID, str]]
) -> None:
    """A Live delegation: ``user_message`` is the voice model's restatement."""
    request = _request(kind=ConversationKind.SECONDARY, spoken_text="mes propres mots")

    await _prepare(request, _Conversations())

    assert titled == [(request.conversation_id, "mes propres mots")]


@pytest.mark.parametrize(
    "overrides",
    [
        # Main has a fixed title.
        {"kind": ConversationKind.MAIN},
        # An answer to a question is not a subject.
        {"kind": ConversationKind.SECONDARY, "is_hitl_resumption": True},
        # Nobody typed a routine's instruction.
        {"kind": ConversationKind.SECONDARY, "is_automated_source": True},
        # A retry archived nothing: its first attempt already offered the title.
        {"kind": ConversationKind.SECONDARY, "archive_user_message": False},
    ],
    ids=["main", "answer to a question", "automated run", "retry"],
)
async def test_what_never_names_a_discussion(
    overrides: dict[str, Any],
    noted: list[uuid.UUID | None],
    titled: list[tuple[uuid.UUID, str]],
) -> None:
    await _prepare(_request(**overrides), _Conversations())

    assert titled == []


async def test_a_request_that_could_not_be_archived_names_nothing(
    noted: list[uuid.UUID | None], titled: list[tuple[uuid.UUID, str]]
) -> None:
    """The title would name a message the discussion does not hold."""

    class _Broken(_Conversations):
        async def archive_message(self, *args: Any, **kwargs: Any) -> SimpleNamespace:
            raise RuntimeError("database gone")

    prepared = await _prepare(_request(kind=ConversationKind.SECONDARY), _Broken())

    assert prepared.archived_user_msg_id is None
    assert titled == []
