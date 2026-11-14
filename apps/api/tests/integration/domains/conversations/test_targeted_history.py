"""Authenticated history stays on one discussion and pages every timestamp collision."""

import base64
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection
from psycopg.rows import DictRow
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import CONVERSATION_HISTORY_CURSOR_MAX_LENGTH
from src.core.conversation_target import ConversationKind
from src.core.session_dependencies import get_current_active_session
from src.domains.agents.services.token_counter_service import get_token_counter
from src.domains.chat.models import MessageTokenSummary
from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.users.models import User
from src.main import app

pytestmark = pytest.mark.integration
_URL = "/api/v1/conversations/me/messages"
_STAMP = datetime(2026, 11, 10, 12, tzinfo=UTC)


@dataclass(frozen=True)
class History:
    """Real rows owned by the test's external transaction."""

    owner: User
    main: Conversation
    annex: Conversation
    visible: list[UUID]

    @property
    def selection(self) -> dict[str, str | int]:
        return {"conversation_id": str(self.annex.id), "conversation_revision": self.annex.revision}


@pytest.fixture
async def history(async_session: AsyncSession) -> History:
    owner = User(email=f"history-{uuid4()}@example.com", hashed_password="unused", is_active=True)
    async_session.add(owner)
    await async_session.flush()
    main = Conversation(
        id=owner.id,
        user_id=owner.id,
        title="Main",
        kind=ConversationKind.MAIN,
        revision=0,
        runtime_id=uuid4(),
    )
    annex = Conversation(
        id=uuid4(),
        user_id=owner.id,
        title="Annex",
        kind=ConversationKind.SECONDARY,
        revision=3,
        runtime_id=uuid4(),
    )
    async_session.add_all([main, annex])
    await async_session.flush()
    identifiers = [uuid4() for _ in range(9)]
    async_session.add_all(
        [
            ConversationMessage(
                id=key,
                conversation_id=annex.id,
                role="user",
                content=f"Visible {number}",
                created_at=_STAMP,
            )
            for number, key in enumerate(identifiers)
        ]
    )
    async_session.add_all(
        [
            ConversationMessage(
                conversation_id=main.id, role="user", content="Main only", created_at=_STAMP
            ),
            ConversationMessage(
                conversation_id=annex.id,
                role="assistant",
                content="\t\u3000\x1c",
                created_at=_STAMP + timedelta(minutes=2),
            ),
            ConversationMessage(
                conversation_id=annex.id,
                role="assistant",
                content="",
                created_at=_STAMP + timedelta(minutes=1),
            ),
            ConversationMessage(
                conversation_id=annex.id,
                role="assistant",
                content="Hidden routine",
                hidden=True,
                created_at=_STAMP + timedelta(minutes=3),
            ),
        ]
    )
    await async_session.flush()
    return History(owner, main, annex, sorted(identifiers, reverse=True))


@pytest.fixture
async def history_client(async_client: AsyncClient, history: History) -> AsyncIterator[AsyncClient]:
    async def authenticated() -> User:
        return history.owner

    app.dependency_overrides[get_current_active_session] = authenticated
    try:
        yield async_client
    finally:
        app.dependency_overrides.pop(get_current_active_session, None)


async def test_an_explicit_annex_never_reads_main(
    history_client: AsyncClient, history: History
) -> None:
    response = await history_client.get(_URL, params={**history.selection, "limit": 2})
    assert response.status_code == 200
    data = response.json()
    assert data["conversation_id"] == str(history.annex.id)
    assert data["conversation_revision"] == history.annex.revision
    assert len(data["messages"]) == 2
    assert all(message["content"].startswith("Visible") for message in data["messages"])
    legacy = await history_client.get(_URL)
    assert legacy.status_code == 200
    assert [message["content"] for message in legacy.json()["messages"]] == ["Main only"]


async def test_equal_timestamps_are_paged_once_without_hidden_or_empty_answers(
    history_client: AsyncClient,
    history: History,
) -> None:
    seen: list[str] = []
    params: dict[str, str | int] = {**history.selection, "limit": 2}
    for _ in range(len(history.visible)):
        response = await history_client.get(_URL, params=params)
        assert response.status_code == 200
        data = response.json()
        seen.extend(message["id"] for message in data["messages"])
        if not data["has_more"]:
            assert data["next_page_cursor"] is None
            break
        assert len(data["messages"]) == 2
        assert isinstance(data["next_page_cursor"], str)
        params["cursor"] = data["next_page_cursor"]
    else:
        pytest.fail("History pagination made no bounded progress")
    assert seen == [str(key) for key in history.visible]


@pytest.mark.parametrize(
    "change, status",
    [
        ({"conversation_revision": 2}, 409),
        ({"conversation_id": str(uuid4())}, 404),
    ],
)
async def test_an_invalid_target_never_falls_back_to_main(
    history_client: AsyncClient,
    history: History,
    change: dict[str, str | int],
    status: int,
) -> None:
    response = await history_client.get(_URL, params={**history.selection, **change})
    assert response.status_code == status


