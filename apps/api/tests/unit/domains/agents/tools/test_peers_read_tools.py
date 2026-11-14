"""Peers read tools tests (Lot 5) — share gate, levels, transparency."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.tools import peers_read_tools
from src.domains.peers.models import PeerShareDomain, PeerShareLevel
from src.domains.relations.identity import RelationIdentity

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
    repo.db.commit = AsyncMock()
    return repo


def _known_people(*identities: RelationIdentity):
    """The relationship list the name resolution consults on a partial name."""
    return patch(
        "src.domains.agents.peer.name_directory.RelationsService",
        return_value=SimpleNamespace(directory=AsyncMock(return_value=list(identities))),
    )


def _patches(repo, *known: RelationIdentity):
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
        # Never the real relationship list: it opens sessions of its own.
        _known_people(*known),
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
        db_p, repo_p, rt_p, known_p = _patches(repo)
        events = AsyncMock()
        with (
            db_p,
            repo_p,
            rt_p,
            known_p,
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
        db_p, repo_p, rt_p, known_p = _patches(repo)
        with (
            db_p,
            repo_p,
            rt_p,
            known_p,
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
        db_p, repo_p, rt_p, known_p = _patches(repo)
        with (
            db_p,
            repo_p,
            rt_p,
            known_p,
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
        db_p, repo_p, rt_p, known_p = _patches(repo)
        with (
            db_p,
            repo_p,
            rt_p,
            known_p,
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
        db_p, repo_p, rt_p, known_p = _patches(repo)
        with (
            db_p,
            repo_p,
            rt_p,
            known_p,
            patch(
                "src.domains.agents.tools.peers_read_tools._peer_task_titles",
                new=AsyncMock(return_value=(["Acheter du pain", "Appeler le plombier"], False)),
            ),
        ):
            output = await peers_read_tools.get_peer_tasks_tool.coroutine(  # type: ignore[misc]
                peer_name="Marie Dupont", runtime=MagicMock()
            )
        assert output.success is True
        assert output.structured_data["task_titles"] == ["Acheter du pain", "Appeler le plombier"]
        assert output.structured_data["partial"] is False
        assert "INCOMPLETE" not in output.message
        repo.log_access.assert_awaited_once()
        assert repo.log_access.await_args.kwargs["domain"] == "task"

    async def test_unknown_peer_is_a_neutral_not_found(self):
        repo = _repo(shares=[_share(PeerShareDomain.TASK, PeerShareLevel.TITLES)])
        db_p, repo_p, rt_p, known_p = _patches(repo)
        with db_p, repo_p, rt_p, known_p:
            output = await peers_read_tools.get_peer_tasks_tool.coroutine(  # type: ignore[misc]
                peer_name="Personne Inconnue", runtime=MagicMock()
            )
        assert output.success is False
        assert output.error_code == "NOT_FOUND"


@pytest.mark.unit
class TestPeerNameResolution:
    """A first name reads the one connection it designates — or asks."""

    async def test_a_unique_first_name_reads_and_audits_the_connection(self):
        repo = _repo(shares=[_share(PeerShareDomain.TASK, PeerShareLevel.TITLES)])
        db_p, repo_p, rt_p, known_p = _patches(repo)
        with (
            db_p,
            repo_p,
            rt_p,
            known_p,
            patch(
                "src.domains.agents.tools.peers_read_tools._peer_task_titles",
                new=AsyncMock(return_value=(["Réserver la salle"], False)),
            ),
        ):
            output = await peers_read_tools.get_peer_tasks_tool.coroutine(  # type: ignore[misc]
                peer_name="Marie", runtime=MagicMock()
            )
        assert output.success is True
        # The answer names who was read, so a wrong person can be caught.
        assert output.structured_data["peer_name"] == "Marie Dupont"
        repo.log_access.assert_awaited_once()

    async def test_a_name_designating_another_person_too_is_asked_never_read(self):
        repo = _repo(shares=[_share(PeerShareDomain.CALENDAR, PeerShareLevel.DETAILS)])
        other = RelationIdentity(
            key="marie lambert",
            display_name="Marie Lambert",
            spellings=("Marie Lambert",),
            is_peer=False,
        )
        db_p, repo_p, rt_p, known_p = _patches(repo, other)
        events = AsyncMock(return_value=EVENTS)
        with (
            db_p,
            repo_p,
            rt_p,
            known_p,
            patch("src.domains.agents.tools.peers_read_tools._peer_calendar_events", events),
        ):
            output = await peers_read_tools.get_peer_availability_tool.coroutine(  # type: ignore[misc]
                peer_name="Marie", runtime=MagicMock()
            )
        assert output.success is False
        assert output.error_code == "DISAMBIGUATION_REQUIRED"
        assert output.metadata["candidates"] == ["Marie Dupont", "Marie Lambert"]
        events.assert_not_awaited()
        repo.log_access.assert_not_awaited()  # nothing was read, nothing to audit

    async def test_a_name_designating_only_someone_not_connected_says_so(self):
        repo = _repo(shares=[_share(PeerShareDomain.CALENDAR, PeerShareLevel.DETAILS)])
        not_connected = RelationIdentity(
            key="ana costa", display_name="Ana Costa", spellings=("Ana Costa",), is_peer=False
        )
        db_p, repo_p, rt_p, known_p = _patches(repo, not_connected)
        with db_p, repo_p, rt_p, known_p:
            output = await peers_read_tools.get_peer_availability_tool.coroutine(  # type: ignore[misc]
                peer_name="Ana", runtime=MagicMock()
            )
        assert output.success is False
        assert output.error_code == "NOT_FOUND"
        assert "Ana Costa" in output.message
        assert "not a connected" in output.message
        repo.log_access.assert_not_awaited()

    async def test_the_reads_end_before_the_relationship_list_is_read(self):
        # A partial name reads the relationship list, whose SMS senders can
        # ask the contacts provider: no transaction waits on it (ADR-304).
        order: list[str] = []
        repo = _repo(shares=[_share(PeerShareDomain.CALENDAR, PeerShareLevel.DETAILS)])
        repo.db.commit = AsyncMock(side_effect=lambda: order.append("commit"))
        directory = AsyncMock(side_effect=lambda: order.append("directory") or [])
        db_p, repo_p, rt_p, _known_p = _patches(repo)
        with (
            db_p,
            repo_p,
            rt_p,
            patch(
                "src.domains.agents.peer.name_directory.RelationsService",
                return_value=SimpleNamespace(directory=directory),
            ),
        ):
            await peers_read_tools.get_peer_availability_tool.coroutine(  # type: ignore[misc]
                peer_name="Paul", runtime=MagicMock()
            )
        assert order == ["commit", "directory"]


@pytest.mark.unit
class TestAPeersTasksAreReadInEveryList:
    """Owner decision, 2026-11-10: a peer's default list is where THEY create a task, not what
    they share. Every list is read; what leaves stays the titles."""

    @staticmethod
    def _door(opened):
        @asynccontextmanager
        async def door(category, user_id, **options):
            assert (category, user_id, options) == ("tasks", PEER_ID, {}), "no default list asked"
            yield opened

        return patch.object(peers_read_tools, "open_active_client", door)

    @staticmethod
    def _client(pages):
        from src.domains.connectors.active_client import ActiveClient

        async def read(list_id, **_kwargs):
            answer = pages[list_id]
            if isinstance(answer, Exception):
                raise answer
            return {"items": [dict(task) for task in answer], "next_page_token": None}

        client = MagicMock(
            list_tasks=AsyncMock(side_effect=read),
            list_task_lists=AsyncMock(
                return_value={"items": [{"id": key, "title": f"Liste {key}"} for key in pages]}
            ),
        )
        return ActiveClient(client=client, connector_type="google", preferred_name=None)

    @staticmethod
    def _task(title, due=None, status="needsAction"):
        return {"id": title, "title": title, "status": status, **({"due": due} if due else {})}

    async def test_the_titles_of_every_list_the_most_pressing_first(self):
        opened = self._client(
            {
                "home": [
                    self._task("Plus tard", "2026-11-20T00:00:00.000Z"),
                    self._task("Sans date"),
                ],
                "work": [
                    self._task("Bientôt", "2026-11-12T00:00:00.000Z"),
                    self._task("Fait", "2026-11-01T00:00:00.000Z", status="completed"),
                    self._task("", "2026-11-02T00:00:00.000Z"),
                ],
            }
        )

        with self._door(opened):
            titles, partial = await peers_read_tools._peer_task_titles(_peer())

        assert titles == ["Bientôt", "Plus tard", "Sans date"]
        assert partial is False
        assert [call.args[0] for call in opened.client.list_tasks.await_args_list] == [
            "home",
            "work",
        ]

    async def test_only_titles_leave_never_a_list_s_name(self):
        opened = self._client({"home": [self._task("Appeler")], "work": [self._task("Envoyer")]})

        with self._door(opened):
            titles, _partial = await peers_read_tools._peer_task_titles(_peer())

        assert sorted(titles) == ["Appeler", "Envoyer"]
        assert not any("Liste" in title for title in titles)

    async def test_more_than_the_bound_is_cut_and_said(self):
        crowd = [self._task(f"T{index}") for index in range(peers_read_tools._PEER_TASKS_MAX)]
        opened = self._client({"home": crowd, "work": [self._task("Une de plus")]})

        with self._door(opened):
            titles, partial = await peers_read_tools._peer_task_titles(_peer())

        assert len(titles) == peers_read_tools._PEER_TASKS_MAX
        assert partial is True

    async def test_a_list_that_fails_leaves_the_others_and_is_said(self):
        opened = self._client({"home": TimeoutError(), "work": [self._task("Envoyer")]})

        with self._door(opened):
            titles, partial = await peers_read_tools._peer_task_titles(_peer())

        assert titles == ["Envoyer"]
        assert partial is True

    async def test_nothing_beside_a_failed_list_is_a_failure_never_no_pending_task(self):
        opened = self._client({"home": TimeoutError(), "work": []})

        with self._door(opened), pytest.raises(TimeoutError):
            await peers_read_tools._peer_task_titles(_peer())

    async def test_no_usable_connector_is_said_as_such(self):
        from src.domains.connectors.active_client import ClientUnavailable

        with self._door(ClientUnavailable.NO_CONNECTOR), pytest.raises(LookupError):
            await peers_read_tools._peer_task_titles(_peer())

    async def test_a_partial_read_reaches_the_answer(self):
        repo = _repo(shares=[_share(PeerShareDomain.TASK, PeerShareLevel.TITLES)])
        db_p, repo_p, rt_p, known_p = _patches(repo)
        with (
            db_p,
            repo_p,
            rt_p,
            known_p,
            patch(
                "src.domains.agents.tools.peers_read_tools._peer_task_titles",
                new=AsyncMock(return_value=(["Réserver la salle"], True)),
            ),
        ):
            output = await peers_read_tools.get_peer_tasks_tool.coroutine(  # type: ignore[misc]
                peer_name="Marie Dupont", runtime=MagicMock()
            )

        assert output.structured_data["partial"] is True
        assert "INCOMPLETE" in output.message
