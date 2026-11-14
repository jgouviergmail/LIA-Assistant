"""Words found across every discussion of an account — the door the field and the tool share.

Run on PostgreSQL: the matching is ``unaccent`` + ``ILIKE``, and the oracle is what
the door returns for rows written as the chat writes them.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.conversation_target import ConversationKind
from src.core.field_names import FIELD_RUN_ID
from src.domains.conversations.discussion_search import search_discussions
from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.users.models import User
from src.infrastructure.database.keyset import Keyset

pytestmark = pytest.mark.integration

_T0 = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)


async def _account(session: AsyncSession, email: str) -> tuple[User, Conversation]:
    user = User(email=email, hashed_password="x", is_active=True, is_superuser=False)
    session.add(user)
    await session.flush()
    main = Conversation(id=user.id, user_id=user.id, kind=ConversationKind.MAIN)
    session.add(main)
    await session.flush()
    return user, main


async def _annex(
    session: AsyncSession, user: User, title: str, *, deleted: bool = False
) -> Conversation:
    annex = Conversation(
        user_id=user.id,
        kind=ConversationKind.SECONDARY,
        title=title,
        deleted_at=_T0 if deleted else None,
    )
    session.add(annex)
    await session.flush()
    return annex


def _say(
    session: AsyncSession,
    conversation: Conversation,
    content: str,
    *,
    minutes: int,
    role: str = "user",
    hidden: bool = False,
    run_id: str | None = None,
) -> ConversationMessage:
    message = ConversationMessage(
        conversation_id=conversation.id,
        role=role,
        content=content,
        hidden=hidden,
        message_metadata={FIELD_RUN_ID: run_id} if run_id else None,
        created_at=_T0 + timedelta(minutes=minutes),
    )
    session.add(message)
    return message


async def test_every_discussion_of_the_account_is_searched_newest_first(
    async_session: AsyncSession,
) -> None:
    user, main = await _account(async_session, "search-across@test.local")
    trip = await _annex(async_session, user, "Voyage à Lisbonne")
    _say(async_session, main, "Le devis de la toiture est arrivé", minutes=1)
    _say(async_session, trip, "Penser au devis de l'hôtel", minutes=2, role="assistant")
    _say(async_session, main, "Rien à voir", minutes=3)
    await async_session.commit()

    page = await search_discussions(async_session, user.id, "devis", limit=10)

    assert [hit.content for hit in page.hits] == [
        "Penser au devis de l'hôtel",
        "Le devis de la toiture est arrivé",
    ]
    assert page.has_more is False
    annex_hit, main_hit = page.hits
    assert (annex_hit.conversation_id, annex_hit.conversation_kind) == (
        trip.id,
        ConversationKind.SECONDARY,
    )
    assert annex_hit.conversation_title == "Voyage à Lisbonne"
    assert annex_hit.role == "assistant"
    assert (main_hit.conversation_id, main_hit.conversation_kind) == (
        main.id,
        ConversationKind.MAIN,
    )


async def test_another_account_s_words_are_never_found(async_session: AsyncSession) -> None:
    user, main = await _account(async_session, "search-mine@test.local")
    other, theirs = await _account(async_session, "search-theirs@test.local")
    _say(async_session, main, "Mon devis", minutes=1)
    _say(async_session, theirs, "Leur devis", minutes=2)
    await async_session.commit()

    page = await search_discussions(async_session, user.id, "devis", limit=10)

    assert [hit.content for hit in page.hits] == ["Mon devis"]
    assert other.id != user.id


async def test_a_deleted_discussion_is_not_searched(async_session: AsyncSession) -> None:
    user, main = await _account(async_session, "search-deleted@test.local")
    gone = await _annex(async_session, user, "Supprimée", deleted=True)
    _say(async_session, gone, "Un devis oublié", minutes=1)
    _say(async_session, main, "Un devis gardé", minutes=2)
    await async_session.commit()

    page = await search_discussions(async_session, user.id, "devis", limit=10)

    assert [hit.content for hit in page.hits] == ["Un devis gardé"]


async def test_what_the_chat_does_not_show_is_never_found(async_session: AsyncSession) -> None:
    user, main = await _account(async_session, "search-hidden@test.local")
    _say(async_session, main, "Devis lu par un ticket", minutes=1, hidden=True)
    _say(async_session, main, "  \n", minutes=2, role="assistant")
    _say(async_session, main, "Devis visible", minutes=3)
    await async_session.commit()

    page = await search_discussions(async_session, user.id, "devis", limit=10)

    assert [hit.content for hit in page.hits] == ["Devis visible"]


async def test_the_matching_is_the_history_search_s(async_session: AsyncSession) -> None:
    """Case- and accent-insensitive both ways, wildcards literal — the field's own reading.

    ``unaccent()`` runs on the column AND the term (migration ``add_unaccent_ext_001``),
    and LIKE wildcards in what the person typed are escaped by the shared helper.
    """
    user, main = await _account(async_session, "search-matching@test.local")
    _say(async_session, main, "La RÉUNION de lundi", minutes=1)
    _say(async_session, main, "Prepare the reunion agenda", minutes=2)
    _say(async_session, main, "Remise de 50% appliquée", minutes=3)
    _say(async_session, main, "Remise de 500 euros", minutes=4)
    _say(async_session, main, "J'adore la Pizza margherita", minutes=5)
    await async_session.commit()

    async def found(term: str) -> list[str]:
        page = await search_discussions(async_session, user.id, term, limit=10)
        return [hit.content for hit in page.hits]

    both_spellings = ["Prepare the reunion agenda", "La RÉUNION de lundi"]
    assert await found("reunion") == both_spellings
    assert await found("réunion") == both_spellings
    assert await found("pizza") == ["J'adore la Pizza margherita"]
    assert await found("50%") == ["Remise de 50% appliquée"]
    # Unescaped, `_` would read « any character »: « Pizza » would match.
    assert await found("_izza") == []


async def test_a_page_says_whether_more_follow_and_the_next_one_resumes_exactly(
    async_session: AsyncSession,
) -> None:
    user, main = await _account(async_session, "search-pages@test.local")
    for minute in range(5):
        _say(async_session, main, f"Devis numéro {minute}", minutes=minute)
    # Inside the paging window, matching nothing: never on any page.
    _say(async_session, main, "Sans rapport", minutes=2)
    # Two rows at the same instant: the primary key breaks the tie.
    _say(async_session, main, "Devis jumeau A", minutes=10)
    _say(async_session, main, "Devis jumeau B", minutes=10)
    await async_session.commit()

    seen: list[str] = []
    before: Keyset | None = None
    pages = 0
    while True:
        page = await search_discussions(async_session, user.id, "devis", limit=3, before=before)
        pages += 1
        seen += [hit.content for hit in page.hits]
        if not page.has_more:
            break
        last = page.hits[-1]
        before = Keyset(at=last.created_at, id=last.message_id)

    assert pages == 3
    assert sorted(seen) == sorted(
        ["Devis jumeau A", "Devis jumeau B", *(f"Devis numéro {m}" for m in range(5))]
    )
    assert len(seen) == len(set(seen))


async def test_the_run_that_asks_is_not_its_own_answer(async_session: AsyncSession) -> None:
    """The question is archived before the run (ADR-117): it would be the first match."""
    user, main = await _account(async_session, "search-run@test.local")
    _say(async_session, main, "Le devis de la toiture", minutes=1, run_id="earlier-run")
    _say(async_session, main, "Retrouve le devis", minutes=2, run_id="this-run")
    _say(async_session, main, "Devis sans tour", minutes=3)
    await async_session.commit()

    page = await search_discussions(
        async_session, user.id, "devis", limit=10, excluding_run="this-run"
    )

    assert [hit.content for hit in page.hits] == ["Devis sans tour", "Le devis de la toiture"]


async def test_a_blank_term_finds_nothing_rather_than_everything(
    async_session: AsyncSession,
) -> None:
    user, _main = await _account(async_session, "search-blank@test.local")

    with pytest.raises(ValueError):
        await search_discussions(async_session, user.id, "   ", limit=10)


async def test_an_account_with_no_match_gets_an_empty_page(async_session: AsyncSession) -> None:
    page = await search_discussions(async_session, uuid4(), "devis", limit=5)

    assert (page.hits, page.has_more) == ([], False)