async def test_the_legacy_timestamp_cut_remains_strict(
    history_client: AsyncClient,
    history: History,
) -> None:
    response = await history_client.get(
        _URL, params={**history.selection, "before": _STAMP.isoformat()}
    )
    assert response.status_code == 200
    assert response.json()["messages"] == []


@pytest.mark.parametrize(
    "cursor, status",
    [
        ("", 422),
        ("%%%", 400),
        ("é", 400),
        ("e30", 400),
        ("bnVsbA", 400),
        ("W10", 400),
        ("a" * (CONVERSATION_HISTORY_CURSOR_MAX_LENGTH + 1), 422),
    ],
)
async def test_a_damaged_cursor_is_a_client_error(
    history_client: AsyncClient,
    history: History,
    cursor: str,
    status: int,
) -> None:
    response = await history_client.get(_URL, params={**history.selection, "cursor": cursor})
    assert response.status_code == status


@pytest.mark.parametrize(
    "change",
    [
        {"version": 2},
        {"version": True},
        {"version": "1"},
        {"conversation_revision": -1},
        {"conversation_revision": True},
        {"conversation_revision": "3"},
        {"conversation_revision": 2},
        {"conversation_id": str(uuid4())},
        {"message_id": "not-a-uuid"},
        {"at": "2026-11-10T12:00:00"},
        {"extra": "field"},
    ],
)
async def test_a_cursor_cannot_change_target_or_its_typed_contract(
    history_client: AsyncClient,
    history: History,
    change: dict[str, object],
) -> None:
    first = (await history_client.get(_URL, params={**history.selection, "limit": 1})).json()
    raw = first["next_page_cursor"]
    data = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    cursor = base64.urlsafe_b64encode(json.dumps({**data, **change}).encode()).decode()
    response = await history_client.get(_URL, params={**history.selection, "cursor": cursor})
    assert response.status_code == 400


async def test_an_existing_foreign_discussion_is_hidden(
    async_session: AsyncSession,
    history_client: AsyncClient,
) -> None:
    other = User(
        email=f"foreign-history-{uuid4()}@example.test", hashed_password="unused", is_active=True
    )
    async_session.add(other)
    await async_session.flush()
    foreign = Conversation(
        id=other.id, user_id=other.id, title="Other Main", kind=ConversationKind.MAIN
    )
    async_session.add(foreign)
    await async_session.flush()
    async_session.add(
        ConversationMessage(
            conversation_id=foreign.id, role="user", content="Private other account"
        )
    )
    await async_session.flush()
    response = await history_client.get(
        _URL, params={"conversation_id": str(foreign.id), "conversation_revision": 0}
    )
    assert response.status_code == 404
    assert "Private" not in response.text and "Other Main" not in response.text


async def test_a_cursor_never_silently_combines_two_paging_modes(
    history_client: AsyncClient,
    history: History,
) -> None:
    first = (await history_client.get(_URL, params={**history.selection, "limit": 1})).json()
    response = await history_client.get(
        _URL,
        params={
            **history.selection,
            "cursor": first["next_page_cursor"],
            "before": _STAMP.isoformat(),
        },
    )
    assert response.status_code == 400


async def test_a_run_is_billed_on_its_newest_answer_across_pages(
    async_session: AsyncSession,
    history_client: AsyncClient,
    history: History,
) -> None:
    run_id = str(uuid4())
    keys = sorted([uuid4(), uuid4()])
    async_session.add_all(
        [
            ConversationMessage(
                id=key,
                conversation_id=history.annex.id,
                role="assistant",
                content=text,
                message_metadata={"run_id": run_id},
                created_at=_STAMP + timedelta(hours=1),
            )
            for key, text in zip(keys, ["Earlier question", "Final answer"], strict=True)
        ]
    )
    async_session.add_all(
        [
            ConversationMessage(
                conversation_id=history.annex.id,
                role="assistant",
                content=" ",
                message_metadata={"run_id": run_id},
                created_at=_STAMP + timedelta(hours=2),
            ),
            ConversationMessage(
                conversation_id=history.annex.id,
                role="assistant",
                content="Hidden answer",
                hidden=True,
                message_metadata={"run_id": run_id},
                created_at=_STAMP + timedelta(hours=3),
            ),
            MessageTokenSummary(
                user_id=history.owner.id,
                conversation_id=history.annex.id,
                session_id="history",
                run_id=run_id,
                total_prompt_tokens=100,
                total_completion_tokens=10,
                total_cost_eur=Decimal("0.05"),
            ),
        ]
    )
    await async_session.flush()
    first = (await history_client.get(_URL, params={**history.selection, "limit": 1})).json()
    assert first["messages"][0]["id"] == str(keys[-1])
    assert first["messages"][0]["tokens_in"] == 100
    assert first["messages"][0]["cost_eur"] == 0.05
    older = (
        await history_client.get(
            _URL,
            params={
                **history.selection,
                "limit": 1,
                "cursor": first["next_page_cursor"],
            },
        )
    ).json()
    assert older["messages"][0]["id"] == str(keys[0])
    assert older["messages"][0]["tokens_in"] is None
    assert older["messages"][0]["cost_eur"] is None


