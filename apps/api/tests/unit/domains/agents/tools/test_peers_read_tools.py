"""Peers read tools tests (Lot 5) — share gate, levels, transparency."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.tools import peers_read_tools
from src.domains.peers.models import PeerShareDomain, PeerShareLevel

USER_ID = uuid4()
PEER_ID = uuid4()
CONNECTION_ID = uuid4()


def _peer(full_name="Marie Dupont", is_active=True):
    return SimpleNamespace(
        id=PEER_ID,
        full_name=full_name,
        is_active=is_active,
        deleted_at=None,
        timezone="Europe/Rome",
    )


def _connection():
    user_a, user_b = sorted([USER_ID, PEER_ID])
    return SimpleNamespace(id=CONNECTION_ID, user_a_id=user_a, user_b_id=user_b)


def _share(domain: PeerShareDomain, level: PeerShareLevel, owner=PEER_ID):
    return SimpleNamespace(owner_user_id=owner, domain=domain.value, level=level.value)


def _repo(shares=None, peer=None):
    repo = AsyncMock()
    repo.list_accepted_for_user.return_value = [_connection()]
    repo.list_shares.return_value = shares or []
    scalars = MagicMock()
    scalars.scalars = MagicMock(return_value=iter([peer or _peer()]))
    repo.db = MagicMock()
    repo.db.execute = AsyncMock(return_value=scalars)
    return repo


def _patches(repo):
    @asynccontextmanager
    async def _ctx():
        db = MagicMock()
        db.commit = AsyncMock()
        yield db

    return (
        patch("src.domains.agents.tools.peers_read_tools.get_db_context", _ctx),
        patch(
            "src.domains.agents.tools.peers_read_tools.PeersRepository",
            return_value=repo,
        ),
        patch(
            "src.domains.agents.tools.peers_read_tools.validate_runtime_config",
            return_value=SimpleNamespace(user_id=str(USER_ID)),
        ),
    )


EVENTS = [
    {
        "id": "e1",
        "summary": "Rendez-vous médical",
        "start": {"dateTime": "2026-07-30T09:00:00+02:00"},
        "end": {"dateTime": "2026-07-30T10:00:00+02:00"},
    }
]


@pytest.mark.unit
class TestGetPeerAvailability:
    async def test_not_shared_refuses_and_never_reads(self):
        repo = _repo(shares=[])
        db_p, repo_p, rt_p = _patches(repo)
        events = AsyncMock()
        with (
            db_p,
            repo_p,
            rt_p,
            patch("src.domains.agents.tools.peers_read_tools._peer_calendar_events", events),
        ):
            output = await peers_read_tools.get_peer_availability_tool.coroutine(  # type: ignore[misc]
                peer_name="Marie Dupont", runtime=MagicMock()
            )
        assert output.success is False
        assert output.error_code == "FORBIDDEN"
        events.assert_not_awaited()
        repo.log_access.assert_not_awaited()  # no read happened, nothing to audit

    async def test_availability_level_strips_titles(self):
        repo = _repo(shares=[_share(PeerShareDomain.CALENDAR, PeerShareLevel.AVAILABILITY)])
        db_p, repo_p, rt_p = _patches(repo)
        with (
            db_p,
            repo_p,
            rt_p,
            patch(
                "src.domains.agents.tools.peers_read_tools._peer_calendar_events",
                new=AsyncMock(return_value=EVENTS),
            ),
        ):
            output = await peers_read_tools.get_peer_availability_tool.coroutine(  # type: ignore[misc]
                peer_name="marie dupont", runtime=MagicMock()
            )
        assert output.success is True
        slot = output.structured_data["busy_slots"][0]
        assert "title" not in slot  # free/busy ONLY at level availability
        assert slot["start"] == "2026-07-30T09:00:00+02:00"
        assert output.structured_data["provenance"] == "peer_shared_data"

    async def test_details_level_includes_titles_and_audits_the_read(self):
        repo = _repo(shares=[_share(PeerShareDomain.CALENDAR, PeerShareLevel.DETAILS)])
        db_p, repo_p, rt_p = _patches(repo)
        with (
            db_p,
            repo_p,
            rt_p,
            patch(
                "src.domains.agents.tools.peers_read_tools._peer_calendar_events",
                new=AsyncMock(return_value=EVENTS),
            ),
        ):
            output = await peers_read_tools.get_peer_availability_tool.coroutine(  # type: ignore[misc]
                peer_name="Marie Dupont", runtime=MagicMock()
            )
        assert output.structured_data["busy_slots"][0]["title"] == "Rendez-vous médical"
        repo.log_access.assert_awaited_once()
        audit = repo.log_access.await_args.kwargs
        assert audit["accessor_id"] == USER_ID
        assert audit["owner_id"] == PEER_ID
        assert audit["domain"] == "calendar"

    async def test_peer_without_calendar_is_not_available(self):
        repo = _repo(shares=[_share(PeerShareDomain.CALENDAR, PeerShareLevel.AVAILABILITY)])
        db_p, repo_p, rt_p = _patches(repo)
        with (
            db_p,
            repo_p,
            rt_p,
            patch(
                "src.domains.agents.tools.peers_read_tools._peer_calendar_events",
                new=AsyncMock(side_effect=LookupError("calendar_not_connected")),
            ),
        ):
            output = await peers_read_tools.get_peer_availability_tool.coroutine(  # type: ignore[misc]
                peer_name="Marie Dupont", runtime=MagicMock()
            )
        assert output.success is False
        assert output.error_code == "NOT_AVAILABLE"


@pytest.mark.unit
class TestGetPeerTasks:
    async def test_titles_shared_returns_titles_and_audits(self):
        repo = _repo(shares=[_share(PeerShareDomain.TASK, PeerShareLevel.TITLES)])
        db_p, repo_p, rt_p = _patches(repo)
        with (
            db_p,
            repo_p,
            rt_p,
            patch(
                "src.domains.agents.tools.peers_read_tools._peer_task_titles",
                new=AsyncMock(return_value=["Acheter du pain", "Appeler le plombier"]),
            ),
        ):
            output = await peers_read_tools.get_peer_tasks_tool.coroutine(  # type: ignore[misc]
                peer_name="Marie Dupont", runtime=MagicMock()
            )
        assert output.success is True
        assert output.structured_data["task_titles"] == ["Acheter du pain", "Appeler le plombier"]
        repo.log_access.assert_awaited_once()
        assert repo.log_access.await_args.kwargs["domain"] == "task"

    async def test_unknown_peer_is_a_neutral_not_found(self):
        repo = _repo(shares=[_share(PeerShareDomain.TASK, PeerShareLevel.TITLES)])
        db_p, repo_p, rt_p = _patches(repo)
        with db_p, repo_p, rt_p:
            output = await peers_read_tools.get_peer_tasks_tool.coroutine(  # type: ignore[misc]
                peer_name="Personne Inconnue", runtime=MagicMock()
            )
        assert output.success is False
        assert output.error_code == "NOT_FOUND"
