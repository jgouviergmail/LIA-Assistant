"""A peer's broken connector must not read as a peer who shares nothing.

Both states produced the same sentence — "{peer} has no connected calendar
right now" — and they are not the same fact for the person asking:

- *never connected*: nothing will change until the peer sets it up;
- *connector in ERROR*: the peer had it working, their OAuth access broke, and
  one reconnection restores it.

Lived on 2026-07-30: the asking user was told the peer had no connected
calendar at 13:23, while that peer had connected Google Calendar on 2 July and
was himself unaware his connectors had broken — so the message read as plainly
false and sent the diagnosis in the wrong direction for an hour.

``find_error_connector_type`` (ADR-134 V2) already draws exactly this line for
the connector-notice banner; the peer read path reuses it rather than inventing
a second notion of "broken".
"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.tools import peers_read_tools
from src.domains.peers.models import PeerShareDomain


def _peer() -> MagicMock:
    peer = MagicMock()
    peer.id = uuid4()
    peer.full_name = "Jérôme G"
    peer.timezone = "Europe/Paris"
    peer.is_active = True
    peer.deleted_at = None
    return peer


@asynccontextmanager
async def _db_ctx():
    # AsyncMock: the tool awaits `db.commit()` after writing the access log.
    yield AsyncMock()


async def _run_availability(*, error_connector: str | None):
    """Call the tool with the provider lookup failing, ERROR state configurable."""
    connection = MagicMock()
    connection.id = uuid4()
    peer = _peer()
    repo = MagicMock()
    repo.log_access = AsyncMock()

    validated = MagicMock()
    validated.user_id = str(uuid4())

    with (
        patch.object(peers_read_tools, "validate_runtime_config", return_value=validated),
        patch.object(peers_read_tools, "get_db_context", _db_ctx),
        patch.object(peers_read_tools, "PeersRepository", return_value=repo),
        patch.object(
            peers_read_tools,
            "_resolve_shared_peer",
            AsyncMock(return_value=(connection, peer, "details", "")),
        ),
        patch.object(
            peers_read_tools,
            "_peer_calendar_events",
            AsyncMock(side_effect=LookupError("calendar_not_connected")),
        ),
        patch.object(
            peers_read_tools,
            "find_error_connector_type",
            AsyncMock(return_value=error_connector),
        ),
    ):
        return await peers_read_tools.get_peer_availability_tool.coroutine(
            peer_name="Jerome G", runtime=MagicMock()
        )


@pytest.mark.asyncio
async def test_broken_connector_is_reported_as_broken_not_as_absent():
    """The 13:23 case: the peer HAD a calendar, their access was broken."""
    output = await _run_availability(error_connector="google_calendar")

    assert output.success is False
    message = output.message.lower()
    assert "no connected calendar" not in message
    assert "jérôme g" in message
    # The asking user must learn the fault is on the peer's side and temporary.
    assert "reconnect" in message or "broken" in message


@pytest.mark.asyncio
async def test_absent_connector_keeps_the_never_connected_wording():
    """A peer who never connected a calendar must not be told to reconnect."""
    output = await _run_availability(error_connector=None)

    assert output.success is False
    assert "no connected calendar" in output.message.lower()


@pytest.mark.asyncio
async def test_the_two_states_do_not_share_a_message():
    """Whatever the wording, the two facts must never be indistinguishable."""
    broken = await _run_availability(error_connector="google_calendar")
    absent = await _run_availability(error_connector=None)

    assert broken.message != absent.message


@pytest.mark.asyncio
async def test_peer_name_is_never_replaced_by_the_connector_type():
    """The connector type is the peer's private plumbing, not the answer."""
    output = await _run_availability(error_connector="google_calendar")

    assert "google_calendar" not in output.message


async def _run_tasks(*, error_connector: str | None):
    """Same harness on the TASKS tool — the parity this file exists to hold."""
    connection = MagicMock()
    connection.id = uuid4()
    peer = _peer()
    repo = MagicMock()
    repo.log_access = AsyncMock()
    validated = MagicMock()
    validated.user_id = str(uuid4())

    with (
        patch.object(peers_read_tools, "validate_runtime_config", return_value=validated),
        patch.object(peers_read_tools, "get_db_context", _db_ctx),
        patch.object(peers_read_tools, "PeersRepository", return_value=repo),
        patch.object(
            peers_read_tools,
            "_resolve_shared_peer",
            AsyncMock(return_value=(connection, peer, "titles", "")),
        ),
        patch.object(
            peers_read_tools,
            "_peer_task_titles",
            AsyncMock(side_effect=LookupError("tasks_not_connected")),
        ),
        patch.object(
            peers_read_tools,
            "find_error_connector_type",
            AsyncMock(return_value=error_connector),
        ),
    ):
        return await peers_read_tools.get_peer_tasks_tool.coroutine(
            peer_name="Jerome G", runtime=MagicMock()
        )


