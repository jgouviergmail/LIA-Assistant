"""Authenticated catalogue journeys through the actual API and PostgreSQL."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient
from redis.asyncio import Redis
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.core.constants import CONVERSATION_TITLE_MAX_LENGTH
from src.core.conversation_target import ConversationKind
from src.core.session_dependencies import get_current_active_session
from src.domains.conversations import cleanup_port
from src.domains.conversations.catalogue_schemas import ConversationCreateRequest
from src.domains.conversations.catalogue_service import ConversationCatalogueService
from src.domains.conversations.models import (
    Conversation,
    ConversationAuditLog,
    ConversationCreationReceipt,
)
from src.domains.conversations.service import ConversationService
from src.domains.users.models import User
from src.infrastructure.conversation_cleanup_runtime import NativeRuntimeCleanup
from src.infrastructure.observability.metrics_business import user_return_rate_total
from src.infrastructure.streaming import live_binding
from src.main import app

pytestmark = pytest.mark.integration
URL = "/api/v1/conversations"


async def test_lifecycle_routes_publish_reconciliation_without_claiming_cleanup(
    client: AsyncClient,
    async_engine: AsyncEngine,
    redis_client: Redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(async_engine) as db:
            yield db
            await db.commit()

    async def redis() -> Redis:
        return redis_client

    # The in-process ASGI transport omits lifespan. Use the adapter from startup
    # with the test-owned connections, including its Live retirement check.
    monkeypatch.setattr(cleanup_port, "_runtime_cleanup", NativeRuntimeCleanup())
    monkeypatch.setattr(live_binding, "get_db_context", session)
    monkeypatch.setattr(live_binding, "get_redis_cache", redis)
    created = await client.post(URL, json={"title": "A separate topic", "request_id": str(uuid4())})
    target = created.json()["conversation"]
    payload = {"operation_id": str(uuid4()), "expected_revision": target["revision"]}
    reset = await client.post(f"{URL}/{target['id']}/reset", json=payload)
    assert reset.status_code == 202
    data = reset.json()
    assert data["logical_applied"] and not data["cleanup_complete"]
    assert data["new_revision"] == target["revision"] + 1
    replay = await client.post(f"{URL}/{target['id']}/reset", json=payload)
    assert replay.status_code == 202 and replay.json()["replayed"]
    status = await client.get(f"{URL}/operations/{payload['operation_id']}")
    assert status.status_code == 200 and status.json()["state"] == "pending"
    assert "no-store" in status.headers["cache-control"]
    private = {"runtime_id", "owner_token", "attachment_ids", "fence"}
    assert private.isdisjoint(status.json())
    deletion = {"operation_id": str(uuid4()), "expected_revision": data["new_revision"]}
    endpoint = f"{URL}/{target['id']}"
    plain = await client.request(
        "DELETE",
        endpoint,
        content=json.dumps(deletion),
        headers={"Content-Type": "text/plain;charset=UTF-8"},
    )
    assert plain.status_code == 422
    assert (await client.get(endpoint)).status_code == 200
    removed = await client.request("DELETE", endpoint, json=deletion)
    assert removed.status_code == 202
    assert (await client.get(f"{URL}/{target['id']}")).status_code == 404


async def test_annex_rename_preserves_generation_and_detects_stale_edit(
    client: AsyncClient,
) -> None:
    created = await client.post(URL, json={"title": "Original", "request_id": str(uuid4())})
    row = created.json()["conversation"]
    endpoint = f"{URL}/{row['id']}"
    payload = {"title": "  Nouveau nom  ", "expected_title": "Original", "expected_revision": 0}
    renamed = await client.patch(endpoint, json=payload)
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Nouveau nom"
    assert renamed.json()["revision"] == row["revision"]
    assert renamed.json()["id"] == row["id"]
    assert (await client.patch(endpoint, json=payload)).status_code == 200
    stale = await client.patch(endpoint, json={**payload, "title": "Another edit"})
    assert stale.status_code == 409
    assert (await client.get(endpoint)).json()["title"] == "Nouveau nom"
    assert (await client.patch(endpoint, json={**payload, "title": "\u200b"})).status_code == 422
    assert (await client.patch(f"{URL}/{uuid4()}", json=payload)).status_code == 404
    main = (await client.get(f"{URL}/me")).json()
    assert (await client.patch(f"{URL}/{main['id']}", json=payload)).status_code == 403


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"operation_id": "bad", "expected_revision": 0},
        {"operation_id": str(uuid4()), "expected_revision": True},
        {"operation_id": str(uuid4()), "expected_revision": -1},
        {"operation_id": str(uuid4()), "expected_revision": 0, "runtime_id": "private"},
    ],
)
async def test_lifecycle_http_refuses_malformed_or_private_authority(
    client: AsyncClient,
    payload: dict[str, object],
) -> None:
    response = await client.post(f"{URL}/{uuid4()}/reset", json=payload)
    assert response.status_code == 422
    assert "private" not in response.text and '"input"' not in response.text


@pytest.fixture
async def owner(async_session: AsyncSession) -> User:
    """Create an account whose writes are owned by the external transaction."""
    user = User(email=f"catalogue-{uuid4()}@example.test", hashed_password="unused", is_active=True)
    async_session.add(user)
    await async_session.flush()
    return user


@pytest.fixture
async def client(
    async_client: AsyncClient, owner: User, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AsyncClient]:
    """Replace authentication alone, retaining request validation and real services."""

    async def authenticated() -> User:
        return owner

    monkeypatch.setattr(settings, "secondary_conversations_enabled", True)
    app.dependency_overrides[get_current_active_session] = authenticated
    try:
        yield async_client
    finally:
        app.dependency_overrides.pop(get_current_active_session, None)


async def test_listing_a_new_account_does_not_create_a_main(
    client: AsyncClient, async_session: AsyncSession, owner: User
) -> None:
    response = await client.get(URL)
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total_count"] == 0
    assert (
        await async_session.scalar(
            select(func.count()).select_from(Conversation).where(Conversation.user_id == owner.id)
        )
        == 0
    )


async def test_activity_does_not_move_discussions_between_catalogue_pages(
    client: AsyncClient, async_session: AsyncSession
) -> None:
    """A reply in an older annex cannot move rows while the manager is being read."""
    created: list[Conversation] = []
    for title in ("Older", "Newer"):
        response = await client.post(URL, json={"title": title, "request_id": str(uuid4())})
        assert response.status_code == 200
        row = await async_session.get(Conversation, response.json()["conversation"]["id"])
        assert row is not None
        created.append(row)
    older, newer = created
    stamp = datetime.now(UTC)
    older.created_at = older.updated_at = stamp - timedelta(days=2)
    newer.created_at = newer.updated_at = stamp - timedelta(days=1)
    await async_session.flush()
    initial = (await client.get(URL)).json()
    assert initial["items"][0]["kind"] == "main"
    expected = [str(newer.id), str(older.id)]
    assert [row["id"] for row in initial["items"][1:]] == expected

    older.updated_at = stamp
    await async_session.flush()
    pages = [
        (await client.get(URL, params={"limit": 1, "offset": offset})).json() for offset in (1, 2)
    ]
    assert [page["items"][0]["id"] for page in pages] == expected
    assert all(page["total_count"] == 3 for page in pages)


async def test_trimmed_full_length_title_and_canonical_retry_are_one_creation(
    client: AsyncClient,
) -> None:
    """The API and durable receipt both use the accepted, trimmed Unicode title."""
    title = "🎨" * CONVERSATION_TITLE_MAX_LENGTH
    request_id = str(uuid4())
    first = await client.post(URL, json={"title": f" \t{title}\u3000 ", "request_id": request_id})
    assert first.status_code == 200
    assert first.json()["conversation"]["title"] == title
    replay = await client.post(URL, json={"title": title, "request_id": request_id})
    assert replay.status_code == 200 and replay.json()["replayed"]
    assert replay.json()["conversation"]["id"] == first.json()["conversation"]["id"]


@pytest.mark.parametrize("title", ["\u200b", "\u2800", "\ufeff \u200d"])
async def test_invisible_only_title_is_refused_before_any_row_is_created(
    client: AsyncClient, title: str
) -> None:
    response = await client.post(URL, json={"title": title, "request_id": str(uuid4())})
    assert response.status_code == 422
    assert (await client.get(URL)).json()["total_count"] == 0


async def test_creation_ensures_main_and_replay_never_duplicates(
    client: AsyncClient, owner: User
) -> None:
    request = {"title": "  Workshop  ", "request_id": str(uuid4())}
    first = await client.post(URL, json=request)
    assert first.status_code == 200
    second = await client.post(URL, json=request)
    assert second.status_code == 200
    assert first.json()["conversation"]["id"] == second.json()["conversation"]["id"]
    assert first.json()["replayed"] is False
    assert second.json()["replayed"] is True
    listing = (await client.get(URL)).json()
    assert listing["total_count"] == 2
    assert [row["kind"] for row in listing["items"]] == ["main", "secondary"]
    assert listing["items"][0]["id"] == str(owner.id)
    assert listing["items"][1]["title"] == "Workshop"
    main_alias = await client.get(f"{URL}/me")
    assert main_alias.status_code == 200
    assert main_alias.json()["id"] == str(owner.id)


async def test_reusing_an_attempt_with_different_words_is_a_conflict(client: AsyncClient) -> None:
    request_id = str(uuid4())
    assert (
        await client.post(URL, json={"title": "One", "request_id": request_id})
    ).status_code == 200
    response = await client.post(URL, json={"title": "Two", "request_id": request_id})
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "conversation_request_conflict"


@pytest.mark.parametrize(
    "title",
    [
        "",
        " \t\n",
        "\u00a0\u3000",
        "x" * (CONVERSATION_TITLE_MAX_LENGTH + 1),
        # A null title is no longer here: it asks for an automatic one
        # (test_auto_title.py). A title that IS sent stays held to the grammar.
        12,
        "Null\x00byte",
    ],
)
async def test_invalid_titles_never_create_any_discussion(
    client: AsyncClient, title: object
) -> None:
    response = await client.post(URL, json={"title": title, "request_id": str(uuid4())})
    assert response.status_code == 422
    assert (await client.get(URL)).json()["total_count"] == 0


async def test_withdrawing_creation_keeps_list_and_accepted_replays(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = {"title": "Kept", "request_id": str(uuid4())}
    first = await client.post(URL, json=request)
    assert first.status_code == 200
    monkeypatch.setattr(settings, "secondary_conversations_enabled", False)
    assert (await client.get(URL)).json()["total_count"] == 2
    replay = await client.post(URL, json=request)
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    refused = await client.post(URL, json={**request, "request_id": str(uuid4())})
    assert refused.status_code == 403


@pytest.mark.parametrize("physically_deleted", [False, True])
async def test_retired_creation_receipt_never_recreates_a_discussion(
    client: AsyncClient,
    async_session: AsyncSession,
    physically_deleted: bool,
) -> None:
    request = {"title": "Retired", "request_id": str(uuid4())}
    created = (await client.post(URL, json=request)).json()["conversation"]
    row = await async_session.get(Conversation, created["id"])
    assert row is not None
    if physically_deleted:
        await async_session.delete(row)
    else:
        row.deleted_at = datetime.now(UTC)
    await async_session.commit()
    response = await client.post(URL, json=request)
    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "conversation_retired"
    assert (await client.get(URL)).json()["total_count"] == 1


async def test_foreign_and_absent_are_indistinguishable_even_for_an_admin(
    client: AsyncClient,
    async_session: AsyncSession,
    owner: User,
) -> None:
    stranger = User(email=f"stranger-{uuid4()}@example.test", hashed_password="unused")
    async_session.add(stranger)
    await async_session.flush()
    foreign = Conversation(user_id=stranger.id, title="Private")
    async_session.add(foreign)
    owner.is_superuser = True
    await async_session.flush()
    hidden = await client.get(f"{URL}/{foreign.id}")
    missing = await client.get(f"{URL}/{uuid4()}")
    assert hidden.status_code == missing.status_code == 404
    assert hidden.json()["detail"] == missing.json()["detail"]
    assert (await client.get(URL)).json()["total_count"] == 0


async def test_page_totals_and_order_remain_exact_beyond_one_page(
    client: AsyncClient,
    async_session: AsyncSession,
    owner: User,
) -> None:
    await client.post(URL, json={"title": "First", "request_id": str(uuid4())})
    stamp = datetime.now(UTC)
    added = [
        Conversation(
            user_id=owner.id,
            kind=ConversationKind.SECONDARY,
            title=f"Number {i}",
            created_at=stamp,
            updated_at=stamp,
        )
        for i in range(settings.conversation_list_max_limit)
    ]
    async_session.add_all(added)
    await async_session.flush()
    # Creation has no hidden account ceiling after filling a maximum-sized page.
    assert (
        await client.post(URL, json={"title": "Another", "request_id": str(uuid4())})
    ).status_code == 200
    total = len(added) + 3
    statements: list[str] = []

    def collect_sql(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        if statement.lstrip().upper().startswith(("SELECT", "WITH")):
            statements.append(statement)

    connection = (await async_session.connection()).sync_connection
    event.listen(connection, "before_cursor_execute", collect_sql)
    try:
        one = await client.get(URL, params={"limit": 1})
        one_count = len(statements)
        statements.clear()
        many = await client.get(URL, params={"limit": settings.conversation_list_max_limit})
        assert one.status_code == many.status_code == 200
        assert len(one.json()["items"]) == 1
        assert len(many.json()["items"]) == settings.conversation_list_max_limit
        assert len(statements) == one_count > 0
        assert all(
            "conversation_messages" not in sql and "checkpoints" not in sql for sql in statements
        )
    finally:
        event.remove(connection, "before_cursor_execute", collect_sql)

    ids: list[str] = []
    for offset in range(0, total, 13):
        page = (await client.get(URL, params={"limit": 13, "offset": offset})).json()
        assert page["total_count"] == total
        ids.extend(row["id"] for row in page["items"])
    assert ids[0] == str(owner.id)
    assert len(ids) == len(set(ids)) == total
    assert [identity for identity in ids if identity in {str(row.id) for row in added}] == sorted(
        str(row.id) for row in added
    )
    empty = (await client.get(URL, params={"offset": total + 10})).json()
    assert empty["items"] == [] and empty["total_count"] == total


async def test_failed_commit_rolls_back_main_annex_and_receipt_together(
    client: AsyncClient,
    async_session: AsyncSession,
    owner: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await async_session.commit()  # Establish the account before the failing operation.
    request = ConversationCreateRequest(title="Retry", request_id=uuid4())

    async def fail_commit() -> None:
        raise RuntimeError("simulated commit failure")

    with monkeypatch.context() as patch:
        patch.setattr(async_session, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="simulated commit failure"):
            await ConversationCatalogueService(async_session).create_secondary(owner.id, request)
        await async_session.rollback()
    await async_session.refresh(owner)  # Rollback expires ORM identities as in production.
    assert (await client.get(URL)).json()["total_count"] == 0
    assert (
        await async_session.scalar(select(func.count()).select_from(ConversationCreationReceipt))
        == 0
    )
    retried = await client.post(URL, json=request.model_dump(mode="json"))
    assert retried.status_code == 200 and retried.json()["replayed"] is False


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": settings.conversation_list_max_limit + 1},
        {"offset": -1},
        {"offset": 2**63},
    ],
)
async def test_invalid_page_bounds_are_rejected_before_sql(
    client: AsyncClient,
    params: dict[str, int],
) -> None:
    assert (await client.get(URL, params=params)).status_code == 422


async def test_invalid_unicode_is_rejected_before_hashing(client: AsyncClient) -> None:
    payload = '{"title":"\\ud800","request_id":"' + str(uuid4()) + '"}'
    response = await client.post(URL, content=payload, headers={"Content-Type": "application/json"})
    assert response.status_code == 422


async def test_legacy_reactivation_preserves_identity_and_audit_provenance(
    client: AsyncClient,
    async_session: AsyncSession,
    owner: User,
) -> None:
    retired_at = datetime.now(UTC)
    primary = Conversation(
        id=owner.id,
        user_id=owner.id,
        runtime_id=owner.id,
        title="Legacy",
        deleted_at=retired_at,
        message_count=4,
        total_tokens=120,
    )
    secondary = Conversation(
        user_id=owner.id,
        kind=ConversationKind.SECONDARY,
        title="Retired annex",
        deleted_at=retired_at,
    )
    async_session.add_all([primary, secondary])
    await async_session.flush()
    resolved = await ConversationService().get_or_create_conversation(owner.id, async_session, "zh")
    assert resolved.id == resolved.runtime_id == owner.id
    assert resolved.deleted_at is None
    assert resolved.message_count == 4 and resolved.total_tokens == 120
    assert secondary.deleted_at == retired_at
    audit = (
        await async_session.scalars(
            select(ConversationAuditLog).where(
                ConversationAuditLog.conversation_id == owner.id,
                ConversationAuditLog.action == "reactivated",
            )
        )
    ).one()
    assert audit.audit_metadata is not None
    assert audit.audit_metadata["previous_deleted_at"] == str(retired_at)
    assert (await client.get(f"{URL}/me")).json()["id"] == str(owner.id)


async def test_late_creation_after_deactivation_writes_nothing(
    client: AsyncClient,
    async_session: AsyncSession,
    owner: User,
) -> None:
    # Keep the stale authentication override: the service must recheck the account.
    owner.is_active = False
    await async_session.flush()
    response = await client.post(URL, json={"title": "Late", "request_id": str(uuid4())})
    assert response.status_code == 404
    assert (
        await async_session.scalar(
            select(func.count()).select_from(Conversation).where(Conversation.user_id == owner.id)
        )
        == 0
    )


async def test_creation_metrics_count_an_accepted_attempt_once(
    client: AsyncClient,
    async_session: AsyncSession,
    owner: User,
) -> None:
    async_session.add(
        Conversation(
            id=owner.id,
            user_id=owner.id,
            runtime_id=owner.id,
            created_at=datetime.now(UTC) - timedelta(hours=2),
        )
    )
    await async_session.flush()
    metric = user_return_rate_total.labels(time_window="24h")
    before = metric._value.get()
    payload = {"title": "Return", "request_id": str(uuid4())}
    assert (await client.post(URL, json=payload)).status_code == 200
    assert metric._value.get() == before + 1
    assert (await client.post(URL, json=payload)).json()["replayed"] is True
    assert metric._value.get() == before + 1
