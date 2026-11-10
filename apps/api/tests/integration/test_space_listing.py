"""Exercise knowledge-space listing over actual metadata and ownership on PostgreSQL."""

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from time import perf_counter
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Connection, event
from sqlalchemy.engine import ExecutionContext
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import DISPLAY_SEARCH_MAX_LENGTH
from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.rag_spaces.models import RAGDocument, RAGSpace
from src.domains.rag_spaces.router import list_spaces
from src.domains.rag_spaces.schemas import RAGSpaceListQuery, RAGSpaceResponse
from src.domains.rag_spaces.service import RAGSpaceService
from src.domains.users.models import User

pytestmark = pytest.mark.integration


async def seed_spaces(db: AsyncSession, owner: User) -> list[RAGSpace]:
    """Include paused, managed, empty, system and foreign spaces and unready files."""
    stranger = User(id=uuid4(), email=f"space-{uuid4()}@example.com")
    db.add(stranger)
    await db.flush()
    instant = datetime(2026, 1, 1, tzinfo=UTC)
    spaces = [
        RAGSpace(id=uuid4(), user_id=owner.id, name="Zèbre", is_active=True),
        RAGSpace(id=uuid4(), user_id=owner.id, name="École", is_active=False),
        RAGSpace(id=uuid4(), user_id=owner.id, name="Alpha", kind="bookmarks"),
        RAGSpace(id=uuid4(), user_id=owner.id, name="Hidden", is_system=True),
        RAGSpace(id=uuid4(), user_id=stranger.id, name="Foreign"),
    ]
    for index, space in enumerate(spaces):
        space.created_at = instant + timedelta(days=index)
    db.add_all(spaces)
    await db.flush()
    for space, names in zip(
        spaces,
        [
            [],
            ["Rapport été.pdf", "Rapport_hiver.pdf"],
            ["mémo.txt"],
            ["secret.txt"],
            ["Rapport été.pdf"],
        ],
        strict=True,
    ):
        for index, name in enumerate(names):
            db.add(
                RAGDocument(
                    id=uuid4(),
                    space_id=space.id,
                    user_id=space.user_id,
                    filename=f"{uuid4()}.txt",
                    original_filename=name,
                    file_size=10,
                    content_type="text/plain",
                    status="error" if index == 0 else "ready",
                )
            )
    await db.flush()
    return spaces