@pytest.mark.asyncio
async def test_tasks_broken_connector_is_reported_as_broken_not_as_absent():
    """The tasks tool must not be the one that kept the old conflation.

    Both tools call the same helper, so this looks redundant — it is not: only
    this test fails if the tasks call site is reverted to the flat message,
    and a shared helper nobody is proved to call is a helper that drifts.
    """
    output = await _run_tasks(error_connector="google_tasks")

    message = output.message.lower()
    assert "no connected task list" not in message
    assert "broken" in message or "reconnect" in message


@pytest.mark.asyncio
async def test_tasks_absent_connector_keeps_the_never_connected_wording():
    output = await _run_tasks(error_connector=None)

    assert "no connected task list" in output.message.lower()


@pytest.mark.asyncio
async def test_tasks_never_leak_the_connector_type():
    assert "google_tasks" not in (await _run_tasks(error_connector="google_tasks")).message


@pytest.mark.asyncio
async def test_state_lookup_failure_degrades_to_the_plain_message():
    """The refinement must never be able to worsen the failure it describes.

    It adds a database read on a path that is already failing; if that read
    raises, the tool must still return a clean "not available" rather than
    propagate — losing the whole answer to improve a wording is a bad trade.
    """
    connection = MagicMock()
    connection.id = uuid4()
    peer = _peer()
    repo = MagicMock()
    repo.log_access = AsyncMock()
    validated = MagicMock()
    validated.user_id = str(uuid4())

    with (
        patch.object(peers_read_tools, "validate_runtime_config", return_value=validated),
        patch.object(peers_read_tools, "get_db_context", _db_ctx),
        patch.object(peers_read_tools, "PeersRepository", return_value=repo),
        patch.object(
            peers_read_tools,
            "_resolve_shared_peer",
            AsyncMock(return_value=(connection, peer, "details", "")),
        ),
        patch.object(
            peers_read_tools,
            "_peer_calendar_events",
            AsyncMock(side_effect=LookupError("calendar_not_connected")),
        ),
        patch.object(
            peers_read_tools,
            "find_error_connector_type",
            AsyncMock(side_effect=RuntimeError("pool exhausted")),
        ),
    ):
        output = await peers_read_tools.get_peer_availability_tool.coroutine(
            peer_name="Jerome G", runtime=MagicMock()
        )

    assert output.success is False
    assert output.error_code == "NOT_AVAILABLE"
    assert "no connected calendar" in output.message.lower()


@pytest.mark.asyncio
async def test_access_is_still_logged_before_the_provider_call(monkeypatch):
    """Transparency (spec §12.4) survives the new branch: the attempt is logged."""
    connection = MagicMock()
    connection.id = uuid4()
    peer = _peer()
    repo = MagicMock()
    repo.log_access = AsyncMock()
    validated = MagicMock()
    validated.user_id = str(uuid4())

    with (
        patch.object(peers_read_tools, "validate_runtime_config", return_value=validated),
        patch.object(peers_read_tools, "get_db_context", _db_ctx),
        patch.object(peers_read_tools, "PeersRepository", return_value=repo),
        patch.object(
            peers_read_tools,
            "_resolve_shared_peer",
            AsyncMock(return_value=(connection, peer, "details", "")),
        ),
        patch.object(
            peers_read_tools,
            "_peer_calendar_events",
            AsyncMock(side_effect=LookupError("calendar_not_connected")),
        ),
        patch.object(peers_read_tools, "find_error_connector_type", AsyncMock(return_value=None)),
    ):
        await peers_read_tools.get_peer_availability_tool.coroutine(
            peer_name="Jerome G", runtime=MagicMock()
        )

    repo.log_access.assert_awaited_once()
    assert repo.log_access.await_args.kwargs["domain"] == PeerShareDomain.CALENDAR.value
