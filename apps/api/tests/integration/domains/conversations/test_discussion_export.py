"""One discussion exported as Markdown, through the real API and PostgreSQL.

The unit tests stub the cursor; these execute the statement. What must hold on
a real server:

- the document holds what the chat shows of THAT discussion, oldest first:
  nothing hidden, no blank progress row, nothing of another discussion, nothing
  written after the export was asked;
- it is the caller's own: a foreign or absent discussion and a reset one are
  refused exactly as the history refuses them;
- it leaves as a Markdown attachment named for the reader's day.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.conversations import discussion_export
from src.domains.conversations import router as conversations_router
from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.users.models import User
from src.main import app
from tests.integration.domains.conversations.test_catalogue_routes import client as client
from tests.integration.domains.conversations.test_catalogue_routes import owner as owner

pytestmark = pytest.mark.integration
URL = "/api/v1/conversations"
EXPORT = f"{URL}/me/export"
#: Long before the export is asked: every row is inside its closed read.
START = datetime(2026, 11, 1, 8, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def own_sessions(
    async_session: AsyncSession, owner: User, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """The export holds no request session: it authenticates and reads on its own.

    Both of its short sessions — the ownership read and the cursor — are, here,
    one more session on the test's connection: the fixture's rows are never
    committed (an outer transaction is rolled back at teardown), so only a
    session on the SAME connection can see them.
    """

    @asynccontextmanager
    async def context() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(
            bind=async_session.bind,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        ) as session:
            yield session

    async def authenticated() -> User:
        return owner

    monkeypatch.setattr(discussion_export, "get_db_context", context)
    monkeypatch.setattr(conversations_router, "get_db_context", context)
    app.dependency_overrides[get_current_active_session_for_stream] = authenticated
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_active_session_for_stream, None)


async def _annex(http: AsyncClient, title: str = "Trip to Lisbon") -> dict[str, Any]:
    created = await http.post(URL, json={"title": title, "request_id": str(uuid4())})
    assert created.status_code == 200, created.text
    row: dict[str, Any] = created.json()["conversation"]
    return row


async def _say(
    db: AsyncSession,
    conversation_id: str,
    role: str,
    content: str,
    *,
    minute: int,
    hidden: bool = False,
) -> None:
    db.add(
        ConversationMessage(
            conversation_id=UUID(conversation_id),
            role=role,
            content=content,
            message_metadata={},
            hidden=hidden,
            created_at=START + timedelta(minutes=minute),
        )
    )
    await db.flush()


def _selection(row: dict[str, Any]) -> dict[str, Any]:
    return {"conversation_id": row["id"], "conversation_revision": row["revision"]}


async def test_the_document_is_what_the_chat_shows_of_that_discussion_in_order(
    client: AsyncClient, async_session: AsyncSession
) -> None:
    annex = await _annex(client)
    main = (await client.get(f"{URL}/me")).json()
    # Written out of order on purpose: the document reads forward.
    await _say(async_session, annex["id"], "assistant", "Second: the answer", minute=2)
    await _say(async_session, annex["id"], "user", "First: the question", minute=1)
    await _say(async_session, annex["id"], "assistant", "   ", minute=3)  # a blank progress row
    await _say(async_session, annex["id"], "assistant", "A hidden run", minute=4, hidden=True)
    await _say(async_session, main["id"], "user", "Said in Main", minute=5)

    response = await client.get(EXPORT, params=_selection(annex))

    assert response.status_code == 200
    document = response.text
    assert document.startswith("# Trip to Lisbon\n")
    assert document.index("First: the question") < document.index("Second: the answer")
    assert "A hidden run" not in document
    assert "Said in Main" not in document
    # The header's rule, and one per message the chat shows: the blank row is not one.
    assert document.count("\n---\n") == 3


async def test_it_leaves_as_a_markdown_attachment(
    client: AsyncClient, async_session: AsyncSession
) -> None:
    annex = await _annex(client)
    await _say(async_session, annex["id"], "user", "Hello", minute=1)

    response = await client.get(EXPORT, params=_selection(annex))

    assert response.headers["content-type"].startswith("text/markdown")
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment")
    assert "lia-discussion-" in disposition and ".md" in disposition
    # Complete, and it says so (ADR-273).
    assert response.headers["x-discussion-truncated"] == "false"


async def test_a_message_written_after_the_export_was_asked_is_not_in_it(
    client: AsyncClient, async_session: AsyncSession
) -> None:
    annex = await _annex(client)
    await _say(async_session, annex["id"], "user", "In time", minute=1)
    db_row = ConversationMessage(
        conversation_id=UUID(annex["id"]),
        role="assistant",
        content="From the future",
        message_metadata={},
        created_at=datetime.now(UTC) + timedelta(hours=1),
    )
    async_session.add(db_row)
    await async_session.flush()

    document = (await client.get(EXPORT, params=_selection(annex))).text

    assert "In time" in document
    assert "From the future" not in document


async def test_no_selection_exports_main_under_its_name(
    client: AsyncClient, async_session: AsyncSession
) -> None:
    await _annex(client)  # creating an annex ensures Main
    main = (await client.get(f"{URL}/me")).json()
    await _say(async_session, main["id"], "user", "Said in Main", minute=1)

    response = await client.get(EXPORT)

    assert response.status_code == 200
    # Main stores a dated legacy title; the document carries the name the chat shows.
    assert response.text.splitlines()[0] in {"# Main", "# Principale"}
    assert main["title"] not in response.text.splitlines()[0]
    assert "Said in Main" in response.text


async def test_an_empty_discussion_exports_a_document_that_says_so(client: AsyncClient) -> None:
    annex = await _annex(client)

    response = await client.get(EXPORT, params=_selection(annex))

    assert response.status_code == 200
    assert response.text.startswith("# Trip to Lisbon\n")
    assert response.text.count("\n---\n") == 1


async def test_a_foreign_or_absent_discussion_is_refused_alike(
    client: AsyncClient, async_session: AsyncSession
) -> None:
    stranger = User(email=f"stranger-{uuid4()}@example.test", hashed_password="x", is_active=True)
    async_session.add(stranger)
    await async_session.flush()
    foreign = Conversation(user_id=stranger.id, kind="secondary", title="Not yours")
    async_session.add(foreign)
    await async_session.flush()

    theirs = await client.get(
        EXPORT, params={"conversation_id": str(foreign.id), "conversation_revision": 0}
    )
    absent = await client.get(
        EXPORT, params={"conversation_id": str(uuid4()), "conversation_revision": 0}
    )

    assert theirs.status_code == absent.status_code == 404
    assert "Not yours" not in theirs.text


async def test_a_generation_that_was_reset_is_refused_as_the_history_refuses_it(
    client: AsyncClient,
) -> None:
    annex = await _annex(client)

    stale = await client.get(
        EXPORT, params={"conversation_id": annex["id"], "conversation_revision": 7}
    )

    assert stale.status_code == 409
