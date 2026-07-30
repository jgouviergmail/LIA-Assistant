"""Peers router endpoint tests (Lot 1, Task 7) — open_loops house style.

Endpoint functions are called directly with a patched PeersService; the
route-table tests pin the surface (paths, rate-limit dependency on the
discovery search) so a silent unwiring cannot pass.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.peers.models import PeerShareDomain, PeerShareLevel
from src.domains.peers.router import (
    respond_to_request,
    router,
    search_discovery,
    set_or_delete_share,
)
from src.domains.peers.schemas import (
    ConnectionRespond,
    ConnectionStateView,
    DiscoveryMatch,
    DiscoverySearchRequest,
    ShareUpdate,
)


def _user():
    return SimpleNamespace(id=uuid4())


def _service(**overrides):
    service = MagicMock()
    for name, value in overrides.items():
        setattr(service, name, AsyncMock(return_value=value))
    return service


@pytest.mark.unit
class TestEndpointDelegation:
    async def test_search_delegates_to_service(self):
        match = DiscoveryMatch(peer_id=uuid4(), display_name="Peer Beta", email_hint="b…@t….local")
        service = _service(search_discoverable=[match])
        with patch("src.domains.peers.router.PeersService", return_value=service):
            result = await search_discovery(
                payload=DiscoverySearchRequest(full_name="Peer Beta"),
                user=_user(),
                db=MagicMock(),
            )
        assert result == [match]

    async def test_respond_commits_then_dispatches_events(self):
        view = ConnectionStateView(id=uuid4(), status="accepted")
        service = _service(respond_request=view)
        service.pending_events = ["evt"]
        db = MagicMock()
        db.commit = AsyncMock()
        with (
            patch("src.domains.peers.router.PeersService", return_value=service),
            patch("src.domains.peers.router.dispatch_peer_events", new=AsyncMock()) as dispatch,
        ):
            result = await respond_to_request(
                connection_id=view.id,
                payload=ConnectionRespond(accept=True),
                user=_user(),
                db=db,
            )
        assert result.status == "accepted"
        db.commit.assert_awaited_once()
        dispatch.assert_awaited_once_with(["evt"], db)

    async def test_dispatch_failure_never_fails_the_committed_action(self):
        """Notification hiccup after commit → warning, not a 500 (Lot 3)."""
        view = ConnectionStateView(id=uuid4(), status="accepted")
        service = _service(respond_request=view)
        service.pending_events = ["evt"]
        db = MagicMock()
        db.commit = AsyncMock()
        with (
            patch("src.domains.peers.router.PeersService", return_value=service),
            patch(
                "src.domains.peers.router.dispatch_peer_events",
                new=AsyncMock(side_effect=RuntimeError("redis down")),
            ),
        ):
            result = await respond_to_request(
                connection_id=view.id,
                payload=ConnectionRespond(accept=True),
                user=_user(),
                db=db,
            )
        assert result.status == "accepted"  # the action still succeeds

    async def test_share_update_delegates_enums_and_commits(self):
        service = _service(set_share=None)
        db = MagicMock()
        db.commit = AsyncMock()
        connection_id = uuid4()
        user = _user()
        with patch("src.domains.peers.router.PeersService", return_value=service):
            await set_or_delete_share(
                connection_id=connection_id,
                payload=ShareUpdate(domain=PeerShareDomain.CALENDAR, level=PeerShareLevel.DETAILS),
                user=user,
                db=db,
            )
        service.set_share.assert_awaited_once_with(
            user.id, connection_id, PeerShareDomain.CALENDAR, PeerShareLevel.DETAILS
        )
        db.commit.assert_awaited_once()


@pytest.mark.unit
class TestRouteTable:
    """The surface itself is pinned — a silently missing route cannot pass."""

    def test_all_expected_paths_declared(self):
        paths = {route.path for route in router.routes}
        assert paths == {
            "/peers/me",
            "/peers/discovery/search",
            "/peers/requests",
            "/peers/requests/{connection_id}/respond",
            "/peers/connections",
            "/peers/connections/{connection_id}",
            "/peers/connections/{connection_id}/shares",
            "/peers/access-log",
            "/peers/blocks",
            "/peers/blocks/{peer_id}",
        }

    def test_discovery_search_carries_the_rate_limit_dependency(self):
        route = next(r for r in router.routes if r.path == "/peers/discovery/search")
        dependency_names = {
            d.call.__name__ for d in route.dependant.dependencies if d.call is not None
        }
        assert "rate_limit_dependency" in dependency_names