async def test_default_listing_is_alphabetical_complete_and_aggregated(
    async_session: AsyncSession,
    test_user: User,
) -> None:
    """The real service keeps managed/paused records and counts all file states once."""
    await seed_spaces(async_session, test_user)
    statements: list[str] = []

    def count_statement(
        conn: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: ExecutionContext,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    engine = async_session.bind
    assert engine is not None
    event.listen(engine.sync_engine, "before_cursor_execute", count_statement)
    try:
        result = await RAGSpaceService(async_session).list_spaces(test_user.id)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", count_statement)
    rows = [RAGSpaceResponse.model_validate(item) for item in result]
    assert [row.name for row in rows] == ["Alpha", "École", "Zèbre"]
    school = rows[1]
    assert (school.document_count, school.ready_document_count, school.total_size) == (2, 1, 20)
    assert len(statements) == 1, "Listing must not query statistics once per space"


async def test_empty_owner_has_no_spaces(async_session: AsyncSession, test_user: User) -> None:
    assert await RAGSpaceService(async_session).list_spaces(test_user.id) == []


@pytest.mark.parametrize(
    ("criteria", "expected"),
    [
        (RAGSpaceListQuery(q="éCO", field="name"), ["École"]),
        (RAGSpaceListQuery(q="ETE", field="filename"), ["École"]),
        (RAGSpaceListQuery(q="rapport", field="filename"), ["École"]),
        (RAGSpaceListQuery(q="_", field="filename"), ["École"]),
        (RAGSpaceListQuery(q="%", field="filename"), []),
        (RAGSpaceListQuery(q="secret", field="filename"), []),
        (RAGSpaceListQuery(q="", field="filename"), ["Alpha", "École", "Zèbre"]),
        (RAGSpaceListQuery(sort="files"), ["École", "Alpha", "Zèbre"]),
        (RAGSpaceListQuery(sort="active"), ["Alpha", "Zèbre", "École"]),
        (RAGSpaceListQuery(sort="recent"), ["Alpha", "École", "Zèbre"]),
    ],
)
async def test_literal_filters_and_stable_orders(
    async_session: AsyncSession,
    test_user: User,
    criteria: RAGSpaceListQuery,
    expected: list[str],
) -> None:
    await seed_spaces(async_session, test_user)
    rows = await RAGSpaceService(async_session).list_spaces(test_user.id, criteria)
    assert [row.name for row in rows] == expected


async def test_historical_data_above_creation_quota_remains_complete(
    async_session: AsyncSession,
    test_user: User,
) -> None:
    """A later quota reduction cannot hide older records or their search metadata."""
    count = settings.rag_spaces_max_spaces_per_user + 1
    async_session.add_all(
        [RAGSpace(id=uuid4(), user_id=test_user.id, name=f"Space {i:06d}") for i in range(count)]
    )
    await async_session.flush()
    rows = await RAGSpaceService(async_session).list_spaces(test_user.id)
    assert len(rows) == count


async def test_search_reads_the_last_file_beyond_both_current_creation_quotas(
    async_session: AsyncSession,
    test_user: User,
    record_property: Callable[[str, object], None],
) -> None:
    """Measure the metadata path on a complete historical corpus, including its tail."""
    space_count = settings.rag_spaces_max_spaces_per_user + 1
    file_count = settings.rag_spaces_max_docs_per_space + 1
    spaces = [
        RAGSpace(id=uuid4(), user_id=test_user.id, name=f"Corpus {i:06d}")
        for i in range(space_count)
    ]
    async_session.add_all(spaces)
    await async_session.flush()
    for space in spaces:
        async_session.add_all(
            [
                RAGDocument(
                    id=uuid4(),
                    space_id=space.id,
                    user_id=test_user.id,
                    filename=f"{uuid4()}.txt",
                    original_filename=f"Document {i:06d}.txt",
                    file_size=10,
                    content_type="text/plain",
                    status="pending",
                )
                for i in range(file_count)
            ]
        )
    await async_session.flush()
    started = perf_counter()
    rows = await RAGSpaceService(async_session).list_spaces(
        test_user.id,
        RAGSpaceListQuery(q=f"{file_count - 1:06d}", field="filename"),
    )
    record_property("listing_seconds", perf_counter() - started)
    record_property("metadata_files", space_count * file_count)
    assert len(rows) == space_count
    assert all(row.document_count == file_count and row.ready_document_count == 0 for row in rows)


async def test_http_query_contract_and_exact_total(
    async_session: AsyncSession,
    test_user: User,
) -> None:
    """Real router parameter parsing must reject unknown/oversized queries before reads."""
    await seed_spaces(async_session, test_user)
    app = FastAPI()

    async def db() -> AsyncIterator[AsyncSession]:
        yield async_session

    async def owner() -> User:
        return test_user

    app.dependency_overrides[get_db] = db
    app.dependency_overrides[get_current_active_session] = owner
    app.add_api_route("/spaces", list_spaces, methods=["GET"])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/spaces", params={"q": "rapport", "field": "filename"})
        assert response.status_code == 200
        assert response.json()["total"] == 1
        assert response.json()["spaces"][0]["document_count"] == 2
        for invalid in [
            {"field": "body"},
            {"sort": "random"},
            {"ignored": "no"},
            {"q": "x" * (DISPLAY_SEARCH_MAX_LENGTH + 1)},
        ]:
            assert (await client.get("/spaces", params=invalid)).status_code == 422
