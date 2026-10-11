"""Connection UI reads retain consent, ownership, notes and bounded source pages."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import event, update

from src.core.config import settings
from src.domains.agents.tools import application_peer_tools
from src.domains.peers.models import (
    PeerBlock,
    PeerConnection,
    PeerDomainShare,
    PeerMessage,
    canonical_pair,
)
from src.domains.peers.service import PeersService
from src.domains.users.models import User
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def enabled_peers(monkeypatch):
    monkeypatch.setattr(settings, "peers_enabled", True)


@pytest.mark.parametrize(
    "section", ["preferences", "connections", "requests", "blocks", "access_log", "messages"]
)
async def test_peer_ui_reads_owned_data_and_source_consent(
    async_session, test_user, monkeypatch, section
):
    owner = test_user.id
    peer = User(
        id=uuid4(),
        email=f"peer-{uuid4()}@example.com",
        hashed_password="controlled",
        is_active=True,
        full_name="Alice",
        peer_email_visible=False,
    )
    outsider = User(
        id=uuid4(),
        email=f"outsider-{uuid4()}@example.com",
        hashed_password="controlled",
        is_active=True,
        full_name="Other account",
    )
    async_session.add_all([peer, outsider])
    await async_session.flush()
    lo, hi = canonical_pair(owner, peer.id)
    pair = PeerConnection(
        user_a_id=lo,
        user_b_id=hi,
        requested_by_id=peer.id,
        status="pending" if section == "requests" else "accepted",
        context_message="Incoming requester note",
        requested_at=datetime.now(UTC),
    )
    lo2, hi2 = canonical_pair(peer.id, outsider.id)
    async_session.add_all(
        [
            pair,
            PeerConnection(
                user_a_id=lo2,
                user_b_id=hi2,
                requested_by_id=outsider.id,
                status=pair.status,
                requested_at=datetime.now(UTC),
            ),
            PeerBlock(blocker_id=owner, blocked_id=outsider.id),
        ]
    )
    await async_session.commit()

    @asynccontextmanager
    async def session():
        yield async_session

    monkeypatch.setattr(application_peer_tools, "get_db_context", session)
    with installed_runtime_context(user_id=owner, deps=object()):
        result = await application_peer_tools.get_lia_peer_settings_tool.coroutine(
            query={"section": section, "limit": 1},
            runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
        )
    assert result.success
    data = result.structured_data
    assert data["section"] == section
    if section == "preferences":
        assert data["preferences"]["email_visible"] == bool(test_user.peer_email_visible)
    elif section in {"connections", "requests"}:
        assert data["total"] == 1 and data["items"][0]["id"] == str(pair.id)
        assert data["items"][0]["peer_email"] is None
        assert data["items"][0]["context_message"] == (
            "Incoming requester note" if section == "requests" else None
        )
    elif section == "blocks":
        assert data["items"][0]["blocked_id"] == str(outsider.id)
    else:
        assert data["items"] == []


@pytest.mark.parametrize(
    "scenario", ["native_off", "peers_off", "late_off", "late_peers_off", "late_actor_off"]
)
async def test_peer_ui_read_rechecks_authority(async_session, test_user, monkeypatch, scenario):
    owner = test_user.id
    await async_session.commit()

    @asynccontextmanager
    async def session():
        yield async_session

    monkeypatch.setattr(application_peer_tools, "get_db_context", session)
    if scenario == "native_off":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    elif scenario == "peers_off":
        monkeypatch.setattr(settings, "peers_enabled", False)
    else:
        original = PeersService.get_connections

        async def withdraw(service, actor_id):
            result = await original(service, actor_id)
            if scenario == "late_actor_off":
                await async_session.execute(
                    update(User)
                    .where(User.id == owner)
                    .values(is_active=False)
                    .execution_options(synchronize_session=False)
                )
                await async_session.commit()
            else:
                monkeypatch.setattr(
                    settings,
                    (
                        "peers_enabled"
                        if scenario == "late_peers_off"
                        else "application_tools_enabled"
                    ),
                    False,
                )
            return result

        monkeypatch.setattr(PeersService, "get_connections", withdraw)
    with installed_runtime_context(user_id=owner, deps=object()):
        result = await application_peer_tools.get_lia_peer_settings_tool.coroutine(
            query={"section": "connections"},
            runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
        )
    assert not result.success and not result.structured_data


async def test_connection_shares_do_not_issue_one_query_per_card(async_session, test_user):
    owner = test_user.id
    peers = [
        User(
            id=uuid4(),
            email=f"scale-{uuid4()}@example.com",
            hashed_password="controlled",
            is_active=True,
            full_name=f"Peer {i}",
        )
        for i in range(8)
    ]
    async_session.add_all(peers)
    await async_session.flush()
    for peer in peers:
        lo, hi = canonical_pair(owner, peer.id)
        pair = PeerConnection(
            user_a_id=lo,
            user_b_id=hi,
            requested_by_id=owner,
            status="accepted",
            requested_at=datetime.now(UTC),
        )
        async_session.add(pair)
        await async_session.flush()
        async_session.add_all(
            [
                PeerDomainShare(
                    connection_id=pair.id, owner_user_id=owner, domain="task", level="titles"
                ),
                PeerDomainShare(
                    connection_id=pair.id,
                    owner_user_id=peer.id,
                    domain="calendar",
                    level="availability",
                ),
            ]
        )
    await async_session.commit()
    statements = []
    engine = async_session.bind.sync_engine

    def record(connection, cursor, statement, parameters, context, many):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        views = await PeersService(async_session).get_connections(owner)
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert len(views) == 8
    assert all([share.domain for share in view.my_shares] == ["task"] for view in views)
    assert all([share.domain for share in view.their_shares] == ["calendar"] for view in views)
    assert len([stmt for stmt in statements if "peer_domain_shares" in stmt]) == 1


async def test_relay_page_keeps_only_owners_text_and_retained_nulls(
    async_session, test_user, monkeypatch
):
    owner = test_user.id
    peer = User(
        id=uuid4(),
        email=f"relay-{uuid4()}@example.com",
        hashed_password="controlled",
        is_active=True,
        full_name="Alice",
    )
    async_session.add(peer)
    await async_session.flush()
    lo, hi = canonical_pair(owner, peer.id)
    pair = PeerConnection(
        user_a_id=lo,
        user_b_id=hi,
        requested_by_id=owner,
        status="accepted",
        requested_at=datetime.now(UTC),
    )
    async_session.add(pair)
    await async_session.flush()
    now = datetime.now(UTC)
    messages = [
        PeerMessage(
            connection_id=pair.id,
            sender_id=owner,
            recipient_id=peer.id,
            status="delivered",
            delivered_at=now,
            content="My sent directive",
            delivered_text="Other assistant private text",
        ),
        PeerMessage(
            connection_id=pair.id,
            sender_id=peer.id,
            recipient_id=owner,
            status="delivered",
            delivered_at=now,
            content="Other sender private directive",
            delivered_text="My received rendering",
        ),
        PeerMessage(
            connection_id=pair.id,
            sender_id=owner,
            recipient_id=peer.id,
            status="delivered",
            delivered_at=now,
            content=None,
            delivered_text=None,
        ),
    ]
    async_session.add_all(messages)
    await async_session.commit()

    @asynccontextmanager
    async def session():
        yield async_session

    monkeypatch.setattr(application_peer_tools, "get_db_context", session)
    pages = []
    with installed_runtime_context(user_id=owner, deps=object()):
        for offset in range(3):
            result = await application_peer_tools.get_lia_peer_settings_tool.coroutine(
                query={"section": "messages", "limit": 1, "offset": offset},
                runtime=make_tool_runtime(user_id=owner, store=InMemoryStore()),
            )
            assert result.success and result.structured_data["total"] == 3
            assert result.structured_data["next_offset"] == (offset + 1 if offset < 2 else None)
            pages.extend(result.structured_data["items"])
    assert len({item["id"] for item in pages}) == 3
    assert {item["content"] for item in pages} == {
        None,
        "My sent directive",
        "My received rendering",
    }
    assert "Other assistant" not in str(pages) and "Other sender" not in str(pages)


async def test_source_connection_list_refreshes_a_retained_pair(async_session, test_user):
    owner = test_user.id
    peer = User(
        id=uuid4(),
        email=f"fresh-{uuid4()}@example.com",
        hashed_password="controlled",
        is_active=True,
        full_name="Alice",
    )
    async_session.add(peer)
    await async_session.flush()
    lo, hi = canonical_pair(owner, peer.id)
    pair = PeerConnection(
        user_a_id=lo,
        user_b_id=hi,
        requested_by_id=owner,
        status="pending",
        requested_at=datetime.now(UTC),
    )
    async_session.add(pair)
    await async_session.commit()
    assert (await PeersService(async_session).get_pending(owner))[0].status == "pending"
    await async_session.execute(
        update(PeerConnection)
        .where(PeerConnection.id == pair.id)
        .values(status="accepted")
        .execution_options(synchronize_session=False)
    )
    await async_session.commit()
    assert pair.status == "pending"  # Retained ORM state does not decide the latest card.
    assert (await PeersService(async_session).get_connections(owner))[0].status == "accepted"
