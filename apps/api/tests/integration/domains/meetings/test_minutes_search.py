"""Search the current minutes on PostgreSQL, never the raw JSON or transcript."""

import logging
from datetime import UTC, datetime
from time import perf_counter
from uuid import UUID, uuid4

import pytest
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.meetings.models import Meeting, MeetingAudioFormat, MeetingStatus
from src.domains.meetings.repository import MeetingRepository
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration


async def _meeting(db: AsyncSession, report: dict[str, object] | None, **fields: object) -> Meeting:
    user = UserFactory.create()
    db.add(user)
    await db.flush()
    meeting = Meeting(
        user_id=user.id,
        status=MeetingStatus.READY,
        audio_format=MeetingAudioFormat.PCM_S16LE_16,
        started_at=datetime(2026, 10, 18, tzinfo=UTC),
        client_timezone="UTC",
        report_current=report,
        **fields,
    )
    db.add(meeting)
    await db.flush()
    return meeting


@pytest.mark.parametrize(
    ("report", "query"),
    [
        (
            {"title": "Décision d’architecture à 50\u202f%"},
            "decision d'architecture a 50 %",
        ),
        ({"participants": [{"name": "Élodie", "role": "ingénieure"}]}, "ingenieure"),
        (
            {"sections": [{"kind": "paragraph", "paragraph": "Résumé clé"}]},
            "resume cle",
        ),
        ({"sections": [{"kind": "bullets", "bullets": ["café"]}]}, "CAFE"),
        (
            {"sections": [{"kind": "topics", "topics": [{"summary": "réponse"}]}]},
            "reponse",
        ),
        (
            {"sections": [{"kind": "action_items", "action_items": [{"owner": "Zoé"}]}]},
            "zoe",
        ),
        (
            {"sections": [{"kind": "transcript", "transcript": [{"text": "réécrit"}]}]},
            "reecrit",
        ),
        ({"sections": [{"kind": "bullets", "label": "Échanges"}]}, "echanges"),
        ({"title": "100%_\\"}, "%_\\"),
    ],
)
async def test_allowed_strings_are_searchable(
    async_session: AsyncSession, report: dict[str, object], query: str
) -> None:
    meeting = await _meeting(async_session, report)
    rows, total = await MeetingRepository(async_session).list_for_user(
        meeting.user_id, limit=20, offset=0, query=query
    )
    assert total == 1 and [row.id for row in rows] == [meeting.id]


@pytest.mark.parametrize(
    ("report", "query"),
    [
        ({"title": "ordinary", "diagnostics": "secret"}, "secret"),
        ({"participants": [{"label": "SPEAKER_SECRET"}]}, "SPEAKER_SECRET"),
        (
            {"sections": [{"kind": "paragraph", "key": "internal_secret"}]},
            "internal_secret",
        ),
        (
            {"sections": [{"kind": "bullets", "paragraph": "inactive_secret"}]},
            "inactive_secret",
        ),
        ({"title": {"hidden": "secret"}}, "secret"),
        ({"title": 12345}, "12345"),
        ({"title": ["secret"]}, "secret"),
        ({"sections": {"label": "secret"}}, "secret"),
        ({"participants": {"name": "secret"}}, "secret"),
        ({"title": "alpha", "sections": [{"label": "beta"}]}, "alpha beta"),
        ({"title": "Budget 1000"}, "100%"),
        (None, "missing"),
    ],
)
async def test_internal_wrong_kind_and_nonstring_values_do_not_match(
    async_session: AsyncSession, report: dict[str, object] | None, query: str
) -> None:
    meeting = await _meeting(async_session, report, report_generated={"title": query})
    rows, total = await MeetingRepository(async_session).list_for_user(
        meeting.user_id, limit=20, offset=0, query=query
    )
    assert (rows, total) == ([], 0)


async def test_snapshot_count_survives_empty_page_and_owner_isolation(
    async_session: AsyncSession,
) -> None:
    meeting = await _meeting(async_session, {"title": "alpha"}, location_label="Bâtiment")
    repo = MeetingRepository(async_session)
    for query in ("alpha", "batiment", "", None):
        rows, total = await repo.list_for_user(meeting.user_id, limit=1, offset=100, query=query)
        assert rows == [] and total == 1
    assert await repo.list_for_user(uuid4(), limit=20, offset=0, query="alpha") == (
        [],
        0,
    )
    meeting.report_current = {"title": "beta"}
    await async_session.flush()
    assert await repo.list_for_user(meeting.user_id, limit=20, offset=0, query="alpha") == ([], 0)


async def test_equal_time_order_is_stable_and_search_is_not_limited_to_first_page(
    async_session: AsyncSession,
) -> None:
    meeting = await _meeting(async_session, {"title": "target"})
    other = Meeting(
        id=UUID(int=1),
        user_id=meeting.user_id,
        status=MeetingStatus.FAILED,
        audio_format=MeetingAudioFormat.PCM_S16LE_16,
        started_at=meeting.started_at,
        client_timezone="UTC",
        report_current={"title": "other"},
    )
    async_session.add(other)
    await async_session.flush()
    repo = MeetingRepository(async_session)
    rows, total = await repo.list_for_user(meeting.user_id, limit=1, offset=1)
    assert total == 2 and [row.id for row in rows] == [other.id]
    rows, total = await repo.list_for_user(meeting.user_id, limit=1, offset=0, query="target")
    assert total == 1 and [row.id for row in rows] == [meeting.id]


async def test_long_reports_do_not_require_loading_the_history(
    async_session: AsyncSession,
) -> None:
    """A representative SQL probe: many long reports and no-match worst case."""
    meeting = await _meeting(async_session, {"title": "seed"})
    report = {
        "title": "Compte rendu",
        "sections": [
            {
                "kind": "paragraph",
                "label": f"Section {number}",
                "paragraph": "échange " * 900,
            }
            for number in range(8)
        ],
    }
    await async_session.execute(
        insert(Meeting),
        [
            {
                "id": uuid4(),
                "user_id": meeting.user_id,
                "status": MeetingStatus.READY,
                "audio_format": MeetingAudioFormat.PCM_S16LE_16,
                "started_at": meeting.started_at,
                "client_timezone": "UTC",
                "report_current": report,
            }
            for _ in range(500)
        ],
    )
    started = perf_counter()
    rows, total = await MeetingRepository(async_session).list_for_user(
        meeting.user_id, limit=20, offset=0, query="absent_token"
    )
    elapsed = perf_counter() - started
    assert (rows, total) == ([], 0)
    assert len(async_session.identity_map) < 10
    logging.getLogger(__name__).info("minutes_search_probe histories=501 seconds=%.3f", elapsed)
