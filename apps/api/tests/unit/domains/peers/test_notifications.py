"""dispatch_peer_events — recipients, languages, isolation (Lot 3, Task 2).

The dispatcher itself is mocked; the oracle is WHO gets notified, in WHICH
language, naming WHOM — and that one failed recipient never silences the
other (best-effort by contract, spec §6).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.domains.peers.notifications import dispatch_peer_events
from src.domains.peers.schemas import PeerEvent

ACTOR = uuid4()
OTHER = uuid4()
CONNECTION_ID = uuid4()


def _user(user_id, language="fr", full_name="Someone", is_active=True):
    return SimpleNamespace(
        id=user_id,
        language=language,
        full_name=full_name,
        is_active=is_active,
        deleted_at=None,
    )


def _db(users: dict, connection=None):
    async def _get(model, key):
        if model.__name__ == "User":
            return users.get(key)
        return connection

    db = AsyncMock()
    db.get.side_effect = _get
    return db


def _event(kind: str) -> PeerEvent:
    return PeerEvent(
        kind=kind,
        connection_id=CONNECTION_ID,
        actor_id=ACTOR,
        affected_ids=(ACTOR, OTHER),
    )


def _connection(context_message=None):
    return SimpleNamespace(id=CONNECTION_ID, context_message=context_message)


@pytest.mark.unit
class TestDispatchPeerEvents:
    async def test_request_created_notifies_only_the_addressee(self):
        users = {ACTOR: _user(ACTOR, "fr", "Marie Dupont"), OTHER: _user(OTHER, "de", "Max")}
        dispatch = AsyncMock()
        with patch("src.domains.peers.notifications.NotificationDispatcher") as dispatcher_cls:
            dispatcher_cls.return_value.dispatch = dispatch
            await dispatch_peer_events(
                [_event("request_created")], _db(users, _connection("salut !"))
            )
        assert dispatch.await_count == 1
        kwargs = dispatch.await_args.kwargs
        assert kwargs["user"].id == OTHER
        assert kwargs["task_type"] == "peer_request"
        # Body in the RECIPIENT's language, naming the requester + quoting the note.
        assert "Marie Dupont" in kwargs["content"]
        assert "salut !" in kwargs["content"]
        assert "verbinden" in kwargs["content"]  # German template

    async def test_accept_notifies_the_requester_in_their_language(self):
        users = {ACTOR: _user(ACTOR, "fr", "Max"), OTHER: _user(OTHER, "it", "Marie")}
        dispatch = AsyncMock()
        with patch("src.domains.peers.notifications.NotificationDispatcher") as dispatcher_cls:
            dispatcher_cls.return_value.dispatch = dispatch
            await dispatch_peer_events([_event("request_accepted")], _db(users, _connection()))
        assert dispatch.await_count == 1
        kwargs = dispatch.await_args.kwargs
        assert kwargs["user"].id == OTHER
        assert kwargs["task_type"] == "peer_connection"
        assert "Max" in kwargs["content"]
        assert "accettato" in kwargs["content"]  # Italian template

    async def test_removed_notifies_both_sides_each_in_own_language(self):
        users = {ACTOR: _user(ACTOR, "fr", "Marie"), OTHER: _user(OTHER, "en", "Max")}
        dispatch = AsyncMock()
        with patch("src.domains.peers.notifications.NotificationDispatcher") as dispatcher_cls:
            dispatcher_cls.return_value.dispatch = dispatch
            await dispatch_peer_events([_event("connection_removed")], _db(users, _connection()))
        assert dispatch.await_count == 2
        by_recipient = {
            call.kwargs["user"].id: call.kwargs["content"] for call in dispatch.await_args_list
        }
        assert "Max" in by_recipient[ACTOR]  # each body names the OTHER side
        assert "Marie" in by_recipient[OTHER]
        assert "supprimée" in by_recipient[ACTOR]  # French for the actor
        assert "removed" in by_recipient[OTHER]  # English for the peer

    async def test_inactive_recipient_is_skipped(self):
        users = {
            ACTOR: _user(ACTOR, "fr", "Marie"),
            OTHER: _user(OTHER, "en", "Max", is_active=False),
        }
        dispatch = AsyncMock()
        with patch("src.domains.peers.notifications.NotificationDispatcher") as dispatcher_cls:
            dispatcher_cls.return_value.dispatch = dispatch
            await dispatch_peer_events([_event("request_created")], _db(users, _connection()))
        dispatch.assert_not_awaited()

    async def test_one_failed_dispatch_never_blocks_the_other(self):
        users = {ACTOR: _user(ACTOR, "fr", "Marie"), OTHER: _user(OTHER, "en", "Max")}
        dispatch = AsyncMock(side_effect=[RuntimeError("fcm down"), None])
        with patch("src.domains.peers.notifications.NotificationDispatcher") as dispatcher_cls:
            dispatcher_cls.return_value.dispatch = dispatch
            await dispatch_peer_events([_event("connection_removed")], _db(users, _connection()))
        assert dispatch.await_count == 2  # second recipient still served
