"""The history search field reaches every discussion of the account — through the real router.

Run on PostgreSQL: the account's discussions are written as the chat writes them, the
oracle is what the route answers.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import Depends, FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import CONVERSATION_SEARCH_MIN_LENGTH
from src.core.conversation_target import ConversationKind
from src.core.dependencies import get_db
from src.core.i18n_api_messages import APIMessages
from src.core.session_dependencies import get_current_active_session
from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.conversations.router import router
from src.domains.users.models import User

pytestmark = pytest.mark.integration

_T0 = datetime(2026, 11, 2, 8, 0, tzinfo=UTC)


@pytest.fixture
async def client(async_session: AsyncSession, test_user: User) -> AsyncIterator[httpx.AsyncClient]:
    async def authenticated(db: AsyncSession = Depends(get_db)) -> User:
        account = await db.scalar(select(User).where(User.id == test_user.id))
        assert account is not None
        return account

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: async_session
    app.dependency_overrides[get_current_active_session] = authenticated
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http:
        yield http


@pytest.fixture
async def discussions(async_session: AsyncSession, test_user: User) -> dict[str, Conversation]:
    main = await async_session.get(Conversation, test_user.id)
    if main is None:
        main = Conversation(id=test_user.id, user_id=test_user.id, kind=ConversationKind.MAIN)
        async_session.add(main)
    annex = Conversation(user_id=test_user.id, kind=ConversationKind.SECONDARY, title="Travaux")
    async_session.add(annex)
    await async_session.flush()
    for minute, (where, content) in enumerate(
        [
            (main, "Le devis du plombier"),
            (annex, "Devis de la toiture reçu"),
            (main, "Rien à voir"),
            (annex, "Relancer le couvreur pour le devis"),
        ]
    ):
        async_session.add(
            ConversationMessage(
                conversation_id=where.id,
                role="user",
                content=content,
                created_at=_T0 + timedelta(minutes=minute),
            )
        )
    await async_session.commit()
    return {"main": main, "annex": annex}


async def test_the_field_finds_words_in_every_discussion_newest_first(
    client: httpx.AsyncClient, discussions: dict[str, Conversation]
) -> None:
    response = await client.get("/conversations/me/search", params={"q": "devis"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert [row["content"] for row in body["results"]] == [
        "Relancer le couvreur pour le devis",
        "Devis de la toiture reçu",
        "Le devis du plombier",
    ]
    assert body["has_more"] is False and body["next_cursor"] is None
    newest = body["results"][0]
    assert newest["conversation_id"] == str(discussions["annex"].id)
    assert (newest["conversation_kind"], newest["conversation_title"]) == ("secondary", "Travaux")
    assert newest["role"] == "user" and newest["message_id"]
    # Main's label is the reader's to translate: no stored title travels.
    assert body["results"][-1]["conversation_title"] is None


async def test_the_next_page_resumes_where_the_cursor_says(
    client: httpx.AsyncClient, discussions: dict[str, Conversation]
) -> None:
    first = (await client.get("/conversations/me/search", params={"q": "devis", "limit": 2})).json()

    assert first["has_more"] is True
    second = (
        await client.get(
            "/conversations/me/search",
            params={"q": "devis", "limit": 2, "cursor": first["next_cursor"]},
        )
    ).json()

    assert [row["content"] for row in first["results"] + second["results"]] == [
        "Relancer le couvreur pour le devis",
        "Devis de la toiture reçu",
        "Le devis du plombier",
    ]
    assert second["has_more"] is False


async def test_a_damaged_cursor_is_refused_in_the_person_s_language(
    client: httpx.AsyncClient, discussions: dict[str, Conversation]
) -> None:
    response = await client.get(
        "/conversations/me/search", params={"q": "devis", "cursor": "not-a-cursor"}
    )

    assert response.status_code == 400
    assert response.json()["detail"] == APIMessages.conversation_history_cursor_invalid()


async def test_a_term_shorter_than_the_history_search_s_is_refused(
    client: httpx.AsyncClient, discussions: dict[str, Conversation]
) -> None:
    response = await client.get(
        "/conversations/me/search", params={"q": "d" * (CONVERSATION_SEARCH_MIN_LENGTH - 1)}
    )

    assert response.status_code == 422