@pytest.mark.parametrize(
    "origin, target, expected",
    [
        ("same", "annex", 100),
        ("other_owner", "annex", None),
        ("other_discussion", "annex", None),
        ("legacy", "annex", None),
        ("legacy", "main", 100),
    ],
)
async def test_billing_belongs_to_the_owner_and_discussion(
    async_session: AsyncSession,
    history_client: AsyncClient,
    history: History,
    origin: str,
    target: str,
    expected: int | None,
) -> None:
    conversation = history.annex if target == "annex" else history.main
    run_id = str(uuid4())
    message = ConversationMessage(
        conversation_id=conversation.id,
        role="assistant",
        content="Billed answer",
        message_metadata={"run_id": run_id},
        created_at=_STAMP + timedelta(days=1),
    )
    async_session.add_all(
        [
            message,
            MessageTokenSummary(
                user_id=uuid4() if origin == "other_owner" else history.owner.id,
                conversation_id=(
                    None
                    if origin == "legacy"
                    else history.main.id if origin == "other_discussion" else conversation.id
                ),
                session_id="history",
                run_id=run_id,
                total_prompt_tokens=100,
            ),
        ]
    )
    await async_session.flush()
    response = await history_client.get(
        _URL,
        params={
            "conversation_id": str(conversation.id),
            "conversation_revision": conversation.revision,
            "limit": 1,
        },
    )
    assert response.status_code == 200
    assert response.json()["messages"][0]["tokens_in"] == expected


async def test_badge_totals_follow_the_exact_discussion(
    async_session: AsyncSession, history_client: AsyncClient, history: History
) -> None:
    """One badge reads the selected owner's stored prices and complete visible count."""
    async_session.add_all(
        [
            MessageTokenSummary(
                user_id=owner_id,
                conversation_id=discussion_id,
                session_id="badge-test",
                run_id=str(uuid4()),
                total_prompt_tokens=tokens,
                total_cached_tokens=3,
                total_completion_tokens=5,
                total_cost_eur=cost,
                google_api_cost_eur=Decimal("0.02"),
            )
            for owner_id, discussion_id, tokens, cost in (
                (history.owner.id, history.main.id, 25, Decimal("0.1")),
                (history.owner.id, history.annex.id, 70, Decimal("0.4")),
                (uuid4(), history.annex.id, 300, Decimal("1.0")),
                (history.owner.id, None, 400, Decimal("2.0")),
            )
        ]
    )
    await async_session.flush()
    endpoint = "/api/v1/conversations/me/totals"
    annex = await history_client.get(endpoint, params=history.selection)
    assert annex.status_code == 200
    assert annex.json()["conversation_id"] == str(history.annex.id)
    assert annex.json()["conversation_revision"] == history.annex.revision
    assert annex.json()["total_tokens_in"] == 70
    assert annex.json()["total_cost_eur"] == pytest.approx(0.42)
    assert annex.json()["user_message_count"] == len(history.visible)
    main = (await history_client.get(endpoint)).json()
    assert main["conversation_id"] == str(history.main.id)
    assert main["total_tokens_in"] == 25
    assert main["user_message_count"] == 1
    stale = await history_client.get(
        endpoint, params={**history.selection, "conversation_revision": 1}
    )
    assert stale.status_code == 409


async def test_badge_reads_only_the_selected_runtime_checkpoint(
    history_client: AsyncClient,
    history: History,
    native_connection: AsyncConnection[DictRow],
) -> None:
    """The checkpoint key is the generation's runtime, independent of its URL or SQL totals."""
    saver = AsyncPostgresSaver(native_connection)
    await saver.setup()
    messages: list[BaseMessage] = [
        HumanMessage(content="An annex holds several words of its own. " * 14)
    ]
    runtime = str(history.annex.runtime_id)
    try:
        checkpoint = empty_checkpoint()
        checkpoint["channel_values"] = {"messages": messages}
        checkpoint["channel_versions"] = {"messages": 1}
        await saver.aput(
            {"configurable": {"thread_id": runtime, "checkpoint_ns": ""}},
            checkpoint,
            {"source": "input", "step": 0, "parents": {}},
            {"messages": 1},
        )
        endpoint = "/api/v1/conversations/me/totals"
        annex = await history_client.get(endpoint, params=history.selection)
        main = await history_client.get(endpoint)
        assert annex.status_code == main.status_code == 200
        tokens = get_token_counter(settings).count_messages_tokens(messages)
        assert tokens > 0 and annex.json()["context_tokens"] == tokens
        assert main.json()["context_tokens"] == 0
        assert annex.json()["context_threshold"] == main.json()["context_threshold"] > 0
    finally:
        await saver.adelete_thread(runtime)
