"""The hub's five totals, resolved before anything is unfolded.

The notifications hub shows five folded sections and a badge on each. The badge
was the thing a reader chooses from — "is there anything in there?" — and it
read `—` until the section was opened, because the only source of a total was
the paginated read the fold gated. So the one number that decides whether to
open a section could only be obtained by opening it.

Resolving the five totals costs ONE request, not five and not zero:

- one, because five separate counts at mount is the same client-side scatter
  the capability map was built to remove (ADR-204), with five chances for two
  answers to disagree about the same account;
- not zero, because "no request while folded" was never the goal — "no
  EXPENSIVE request" was. A count is an aggregate over an indexed column; the
  page, with its rows and its joins, still waits for the fold.

Two properties are load-bearing and easy to lose:

- a probe that fails degrades to 0 rather than taking the hub down. A hub that
  refuses to draw because one table was unreachable is worse than a hub with
  one silent badge;
- the counts come from the SAME filters as the pages they describe. A total
  assembled from a different filter is worse than no total at all (ADR-185).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def _user() -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    return user


async def _counts(**over: object):
    """Call the route with every probe stubbed."""
    from src.domains.notifications.hub_counts import HubCounts

    defaults: dict[str, object] = {
        "offers": 0,
        "peer_messages": 3,
        "proactive": 7,
        "interests": 2,
        "reminders": 1,
        "scheduled": 4,
    }
    defaults.update(over)
    with patch(
        "src.domains.notifications.router.resolve_hub_counts",
        AsyncMock(return_value=HubCounts(**defaults)),  # type: ignore[arg-type]
    ):
        from src.domains.notifications.router import get_hub_counts

        return await get_hub_counts(user=_user())


class TestWhatTheHubPublishes:
    async def test_it_answers_all_five_sections_in_one_payload(self) -> None:
        result = await _counts()

        assert result.peer_messages == 3
        assert result.proactive == 7
        assert result.interests == 2
        assert result.reminders == 1
        assert result.scheduled == 4

    async def test_zero_is_a_real_answer_not_a_missing_one(self) -> None:
        """An empty section must read as empty, never as unknown."""
        result = await _counts(peer_messages=0, proactive=0)

        assert result.peer_messages == 0
        assert result.proactive == 0

    async def test_no_count_is_ever_negative(self) -> None:
        from src.domains.notifications.schemas import HubCountsResponse

        for field in HubCountsResponse.model_fields.values():
            assert any(
                getattr(meta, "ge", None) == 0 for meta in field.metadata
            ), "every count is a cardinality, and a cardinality is >= 0"


class TestTheProbesDegradeRatherThanFail:
    async def test_an_unreadable_table_counts_as_zero(self) -> None:
        """One unreachable table must not blank the whole hub."""
        from src.domains.notifications.hub_counts import _safe_count

        async def boom() -> int:
            raise RuntimeError("db went away")

        assert await _safe_count("peer_messages", boom()) == 0

    async def test_a_successful_probe_returns_its_value(self) -> None:
        from src.domains.notifications.hub_counts import _safe_count

        async def fine() -> int:
            return 12

        assert await _safe_count("reminders", fine()) == 12

    async def test_every_probe_runs_on_its_own_session(self) -> None:
        """`AsyncSession` is not safe for concurrent use — one per probe."""
        from pathlib import Path

        source = Path("src/domains/notifications/hub_counts.py").read_text(encoding="utf-8")
        # Five gathered probes, five context managers.
        assert source.count("async with get_db_context()") == 6
        assert "asyncio.gather" in source


class TestADisabledSubsystemIsNotQueried:
    """Gate-keeper (ADR-061): the hub does not render those sections at all.

    Counting them would be two SQL statements per hub load for a badge nobody
    can see — and the section is absent, not empty, so 0 is not even shown.
    """

    async def test_peers_off_returns_zero_without_touching_the_database(self) -> None:
        from src.domains.notifications import hub_counts

        with patch.object(hub_counts.settings, "peers_enabled", False):
            with patch.object(hub_counts, "get_db_context") as db_context:
                assert await hub_counts._peer_messages(uuid.uuid4()) == 0
                db_context.assert_not_called()

    async def test_heartbeat_off_returns_zero_without_touching_the_database(self) -> None:
        from src.domains.notifications import hub_counts

        with patch.object(hub_counts.settings, "heartbeat_enabled", False):
            with patch.object(hub_counts, "get_db_context") as db_context:
                assert await hub_counts._proactive(uuid.uuid4()) == 0
                db_context.assert_not_called()

    async def test_a_section_the_instance_offers_is_still_counted(self) -> None:
        """The guard must not silence an ENABLED subsystem."""
        from src.domains.notifications import hub_counts

        with patch.object(hub_counts.settings, "peers_enabled", True):
            with patch.object(hub_counts, "get_db_context") as db_context:
                db_context.side_effect = RuntimeError("reached the database")
                with pytest.raises(RuntimeError, match="reached the database"):
                    await hub_counts._peer_messages(uuid.uuid4())
